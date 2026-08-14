"""
LangGraph 工作流构建
定义多智能体的执行流程图
"""
import logging
from typing import Optional

try:
    from langgraph.graph import StateGraph, END
    from langgraph.checkpoint.memory import MemorySaver
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False

from ..core.config import Config
from ..core.state import AgentState
from .agents import (
    requirement_extractor_node,
    venue_searcher_node,
    supplier_searcher_node,
    process_searcher_node,
    integrator_node,
    log_state
)

# 配置日志
logging.basicConfig(
    level=Config.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ActivityPlanningWorkflow:
    """活动策划多智能体工作流"""

    def __init__(self, enable_persistence: bool = False):
        """
        初始化工作流

        Args:
            enable_persistence: 是否启用持久化（用于多轮对话）
        """
        if not LANGGRAPH_AVAILABLE:
            raise ImportError(
                "请安装 langgraph 库: pip install langgraph\n"
                "同时需要安装: pip install langchain langchain-core"
            )

        self.workflow = None
        self.compiled_app = None
        self.enable_persistence = enable_persistence
        self._build_workflow()

    def _build_workflow(self):
        """构建 LangGraph 工作流图"""
        logger.info("开始构建 LangGraph 工作流...")

        # 创建状态图
        self.workflow = StateGraph(AgentState)

        # 添加节点
        self.workflow.add_node("requirement_extractor", requirement_extractor_node)
        self.workflow.add_node("venue_searcher", venue_searcher_node)
        self.workflow.add_node("supplier_searcher", supplier_searcher_node)
        self.workflow.add_node("process_searcher", process_searcher_node)
        self.workflow.add_node("integrator", integrator_node)

        # 设置入口点
        self.workflow.set_entry_point("requirement_extractor")

        # 定义边（执行流程）
        # 从需求提取节点，并行分发到三个搜索 Agent
        self.workflow.add_edge("requirement_extractor", "venue_searcher")
        self.workflow.add_edge("requirement_extractor", "supplier_searcher")
        self.workflow.add_edge("requirement_extractor", "process_searcher")

        # 三个搜索 Agent 完成后，都汇聚到整合节点
        self.workflow.add_edge(["venue_searcher", "supplier_searcher", "process_searcher"], "integrator")

        # 整合完成后结束
        self.workflow.add_edge("integrator", END)

        # 编译图
        if self.enable_persistence:
            checkpointer = MemorySaver()
            self.compiled_app = self.workflow.compile(checkpointer=checkpointer)
        else:
            self.compiled_app = self.workflow.compile()

        logger.info("LangGraph 工作流构建完成")

    def get_graph_info(self) -> str:
        """获取工作流图信息"""
        if self.workflow is None:
            return "工作流未初始化"

        return f"""
工作流节点:
- requirement_extractor: 需求提取节点
- venue_searcher: 场地搜索节点
- supplier_searcher: 商家搜索节点
- process_searcher: 流程参考搜索节点
- integrator: 方案整合节点

执行流程:
用户请求 → 需求提取 → [并行] 场地/商家/流程搜索 → 整合方案 → 完成
"""

    def visualize_graph(self, output_file: str = "workflow_graph.png"):
        """
        可视化工作流图

        Args:
            output_file: 输出文件路径
        """
        try:
            from IPython.display import Image, display

            # 获取图的 Mermaid 表示
            mermaid_graph = self.workflow.get_graph().draw_mermaid_png()

            with open(output_file, "wb") as f:
                f.write(mermaid_graph)

            logger.info(f"工作流图已保存到: {output_file}")

            # 如果在 Jupyter 环境中，可以直接显示
            try:
                display(Image(mermaid_graph))
            except:
                pass

        except Exception as e:
            logger.warning(f"无法可视化工作流图: {e}")


# 工作流图的结构说明
WORKFLOW_STRUCTURE = """
┌─────────────────────────────────────────────────────────────┐
│                      用户界面层                               │
│              (Web 前端 / 聊天界面 / API)                      │
└──────────────────┬──────────────────────────────────────────┘
                   │ 用户自然语言需求
                   │ "帮我策划一个500人的公司年会，预算20万，地点在北京"
┌──────────────────▼──────────────────────────────────────────┐
│      requirement_extractor (需求提取节点)                     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  职责：从自然语言中提取结构化需求信息                 │  │
│  │  模型：GLM-4.7                                        │  │
│  └──────┬─────────────┬───────────────┬─────────────────┘  │
│         │ 并行调度    │               │                    │
┌────────▼────┐  ┌──────▼──────────┐  ┌─▼────────────────┐  │
│ venue_search│  │ supplier_search │  │  process_search  │  │
│   (场地)    │  │    (商家)       │  │   (流程参考)     │  │
│            │  │                │  │                  │  │
│ • 酒店场地 │  │ • 餐饮商家     │  │ • 活动案例       │  │
│ • 会议中心 │  │ • 搭建公司     │  │ • 流程模板       │  │
│ • 展馆     │  │ • 设备租赁     │  │ • 成功要素       │  │
│ • 价格查询 │  │ • 价格查询     │  │ • 避坑指南       │  │
│            │  │                │  │                  │  │
│ 模型：GLM  │  │ 模型：GLM-4.7  │  │ 模型：GLM-4.7    │  │
│ -4.7       │  │                │  │                  │  │
└────┬───────┘  └──────┬──────────┘  └────────┬─────────┘  │
     │                 │                      │             │
     └─────────────────┼──────────────────────┘             │
                       │ 结果汇总                            │
┌──────────────────────▼─────────────────────────────────────┐
│          integrator (方案整合节点)                          │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  • 合并场地、商家、流程参考三类信息                  │  │
│  │  • 生成完整活动方案（流程+资源+预算+时间表）        │  │
│  │  • 优化资源配置，控制预算                            │  │
│  │  • 输出可执行的策划文档                              │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────┬──────────────────────────────────────────┘
                   │
              输出完整方案
"""


def create_workflow(enable_persistence: bool = False) -> ActivityPlanningWorkflow:
    """
    创建活动策划工作流实例

    Args:
        enable_persistence: 是否启用持久化

    Returns:
        工作流实例
    """
    return ActivityPlanningWorkflow(enable_persistence=enable_persistence)


# 预设示例
EXAMPLE_REQUESTS = [
    "帮我策划一个500人的公司年会，预算20万，地点在北京朝阳，时间是下个月中旬",
    "策划一个200人的产品发布会，预算50万，上海浦东，需要高端场地",
    "组织一场100人的客户答谢会，预算10万，广州天河，注重用户体验",
    "安排一个300人的培训会，预算15万，深圳南山，需要完善的设备",
]


def run_example():
    """运行示例（独立测试用）"""
    import asyncio

    async def main():
        print("=" * 60)
        print("活动策划多智能体系统 - 示例运行")
        print("=" * 60)

        # 验证配置
        if not Config.validate():
            print("配置验证失败，请检查 API Key")
            return

        # 创建工作流
        workflow = create_workflow()
        print("\n" + workflow.get_graph_info())

        # 选择示例请求
        print("\n可选示例:")
        for i, req in enumerate(EXAMPLE_REQUESTS, 1):
            print(f"{i}. {req}")

        # 默认使用第一个示例
        user_input = EXAMPLE_REQUESTS[0]
        print(f"\n使用示例: {user_input}")

        # 创建初始状态
        initial_state: AgentState = {
            "user_request": user_input,
            "extracted_requirements": None,
            "venue_result": None,
            "supplier_result": None,
            "process_result": None,
            "final_plan": None,
            "plan_streamed": False,
            "messages": [],
            "errors": [],
        }

        print("\n" + "-" * 60)
        print("开始执行工作流...")
        print("-" * 60)

        # 执行工作流
        try:
            final_state = await workflow.compiled_app.ainvoke(initial_state)

            # 打印结果
            print("\n" + "=" * 60)
            print("工作流执行完成")
            print("=" * 60)

            print("\n【执行日志】")
            for msg in final_state["messages"]:
                print(f"  ✓ {msg}")

            if final_state["errors"]:
                print("\n【错误信息】")
                for error in final_state["errors"]:
                    print(f"  ✗ {error}")

            print("\n【最终策划方案】")
            print("-" * 60)
            if final_state.get("plan_streamed"):
                print("（方案已在上方实时输出）")
            else:
                print(final_state.get("final_plan", "未生成方案"))
            print("-" * 60)

        except Exception as e:
            print(f"\n执行失败: {str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            from ..storage.cache import RedisCache
            from ..storage.database import CasesDB
            await RedisCache.close()
            await CasesDB.close()

    asyncio.run(main())


if __name__ == "__main__":
    run_example()