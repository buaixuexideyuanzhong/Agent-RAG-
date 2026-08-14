"""
活动策划多智能体系统 - 单元测试
"""
import asyncio
import sys
from unittest.mock import Mock, AsyncMock

# 添加模拟响应
MOCK_VENUE_RESPONSE = """
## 场地推荐（按综合评分排序）

### 1. 北京国际会议中心
- **地址**: 北京朝阳区北辰东路8号
- **容纳人数**: 600人
- **价格**: 8万元（含半天使用）
- **设施**:
  * 专业音响系统
  * 大型LED显示屏
  * 灯光设备齐全
  * 同声传译设备
- **交通**: 地铁8号线直达，交通便利
- **推荐理由**: 容量充足，设备完善，适合大型年会

### 2. 北京国贸大酒店
- **地址**: 北京朝阳区建国门外大街1号
- **容纳人数**: 500人
- **价格**: 10万元（含半天+晚宴）
- **设施**:
  * 五星级宴会厅
  * 完善餐饮服务
  * 高端装饰风格
- **交通**: 国贸CBD核心区
- **推荐理由**: 高端大气，一站式服务

### 3. 国家会议中心
- **地址**: 北京朝阳区天辰东路7号
- **容纳人数**: 800人
- **价格**: 6万元（半天）
- **设施**:
  * 国际标准会场
  * 专业舞台
  * 360度环绕音效
- **交通**: 奥林匹克公园附近
- **推荐理由**: 性价比高，专业性强
"""

MOCK_SUPPLIER_RESPONSE = """
## 商家推荐

### 餐饮商家
1. **京味轩餐饮**
   - 服务: 中式酒席、茶歇
   - 报价: 人均150元
   - 评分: 4.8/5.0
   - 特色: 传统京菜，有企业年会经验

### 活动搭建公司
1. **星光搭建**
   - 服务: 舞台、背景板、氛围布置
   - 报价: 套餐价3万元
   - 案例: 100+家企业年会经验

### 设备租赁
1. **音视通设备**
   - 服务: 音响、灯光、LED屏全套
   - 报价: 日租5000元
   - 评价: 设备新、技术人员专业

### 摄影摄像
1. **印象纪实**
   - 服务: 双机位摄影+摄像
   - 报价: 4000元
   - 案例: 擅长企业活动记录
"""

MOCK_PROCESS_RESPONSE = """
## 流程参考和最佳实践

### 推荐案例

**案例1：某科技公司年会（500人）**
- 相似度评分: 95%
- 成功要素: 提前2周邀请、设置抽奖环节、准备伴手礼
- 经验教训: 签到流程需增加人手

**案例2：某金融公司年会（400人）**
- 相似度评分: 88%
- 成功要素: 精心设计的主题环节
- 经验教训: 音响设备需提前测试

### 标准流程模板
```
13:30-14:00  签到与入场
14:00-14:20  开场致辞
14:20-15:00  年度总结汇报
15:00-15:30  中场休息/茶歇
15:30-16:30  颁奖典礼
16:30-17:00  互动游戏/抽奖
17:00-18:00  领导总结
18:00-20:00  晚宴
```

### 关键成功要素
- 提前2-3周发送正式邀请
- 准备精美的伴手礼
- 设置有吸引力的抽奖环节
- 安排专业摄影记录精彩时刻
- 准备备选方案（如室外活动考虑天气）

### 避坑指南
- 签到流程拥堵 → 增加签到人员和通道
- 设备故障 → 提前调试，准备备用设备
- 时间控制 → 制定严格时间表，主持人把控节奏
"""


async def test_workflow_structure():
    """测试工作流结构"""
    print("=" * 60)
    print("测试 1: 工作流结构")
    print("=" * 60)

    try:
        from backend.agents.workflow import create_workflow

        workflow = create_workflow()
        info = workflow.get_graph_info()
        print("✅ 工作流结构创建成功\n")
        print(info)
        return True
    except Exception as e:
        print(f"❌ 工作流结构创建失败: {e}")
        return False


async def test_state_definition():
    """测试状态定义"""
    print("\n" + "=" * 60)
    print("测试 2: 状态定义")
    print("=" * 60)

    try:
        from backend.core.state import AgentState

        test_state: AgentState = {
            "user_request": "测试请求",
            "extracted_requirements": None,
            "venue_result": None,
            "supplier_result": None,
            "process_result": None,
            "final_plan": None,
            "messages": [],
            "errors": [],
        }

        print("✅ AgentState 定义正确")
        print(f"   用户请求: {test_state['user_request']}")
        return True
    except Exception as e:
        print(f"❌ AgentState 定义失败: {e}")
        return False


async def test_llm_client():
    """测试 LLM 客户端（需要真实 API Key）"""
    print("\n" + "=" * 60)
    print("测试 3: LLM 客户端")
    print("=" * 60)

    from backend.core.config import Config

    if not Config.LLM_API_KEY or Config.LLM_API_KEY == "":
        print("⏭️  跳过 LLM 测试（未配置 API Key）")
        return None

    try:
        from backend.agents.agents import LLMClient

        client = LLMClient()
        result = await client.chat(
            system_prompt="你是测试助手",
            user_message="请回复'测试成功'",
            max_tokens=100
        )

        if "测试成功" in result or "success" in result.lower():
            print("✅ LLM 客户端工作正常")
            print(f"   响应: {result[:50]}...")
            return True
        else:
            print("⚠️  LLM 响应不符合预期")
            return False

    except Exception as e:
        print(f"❌ LLM 客户端测试失败: {e}")
        return False


async def test_config():
    """测试配置加载"""
    print("\n" + "=" * 60)
    print("测试 4: 配置加载")
    print("=" * 60)

    try:
        from backend.core.config import (
            Config,
            PLANNER_SYSTEM_PROMPT,
            VENUE_SEARCHER_SYSTEM_PROMPT,
            SUPPLIER_SEARCHER_SYSTEM_PROMPT,
            PROCESS_SEARCHER_SYSTEM_PROMPT,
        )

        print("✅ 配置加载成功")
        print(f"   Planner 模型: {Config.PLANNER_MODEL}")
        print(f"   Searcher 模型: {Config.SEARCHER_MODEL}")
        print(f"   Planner Prompt 长度: {len(PLANNER_SYSTEM_PROMPT)} 字符")
        print(f"   Venue Prompt 长度: {len(VENUE_SEARCHER_SYSTEM_PROMPT)} 字符")
        print(f"   Supplier Prompt 长度: {len(SUPPLIER_SEARCHER_SYSTEM_PROMPT)} 字符")
        print(f"   Process Prompt 长度: {len(PROCESS_SEARCHER_SYSTEM_PROMPT)} 字符")

        api_key_status = "已设置" if Config.LLM_API_KEY else "未设置"
        print(f"   API Key: {api_key_status}")

        return True
    except Exception as e:
        print(f"❌ 配置加载失败: {e}")
        return False


async def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 70)
    print("🧪 活动策划多智能体系统 - 单元测试")
    print("=" * 70)

    results = []

    # 测试配置
    results.append(await test_config())

    # 测试状态定义
    results.append(await test_state_definition())

    # 测试工作流结构
    results.append(await test_workflow_structure())

    # 测试 LLM 客户端
    llm_result = await test_llm_client()
    if llm_result is not None:
        results.append(llm_result)

    # 汇总结果
    print("\n" + "=" * 70)
    print("📊 测试结果汇总")
    print("=" * 70)

    passed = sum(1 for r in results if r is True)
    failed = sum(1 for r in results if r is False)
    skipped = sum(1 for r in results if r is None)
    total = len(results)

    print(f"  ✅ 通过: {passed}/{total}")
    print(f"  ❌ 失败: {failed}/{total}")
    print(f"  ⏭️  跳过: {skipped}/{total}")

    if failed == 0 and skipped > 0:
        print("\n🎉 核心测试通过！配置 API Key 后可运行完整测试。")
    elif failed == 0:
        print("\n🎉 所有测试通过！")
    else:
        print("\n⚠️  有测试失败，请检查配置和依赖。")


if __name__ == "__main__":
    asyncio.run(run_all_tests())