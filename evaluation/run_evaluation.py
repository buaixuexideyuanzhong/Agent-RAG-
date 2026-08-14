"""
活动策划系统质量评估工具

在项目根目录运行（用 conda env huodongcehua 的 python）：
    python -m evaluation.run_evaluation                  # 跑全部用例，输出评分表（manual）
    python -m evaluation.run_evaluation --limit 3        # 只跑前 3 条（快速验证）
    python -m evaluation.run_evaluation --judge llm      # 质量维度用 GLM 自动打分（消耗 token）

自动计算客观指标：
- 需求提取准确率：Requirements 提取结果 vs 测试用例的约束真值逐字段比对
- 方案层约束召回率：方案正确覆盖的约束数 / 用户提出的约束总数（漏掉或做错都会扣）
- 方案层约束准确率：方案正确覆盖的约束数 / 方案中提到的约束数（提到即错会扣）
- 工具真实命中率：场地/商家/流程三个搜索节点是否真实调用外部工具（未降级、未报错）
- 结构完整性：方案是否覆盖概述/流程/场地/商家/预算/任务/风险 7 大板块

质量维度（5 分制，--judge llm 自动打分或 manual 输出评分表人工填）：
完整性 / 可执行性 / 预算合规 / 逻辑一致 / 信息真实
"""
import argparse
import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.cli.main import ActivityPlanner
from backend.core.models import _coerce_number

EVAL_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVAL_DIR / "results"

# ==================== 常量 ====================

# 数值字段容差（±20%）
TOLERANCE = 0.2

# 方案结构完整性：7 大板块检查词
STRUCTURE_CHECKPOINTS = [
    ("概述", ["活动概述", "活动主题", "活动目标"]),
    ("流程", ["流程安排", "时间轴", "时间安排"]),
    ("场地", ["场地配置", "场地推荐", "场地"]),
    ("商家", ["商家资源", "商家推荐", "供应商", "商家"]),
    ("预算", ["预算明细", "预算"]),
    ("任务", ["任务清单", "负责人"]),
    ("风险", ["风险提示", "注意事项", "避坑"]),
]

# 搜索节点（用于从 errors 判断工具真实命中）
SEARCH_NODES = [
    ("场地", "场地搜索"),
    ("商家", "商家搜索"),
    ("流程", "流程参考搜索"),
]

# 质量评分维度
QUALITY_DIMS = ["完整性", "可执行性", "预算合规", "逻辑一致", "信息真实"]

JUDGE_PROMPT = """你是活动策划质量评估专家。请根据以下 5 个维度对生成的策划方案打分（每项 1-5 分，整数）：
1. 完整性：是否包含活动概述/流程安排/场地配置/商家资源/预算明细/任务清单/风险提示
2. 可执行性：时间轴具体到时间点，任务有负责人和时间节点
3. 预算合规：预算明细合计在用户预算范围内，分项合理
4. 逻辑一致：场地容量≥人数、流程时长合理、场地商家地域匹配
5. 信息真实：场地/商家信息来自真实工具（若用户需求与方案所在地区无真实数据，视为可用方案打分）

只输出 JSON，不要其他文字，格式如：{{"完整性":4,"可执行性":3,"预算合规":5,"逻辑一致":4,"信息真实":3}}

【用户需求】
{request}

【策划方案】
{plan}

【系统提示（工具降级/错误）】
{errors}
"""

_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(万|w|W|亿|人|名|位|元)?")


# ==================== 文本/数值匹配工具 ====================

def _norm(s: Any) -> str:
    return str(s).strip().lower()


def _coerce_num(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(_coerce_number(v))
    except Exception:
        return None


def _extract_numbers(text: str) -> List[float]:
    """从文本提取数字（'20万'→200000，'500人'→500），用于约束数值匹配"""
    nums: List[float] = []
    for m in _NUM_RE.finditer(text or ""):
        try:
            num = float(m.group(1))
        except ValueError:
            continue
        unit = m.group(2)
        if unit and unit.lower() == "万":
            num *= 10000
        elif unit == "亿":
            num *= 1e8
        nums.append(num)
    return nums


def _num_in_range(nums: List[float], target: float, tol: float = TOLERANCE) -> bool:
    return any(target * (1 - tol) <= n <= target * (1 + tol) for n in nums)


def _kw_in(text: str, kw: str) -> bool:
    if not kw:
        return True
    return _norm(kw) in _norm(text)


def _field_match(actual: Any, expected: Any, field: str) -> bool:
    """需求提取层：LLM 提取结果字段 vs 真值"""
    if expected is None:
        return True
    if field in ("attendee_count", "budget"):
        e, a = _coerce_num(expected), _coerce_num(actual)
        if e is None or a is None:
            return False
        return abs(a - e) / e <= TOLERANCE
    if isinstance(expected, list):
        exp = {_norm(x) for x in expected}
        act = {_norm(x) for x in (actual or [])}
        return exp.issubset(act) if exp else True
    if isinstance(actual, list):
        return _norm(expected) in {_norm(x) for x in actual}
    return _norm(expected) in _norm(actual) or _norm(actual) in _norm(expected)


def _plan_mentions(plan_text: str, value: Any, field: str) -> bool:
    """方案是否"提到"该约束（宽匹配，数值 ±200% 视为提到）——用于准确率分母"""
    text = plan_text or ""
    if value is None:
        return True
    if field in ("attendee_count", "budget"):
        target = _coerce_num(value)
        if target is None:
            return False
        return _num_in_range(_extract_numbers(text), target, tol=2.0)
    if isinstance(value, list):
        # 提到 = 至少一个关键词出现
        return any(_kw_in(text, str(v)) for v in value)
    return _kw_in(text, str(value))


def _plan_contains(plan_text: str, value: Any, field: str) -> bool:
    """方案是否"正确覆盖"该约束（数值 ±20%，文本包含，列表逐项全含）——用于召回率分子"""
    text = plan_text or ""
    if value is None:
        return True
    if field in ("attendee_count", "budget"):
        target = _coerce_num(value)
        if target is None:
            return False
        return _num_in_range(_extract_numbers(text), target)
    if isinstance(value, list):
        return all(_kw_in(text, str(v)) for v in value)
    return _kw_in(text, str(value))


# ==================== 各维度评估 ====================

def eval_extraction(expected: Dict, requirements: Any) -> Tuple[int, int]:
    """需求提取准确率：返回 (正确字段数, 检查字段数)"""
    if not expected:
        return 0, 0
    req = requirements or {}
    checked = correct = 0
    for field, true_val in expected.items():
        if true_val is None:
            continue
        checked += 1
        if _field_match(req.get(field), true_val, field):
            correct += 1
    return correct, checked


def eval_plan_constraints(plan_text: Optional[str], expected: Dict) -> Tuple[int, int, int]:
    """方案层约束：返回 (总约束数, 被方案提到的约束数, 正确覆盖的约束数)

    召回率 = correct/total（漏掉或做错都会扣）；
    准确率 = correct/covered（仅扣"提到但做错"，如人数写错）。
    """
    if not expected:
        return 0, 0, 0
    total = covered = correct = 0
    for field, true_val in expected.items():
        if true_val is None:
            continue
        total += 1
        if _plan_mentions(plan_text or "", true_val, field):
            covered += 1
        if _plan_contains(plan_text or "", true_val, field):
            correct += 1
    return total, covered, correct


def eval_tool_hits(errors: List[str]) -> List[bool]:
    """工具真实命中率：三个搜索节点是否真实调用外部工具（未降级、未失败）"""
    errors = errors or []
    hits: List[bool] = []
    for _, node in SEARCH_NODES:
        related = [e for e in errors if node in e]
        degraded = any("降级" in e for e in related)
        failed = any("失败" in e for e in related)
        hits.append(not degraded and not failed)
    return hits


def eval_structure(plan_text: Optional[str]) -> List[bool]:
    """结构完整性：7 大板块是否覆盖"""
    text = plan_text or ""
    return [any(_kw_in(text, kw) for kw in kws) for _, kws in STRUCTURE_CHECKPOINTS]


async def judge_llm(request: str, plan: Optional[str], errors: List[str]) -> Optional[Dict[str, int]]:
    """用 GLM 按 rubric 对方案打分（消耗 token）"""
    from backend.agents.agents import LLMClient

    prompt = JUDGE_PROMPT.format(
        request=request,
        plan=plan or "（未生成方案）",
        errors="\n".join(errors) if errors else "无",
    )
    try:
        client = LLMClient()
        # glm-4.6v 是推理模型：会先输出大量 reasoning_content，正文 content 在最后。
        # max_tokens 必须给足推理+JSON 预算（实测 1024 会被推理耗尽导致正文为空），这里用 4096。
        # on_chunk 传空回调：禁用 LLM 缓存（judge 输出不稳定，空结果不应被缓存复用）
        text = await client.chat(
            system_prompt="你是严谨的活动策划质量评估助手，只输出 JSON。",
            user_message=prompt,
            max_tokens=4096,
            on_chunk=lambda d: None,
        )
        # 提取 JSON 部分（GLM 偶尔返回带转义引号的 JSON，先直接解析、失败再反转义）
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None
        raw = m.group(0)
        scores: Optional[Dict[str, Any]] = None
        for candidate in (raw, raw.replace('\\"', '"')):
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    scores = parsed
                    break
            except Exception:
                continue
        if not scores:
            return None
        return {k: int(v) for k, v in scores.items() if k in QUALITY_DIMS}
    except Exception as e:
        print(f"  ⚠️ LLM 评分失败: {e}")
        return None


# ==================== 主流程 ====================

def load_test_cases() -> List[Dict]:
    path = EVAL_DIR / "test_cases.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["cases"]


async def run_case(planner: ActivityPlanner, case: Dict, judge_mode: str) -> Dict:
    cid = case["id"]
    request = case["request"]
    expected = case.get("expected_constraints", {})
    print(f"\n▶ 运行 {cid}: {request[:40]}...", flush=True)

    result = await planner.plan(request, console_output=False)
    plan_text = result.get("plan")
    requirements = result.get("requirements")
    errors = result.get("errors", [])

    # 客观指标
    ext_correct, ext_checked = eval_extraction(expected, requirements)
    total, covered, correct = eval_plan_constraints(plan_text, expected)
    tool_hits = eval_tool_hits(errors)
    structure = eval_structure(plan_text)

    # 质量维度评分
    quality: Optional[Dict[str, int]] = None
    if judge_mode == "llm":
        quality = await judge_llm(request, plan_text, errors)

    return {
        "id": cid,
        "request": request,
        "success": result.get("success"),
        "plan": plan_text,
        "requirements": requirements,
        "messages": result.get("messages", []),
        "errors": errors,
        "expected_constraints": expected,
        "metrics": {
            "extraction": {"correct": ext_correct, "checked": ext_checked},
            "plan_constraints": {"total": total, "covered": covered, "correct": correct},
            "tool_hits": {name: hit for (name, _), hit in zip(SEARCH_NODES, tool_hits)},
            "structure": {name: hit for (name, _), hit in zip(STRUCTURE_CHECKPOINTS, structure)},
        },
        "quality_scores": quality,
    }


def _rate(dividend: int, divisor: int) -> Optional[float]:
    return round(dividend / divisor, 3) if divisor else None


def summarize(results: List[Dict]) -> Dict:
    agg = {
        "ext_correct": 0, "ext_checked": 0,
        "pc_total": 0, "pc_covered": 0, "pc_correct": 0,
        "tool_hits": 0, "tool_total": 0,
        "struct_hits": 0, "struct_total": 0,
        "success_cases": 0,
    }
    qual_sums: Dict[str, List[int]] = {d: [] for d in QUALITY_DIMS}
    for r in results:
        m = r["metrics"]
        agg["ext_correct"] += m["extraction"]["correct"]
        agg["ext_checked"] += m["extraction"]["checked"]
        agg["pc_total"] += m["plan_constraints"]["total"]
        agg["pc_covered"] += m["plan_constraints"]["covered"]
        agg["pc_correct"] += m["plan_constraints"]["correct"]
        for name, _ in SEARCH_NODES:
            agg["tool_total"] += 1
            if m["tool_hits"][name]:
                agg["tool_hits"] += 1
        for name, _ in STRUCTURE_CHECKPOINTS:
            agg["struct_total"] += 1
            if m["structure"][name]:
                agg["struct_hits"] += 1
        if r["success"]:
            agg["success_cases"] += 1
        for d, s in (r.get("quality_scores") or {}).items():
            qual_sums[d].append(s)

    ext_rate = _rate(agg["ext_correct"], agg["ext_checked"])
    recall = _rate(agg["pc_correct"], agg["pc_total"])           # 正确覆盖/总约束
    precision = _rate(agg["pc_correct"], agg["pc_covered"])      # 正确覆盖/提到约束
    tool_rate = _rate(agg["tool_hits"], agg["tool_total"])
    struct_rate = _rate(agg["struct_hits"], agg["struct_total"])

    return {
        "case_count": len(results),
        "success_cases": agg["success_cases"],
        "extraction_accuracy": ext_rate,
        "constraint_recall": recall,
        "constraint_precision": precision,
        "tool_hit_rate": tool_rate,
        "structure_completeness": struct_rate,
        "quality_scores": {
            d: (round(sum(v) / len(v), 2) if v else None) for d, v in qual_sums.items()
        },
    }


def render_report(results: List[Dict], summary: Dict) -> str:
    lines = [
        "# 活动策划系统质量评估报告",
        "",
        f"用例数: {summary['case_count']}  |  成功: {summary['success_cases']}",
        "",
        "## 客观指标",
        "",
        "| 指标 | 值 |",
        "|---|---|",
        f"| 需求提取准确率 | {summary['extraction_accuracy'] or '-'} |",
        f"| 方案约束召回率 | {summary['constraint_recall'] or '-'} |",
        f"| 方案约束准确率 | {summary['constraint_precision'] or '-'} |",
        f"| 工具真实命中率 | {summary['tool_hit_rate'] or '-'} |",
        f"| 结构完整性 | {summary['structure_completeness'] or '-'} |",
        "",
        "## 质量维度分（5 分制）",
        "",
        "| 维度 | 均分 |",
        "|---|---|",
    ]
    for d, v in summary["quality_scores"].items():
        lines.append(f"| {d} | {v if v is not None else '-'} |")
    lines += ["", "## 用例明细", ""]
    for r in results:
        m = r["metrics"]
        lines.append(f"### {r['id']}: {r['request'][:40]}")
        lines.append(f"- success: {r['success']}")
        lines.append(f"- 提取: {m['extraction']}")
        lines.append(f"- 约束: {m['plan_constraints']}  (recall={_rate(m['plan_constraints']['correct'], m['plan_constraints']['total'])}, precision={_rate(m['plan_constraints']['correct'], m['plan_constraints']['covered'])})")
        lines.append(f"- 工具命中: {m['tool_hits']}")
        lines.append(f"- 结构: {m['structure']}")
        if r.get("quality_scores"):
            lines.append(f"- 质量分: {r['quality_scores']}")
        if r["errors"]:
            lines.append(f"- errors: {r['errors']}")
        lines.append("")
    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser(description="活动策划系统质量评估")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 条用例（默认全部）")
    parser.add_argument("--judge", choices=["manual", "llm"], default="manual",
                        help="质量维度评分方式：manual 输出评分表人工填（默认）/ llm 用 GLM 自动打分")
    args = parser.parse_args()

    cases = load_test_cases()
    if args.limit > 0:
        cases = cases[: args.limit]

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = RESULTS_DIR / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    planner = ActivityPlanner()
    results: List[Dict] = []
    for case in cases:
        r = await run_case(planner, case, args.judge)
        results.append(r)
        with open(out_dir / f"{case['id']}.json", "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)

    summary = summarize(results)
    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    with open(out_dir / "report.md", "w", encoding="utf-8") as f:
        f.write(render_report(results, summary))

    print("\n" + "=" * 60)
    print("📊 评测完成，结果目录:", out_dir)
    print("=" * 60)
    print(f"  需求提取准确率: {summary['extraction_accuracy'] or '-'}")
    print(f"  方案约束召回率: {summary['constraint_recall'] or '-'}")
    print(f"  方案约束准确率: {summary['constraint_precision'] or '-'}")
    print(f"  工具真实命中率: {summary['tool_hit_rate'] or '-'}")
    print(f"  结构完整性:     {summary['structure_completeness'] or '-'}")
    if args.judge == "manual":
        print("\n💡 质量维度评分表见 report.md（manual 模式，请人工填写后统计）")
    else:
        print(f"  质量维度均分:   {summary['quality_scores']}")


if __name__ == "__main__":
    asyncio.run(main())
