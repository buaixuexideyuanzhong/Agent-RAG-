"""
活动策划多智能体系统 - 主程序入口
基于 LangGraph + 智谱 AI GLM-4.7 的多智能体协作架构
"""
import asyncio
import argparse
import logging
from typing import Optional

from ..core.config import Config, EXAMPLE_REQUESTS
from ..core.state import AgentState
from ..agents.workflow import create_workflow, WORKFLOW_STRUCTURE

# 配置日志
logging.basicConfig(
    level=Config.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ActivityPlanner:
    """活动策划多智能体系统主类"""

    def __init__(self, enable_persistence: bool = False):
        """
        初始化活动策划系统

        Args:
            enable_persistence: 是否启用状态持久化（支持多轮对话）
        """
        self.workflow = create_workflow(enable_persistence=enable_persistence)
        logger.info("活动策划系统初始化完成")

    async def plan(
        self,
        user_request: str,
        stream_queue: Optional["asyncio.Queue"] = None,
        console_output: Optional[bool] = None,
    ) -> dict:
        """
        根据用户需求生成活动策划方案

        Args:
            user_request: 用户的自然语言需求描述
            stream_queue: （后端 API SSE 专用）方案 chunk 队列，None 表示非流式
            console_output: 是否打印方案到控制台；None 走 Config.ENABLE_STREAM_OUTPUT（CLI 默认打印）

        Returns:
            包含策划结果和元信息的字典
        """
        logger.info(f"收到新的策划请求: {user_request[:50]}...")

        # 创建初始状态
        initial_state: AgentState = {
            "user_request": user_request,
            "extracted_requirements": None,
            "venue_result": None,
            "supplier_result": None,
            "process_result": None,
            "final_plan": None,
            "plan_streamed": False,
            "messages": [],
            "errors": [],
        }
        # 仅当显式传入时才写入状态，CLI 调用保持原有行为
        if stream_queue is not None:
            initial_state["stream_queue"] = stream_queue
        if console_output is not None:
            initial_state["console_output"] = console_output

        try:
            # 执行工作流
            final_state = await self.workflow.compiled_app.ainvoke(initial_state)

            # 返回结果
            return {
                "success": True,
                "plan": final_state.get("final_plan"),
                "plan_streamed": final_state.get("plan_streamed", False),
                "requirements": final_state.get("extracted_requirements"),
                "venue_info": final_state.get("venue_result"),
                "supplier_info": final_state.get("supplier_result"),
                "process_info": final_state.get("process_result"),
                "messages": final_state.get("messages", []),
                "errors": final_state.get("errors", []),
            }

        except Exception as e:
            logger.error(f"策划失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "plan": None,
            }

    def get_workflow_info(self) -> str:
        """获取工作流信息"""
        return self.workflow.get_graph_info()

    def visualize_workflow(self, output_file: str = "workflow_graph.png"):
        """可视化工作流图"""
        self.workflow.visualize_graph(output_file)


async def _save_last_case(result: dict) -> Optional[str]:
    """把上次生成的方案存入案例知识库，返回 case_id"""
    from ..storage.rag_knowledgebase import CaseStore

    req = result.get("requirements") or {}
    meta = {
        "activity_type": req.get("activity_type"),
        "attendee_count": req.get("attendee_count"),
        "budget": req.get("budget"),
        "city": req.get("city"),
        "theme": req.get("theme"),
    }
    return await CaseStore.add_case(result.get("plan") or "", meta)


async def interactive_mode():
    """交互式对话模式"""
    from ..storage.rag_knowledgebase import CaseStore

    print("\n" + "=" * 70)
    print("🎉 活动策划多智能体系统 - 交互式对话模式")
    print("=" * 70)
    print("\n📋 工作流架构:")
    print("  需求提取 → [并行] 场地搜索 | 商家搜索 | 流程参考 → 方案整合")
    print("\n💡 输入示例:")
    for i, example in enumerate(EXAMPLE_REQUESTS[:2], 1):
        print(f"  {i}. {example}")
    print("\n📌 命令:")
    print("  save           保存上一次成功方案到案例知识库")
    print("  import <文件>  批量导入案例（json / txt / md）")
    print("  list           查看知识库案例列表")
    print("  quit / exit    退出\n")

    planner = ActivityPlanner()
    last_result: Optional[dict] = None

    while True:
        try:
            # 获取用户输入
            user_input = input("🎯 请描述您的活动需求: ").strip()

            if not user_input:
                continue

            # 企业级：用户输入校验（长度/空值）
            from ..core.models import UserRequest
            from pydantic import ValidationError
            try:
                user_input = UserRequest(text=user_input).text
            except ValidationError:
                print("⚠️ 输入无效：需求描述不能为空且长度不超过 2000 字\n")
                continue

            parts = user_input.lower().split()
            cmd = parts[0]

            if cmd in ['quit', 'exit', 'q']:
                print("\n👋 感谢使用，再见！")
                break

            # ===== 命令处理 =====
            if cmd == 'save':
                if last_result and last_result.get("success"):
                    print("\n💾 正在保存案例到知识库...")
                    cid = await _save_last_case(last_result)
                    if cid:
                        print(f"✅ 案例已存入知识库: {cid[:8]}...")
                    else:
                        print("⚠️ 保存失败（MySQL/Milvus 不可用，或基础设施未启动）")
                else:
                    print("⚠️ 还没有可保存的方案，请先策划一次。")
                print()
                continue

            if cmd == 'import':
                if len(parts) < 2:
                    print("用法: import <文件路径>\n")
                    continue
                print(f"\n📥 正在导入案例: {parts[1]}")
                stats = await CaseStore.import_from_file(parts[1])
                print(f"导入完成: 成功 {stats.get('imported')} 条, 失败 {stats.get('failed')} 条")
                if stats.get("error"):
                    print(f"⚠️ {stats['error']}")
                print()
                continue

            if cmd == 'list':
                cases = await CaseStore.list_cases()
                print(f"\n📚 知识库共 {len(cases)} 条案例:")
                for c in cases[:20]:
                    print(f"  - {c.get('activity_type') or '未知类型'} | "
                          f"{c.get('city') or '未知城市'} | "
                          f"{c.get('attendee_count') or '?'}人 | "
                          f"id:{c['id'][:8]}...")
                print()
                continue

            if cmd == 'help':
                print("命令: save / import <文件> / list / quit")
                print()
                continue

            # ===== 正常策划流程 =====
            print("\n⏳ 正在为您策划活动，请稍候...\n")

            # 执行策划
            result = await planner.plan(user_input)

            # 显示结果
            if result["success"]:
                print("✅ 策划完成！\n")
                print("-" * 70)
                print("【执行日志】")
                for msg in result["messages"]:
                    print(f"  ✓ {msg}")

                if result["errors"]:
                    print("\n【注意事项】")
                    for error in result["errors"]:
                        print(f"  ⚠ {error}")

                if result.get("plan_streamed"):
                    # 方案已在生成时实时输出，此处不再重复打印
                    print("\n💡 完整方案已在上方实时输出。")
                else:
                    print("\n【活动策划方案】")
                    print("-" * 70)
                    print(result["plan"])
                    print("-" * 70)

                # 记录上次方案，供 save 命令使用
                last_result = result
                print("\n💡 输入 'save' 可把该方案存入案例知识库")
            else:
                print(f"❌ 策划失败: {result.get('error')}")

            print("\n")

        except KeyboardInterrupt:
            print("\n\n👋 程序已终止")
            break
        except Exception as e:
            logger.error(f"发生错误: {str(e)}")
            print(f"\n❌ 发生错误: {str(e)}")


async def single_request_mode(request: str):
    """单次请求模式"""
    print(f"\n🎯 收到策划请求: {request}")
    print("\n⏳ 正在为您策划活动，请稍候...\n")

    planner = ActivityPlanner()
    result = await planner.plan(request)

    if result["success"]:
        print("\n✅ 策划完成！\n")
        print("-" * 70)
        print("【执行日志】")
        for msg in result["messages"]:
            print(f"  ✓ {msg}")

        if result["errors"]:
            print("\n【注意事项】")
            for error in result["errors"]:
                print(f"  ⚠ {error}")

        if result.get("plan_streamed"):
            print("\n💡 完整方案已在上方实时输出。")
        else:
            print("\n【活动策划方案】")
            print("-" * 70)
            print(result["plan"])
            print("-" * 70)

        return result
    else:
        print(f"\n❌ 策划失败: {result.get('error')}")
        return None


def print_banner():
    """打印欢迎横幅"""
    banner = """
╔════════════════════════════════════════════════════════════════╗
║                                                                  ║
║      🎊 活动策划多智能体系统 🎊                                  ║
║      Event Planning Multi-Agent System                          ║
║                                                                  ║
║      基于 LangGraph + 智谱 AI GLM-4.7                            ║
║                                                                  ║
║      架构: 3个搜索Agent + 1个PlannerAgent                       ║
║      - 场地搜索 Agent                                           ║
║      - 商家搜索 Agent                                           ║
║      - 流程参考搜索 Agent                                        ║
║      - Planner 整合 Agent                                       ║
║                                                                  ║
╚════════════════════════════════════════════════════════════════╝
    """
    print(banner)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="活动策划多智能体系统 - 基于 LangGraph 和智谱 AI"
    )
    parser.add_argument(
        "--mode",
        choices=["interactive", "single", "example"],
        default="interactive",
        help="运行模式: interactive(交互式), single(单次请求), example(示例)"
    )
    parser.add_argument(
        "--request",
        type=str,
        help="单次请求模式下的需求描述"
    )
    parser.add_argument(
        "--example-index",
        type=int,
        choices=range(1, len(EXAMPLE_REQUESTS) + 1),
        help="使用预设示例的索引（1-4）"
    )
    parser.add_argument(
        "--visualize",
        action="store_true",
        help="生成工作流可视化图"
    )
    parser.add_argument(
        "--workflow-info",
        action="store_true",
        help="显示工作流详细信息"
    )

    args = parser.parse_args()

    # 验证配置
    if not Config.validate():
        print("\n⚠️  警告: LLM_API_KEY 未设置")
        print("请设置环境变量: export LLM_API_KEY=your_api_key")
        print("或在 config.py 中直接设置 LLM_API_KEY\n")
        return

    # 打印横幅
    print_banner()

    # 显示工作流信息
    if args.workflow_info:
        print("\n" + WORKFLOW_STRUCTURE)
        planner = ActivityPlanner()
        print("\n" + planner.get_workflow_info())
        return

    # 生成可视化图
    if args.visualize:
        print("\n📊 生成工作流可视化图...")
        planner = ActivityPlanner()
        planner.visualize_workflow("workflow_graph.png")
        print("✅ 图已保存到 workflow_graph.png\n")
        return

    # 根据模式执行
    if args.mode == "interactive":
        asyncio.run(_run_and_cleanup(interactive_mode()))

    elif args.mode == "single":
        if args.request:
            asyncio.run(_run_and_cleanup(single_request_mode(args.request)))
        else:
            print("❌ 单次请求模式需要 --request 参数")

    elif args.mode == "example":
        index = args.example_index or 1
        request = EXAMPLE_REQUESTS[index - 1]
        print(f"\n📝 使用示例 {index}:")
        print(f"   {request}\n")
        asyncio.run(_run_and_cleanup(single_request_mode(request)))


async def _run_and_cleanup(coro):
    """执行入口并统一关闭连接池（Redis/MySQL），避免事件循环关闭时告警"""
    try:
        await coro
    finally:
        from ..storage.cache import RedisCache
        from ..storage.database import CasesDB
        await RedisCache.close()
        await CasesDB.close()


if __name__ == "__main__":
    main()