# 活动策划智能体 - 技术方案与实施说明

## 一、项目概述

### 1.1 项目目标
活动策划智能体旨在通过 AI 技术，自动化地协助用户完成活动策划的全流程，包括需求分析、方案生成、资源配置、时间规划、预算估算等核心环节。

### 1.2 核心价值
- 提升活动策划效率，降低人工成本
- 标准化活动策划流程，减少遗漏
- 智能化推荐方案，提升策划质量
- 可视化管理，便于协作和追踪

---

## 二、技术栈选择

### 2.1 核心技术

| 技术类别 | 推荐技术 | 说明 |
|---------|---------|------|
| LLM 模型 | 智谱 AI GLM-4.7 (Zhipu AI API) | 国产大模型，强大的中文理解和生成能力，支持工具调用和复杂推理 |
| 多智能体框架 | LangGraph / AutoGen / CrewAI | 实现多智能体协作编排 |
| 向量数据库 | Milvus / Qdrant / Pinecone | 存储活动案例、知识库，支持语义检索 |
| 开发框架 | Python + LangChain | 便于构建 RAG 系统和智能体流程 |
| Web 框架 | FastAPI / Flask | 提供 RESTful API 服务 |
| 前端框架 | React / Vue.js | 构建用户交互界面 |
| 数据库 | PostgreSQL / MySQL | 存储用户数据、活动历史记录 |
| 消息队列 | Redis / RabbitMQ | 处理异步任务和长流程 |

### 2.2 可选增强技术

- **知识图谱**: Neo4j - 存储活动要素之间的关联关系
- **知识库管理**: LangSmith / Arize Phoenix - 追踪和优化智能体行为
- **A/B 测试框架**: Optuna - 优化提示词和参数
- **容器化**: Docker + Kubernetes - 便于部署和扩展

### 2.3 智谱 AI GLM-4.7 特性

| 特性 | 描述 |
|-----|------|
| 模型版本 | glm-4.7 (最新 GLM-4 系列) |
| 上下文长度 | 最高支持 128K tokens |
| 工具调用 | 原生支持 Function Calling |
| 多轮对话 | 优秀的对话历史管理能力 |
| 中文理解 | 专为中文优化，理解国内活动场景 |
| API 文档 | https://open.bigmodel.cn/dev/api |

---

## 三、系统架构设计

### 3.1 多智能体架构

采用 **3 个搜索 Agent + 1 个 Planner Agent** 的多智能体协作架构。

**工作流程**：
1. 用户输入自然语言需求
2. 系统并行检索三类信息（场地/商家/流程参考）
3. Planner 汇总生成可执行的完整活动方案

```
┌─────────────────────────────────────────────────────────────┐
│                      用户界面层                              │
│              (Web 前端 / 聊天界面 / API)                     │
└──────────────────┬──────────────────────────────────────────┘
                   │ 用户自然语言需求
                   │ "帮我策划一个500人的公司年会，预算20万，地点在北京"
┌──────────────────▼──────────────────────────────────────────┐
│              Planner Agent (主控智能体)                       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  职责：需求提取、任务分发、结果整合、方案生成        │  │
│  │  模型：GLM-4.7                                        │  │
│  └──────┬─────────────┬───────────────┬─────────────────┘  │
│         │ 并行调度    │               │                    │
┌────────▼────┐  ┌──────▼──────────┐  ┌─▼────────────────┐  │
│   Search    │  │     Search      │  │     Search       │  │
│   Agent 1   │  │     Agent 2     │  │     Agent 3      │  │
│ 【场地搜索】│  │  【商家搜索】   │  │ 【流程参考搜索】 │  │
│            │  │                │  │                  │  │
│ • 酒店场地 │  │ • 餐饮商家     │  │ • 活动案例       │  │
│ • 会议中心 │  │ • 搭建公司     │  │ • 流程模板       │  │
│ • 展馆     │  │ • 设备租赁     │  │ • 成功要素       │  │
│ • 公共空间 │  │ • 礼品定制     │  │ • 经验教训       │  │
│            │  │ • 摄影摄像     │  │ • 行业标准       │  │
│ • 价格查询 │  │ • 价格查询     │  │ • 避坑指南       │  │
│ • 可用性   │  │ • 评价查询     │  │                  │  │
│            │  │                │  │                  │  │
│ 模型：GLM  │  │ 模型：GLM-4.7  │  │ 模型：GLM-4.7    │  │
│ -4.7       │  │                │  │                  │  │
└────┬───────┘  └──────┬──────────┘  └────────┬─────────┘  │
     │                 │                      │             │
     └─────────────────┼──────────────────────┘             │
                       │ 结果汇总                            │
┌──────────────────────▼─────────────────────────────────────┐
│              Planner Agent - 结果整合与方案生成             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  • 合并场地、商家、流程参考三类信息                  │  │
│  │  • 生成完整活动方案（流程+资源+预算+时间表）        │  │
│  │  • 优化资源配置，控制预算                            │  │
│  │  • 输出可执行的策划文档                              │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────┬──────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────┐
│                      共享数据层                               │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │ 向量数据库 │  │关系数据库  │  │ 外部 API   │            │
│  │(活动案例)  │  │(场地/商家) │  │(天气/地图) │            │
│  └────────────┘  └────────────┘  └────────────┘            │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 智能体详细设计

#### 3.2.1 Planner Agent（主控智能体）

**核心职责**：
- **需求提取**: 从用户自然语言中提取结构化的活动需求
- **任务分发**: 并行调用 3 个搜索 Agent 获取所需信息
- **结果整合**: 汇总场地、商家、流程参考三类信息
- **方案生成**: 生成完整、可执行的活动策划方案
- **对话管理**: 处理用户反馈和调整请求

**工作流程**：
```
1. 接收用户自然语言输入
2. 提取关键需求信息（活动类型、人数、预算、时间、地点等）
3. 并行调用 3 个搜索 Agent
4. 等待并收集搜索结果
5. 整合信息，生成完整方案
6. 向用户展示方案
7. 处理用户的修改请求
```

**System Prompt**：
```python
PLANNER_SYSTEM_PROMPT = """
你是一个专业的活动策划主控智能体，负责协调多个搜索智能体完成活动策划任务。

你的职责：
1. 理解用户的活动需求，提取关键信息（活动类型、规模、时间、地点、预算等）
2. 协调三个搜索智能体并行工作：
   - 场地搜索：获取合适的场地信息
   - 商家搜索：获取供应商和商家信息
   - 流程参考搜索：获取活动案例和流程模板
3. 整合三类搜索结果，生成完整、可执行的活动策划方案
4. 处理用户的反馈和调整请求

方案要求：
- 结构清晰：包含活动流程、时间表、资源配置、预算明细
- 可执行：每个环节都有具体的负责人和时间节点
- 符合约束：严格控制在用户预算范围内
- 逻辑连贯：场地、商家、流程之间相互匹配

输出格式：
- 活动概述（主题、目标、时间、地点）
- 详细流程安排（时间轴）
- 场地配置方案
- 商家资源配置
- 预算明细表
- 任务清单和负责人
"""
```

#### 3.2.2 Search Agent 1 - 场地搜索

**核心职责**：
- 根据活动需求搜索合适的活动场地
- 获取场地的价格、设施、位置、可用性等信息
- 按用户偏好和预算进行排序推荐

**搜索内容**：
- 酒店宴会厅
- 会议中心
- 展馆
- 公共活动空间
- 特色场地（美术馆、创意园等）

**工具集**：
- `venue_searcher`: 从数据库或第三方平台搜索场地
- `price_checker`: 查询场地价格
- `availability_checker`: 检查场地可用性
- `map_api`: 获取场地位置和交通信息

**System Prompt**：
```python
VENUE_SEARCHER_SYSTEM_PROMPT = """
你是活动场地搜索专家，负责根据活动需求搜索合适的场地。

你的职责：
1. 根据活动类型、人数、预算、地点偏好搜索场地
2. 获取场地的详细信息：价格、容量、设施、位置
3. 检查场地在指定时间的可用性
4. 按综合评分（价格、位置、设施、口碑）推荐场地

搜索维度：
- 容量：必须满足或超过活动人数
- 价格：在预算范围内
- 位置：交通便利，符合城市/区域偏好
- 设施：根据活动需求匹配（餐饮、投影、音响等）
- 口碑：优先选择评价好的场地

输出格式：
- 场地名称和基本信息
- 容量和价格
- 地址和交通信息
- 设施清单
- 可用时间
- 推荐理由
"""
```

#### 3.2.3 Search Agent 2 - 商家搜索

**核心职责**：
- 搜索活动所需的各类商家和供应商
- 获取商家的服务内容、价格、评价等信息
- 推荐优质商家资源

**搜索内容**：
- 餐饮商家（酒席、茶歇）
- 活动搭建公司（舞台、背景板）
- 设备租赁商（音响、灯光、LED屏）
- 礼品定制商
- 摄影摄像服务
- 主持人和演艺人员
- 花艺布置

**工具集**：
- `supplier_searcher`: 搜索供应商信息
- `price_inquiry`: 询价
- `rating_checker`: 查询商家评价
- `portfolio_viewer`: 查看商家作品集

**System Prompt**：
```python
SUPPLIER_SEARCHER_SYSTEM_PROMPT = """
你是活动商家搜索专家，负责搜索活动所需的各类商家和供应商。

你的职责：
1. 根据活动需求搜索相关商家（餐饮、搭建、设备、礼品等）
2. 获取商家的服务内容、价格、评价
3. 查看商家的作品集和案例
4. 推荐性价比高、口碑好的商家

搜索维度：
- 服务类型：匹配活动需求
- 价格：在预算范围内
- 口碑：优先选择高评分商家
- 经验：有相关活动经验
- 响应速度：沟通及时

输出格式：
- 商家名称和基本信息
- 服务内容和报价
- 用户评价和评分
- 相关案例和作品
- 联系方式
- 推荐理由
"""
```

#### 3.2.4 Search Agent 3 - 流程参考搜索

**核心职责**：
- 检索相似的活动案例
- 提取活动流程模板
- 总结成功要素和经验教训
- 提供行业标准和最佳实践

**搜索内容**：
- 活动案例（年会、发布会、培训会等）
- 流程模板（签到、开场、核心环节、晚宴等）
- 成功要素分析
- 经验教训和避坑指南
- 行业标准和规范

**工具集**：
- `case_retriever`: 从向量数据库检索相似案例
- `template_matcher`: 匹配流程模板
- `success_analyzer`: 分析成功要素
- `lesson_summarizer`: 总结经验教训

**System Prompt**：
```python
PROCESS_SEARCHER_SYSTEM_PROMPT = """
你是活动流程参考搜索专家，负责检索相似活动案例并提供流程模板。

你的职责：
1. 根据活动类型和场景检索相似案例
2. 提取可复用的流程模板
3. 总结成功的关键要素
4. 整理经验教训和避坑指南

检索维度：
- 活动类型相似度（年会、发布会、培训会等）
- 规模相似度（人数、预算范围）
- 行业相似度（科技、金融、教育等）
- 场景相似度（庆祝、宣传、培训等）

输出格式：
- 推荐案例列表（包含相似度评分）
- 标准流程模板
- 关键成功要素
- 常见问题和避坑指南
- 行业标准和最佳实践
"""
```

### 3.3 智能体协作示例

**用户输入**：
> "帮我策划一个500人的公司年会，预算20万，地点在北京朝阳，时间是下个月中旬"

**协作流程**：
```
Step 1: Planner 提取需求
{
  "activity_type": "公司年会",
  "attendee_count": 500,
  "budget": 200000,
  "location": "北京朝阳区",
  "time": "下个月中旬"
}

Step 2: Planner 并行调用 3 个搜索 Agent

Search Agent 1（场地搜索）返回：
- 酒店A：朝阳区，容纳600人，价格8万，档期可用
- 会议中心B：朝阳区，容纳800人，价格6万，档期可用
- 特色场地C：朝阳区创意园，容纳500人，价格10万，档期可用

Search Agent 2（商家搜索）返回：
- 餐饮商家1：中式酒席，人均150元，评分4.8
- 搭建公司2：年会布置，套餐价3万，有成功案例
- 设备租赁3：音响灯光LED屏全套，日租5000元
- 摄影摄像4：双机位，4000元

Search Agent 3（流程参考搜索）返回：
- 案例1：科技公司年会500人，流程参考...
- 案例2：金融公司年会300人，流程参考...
- 流程模板：签到→开场→颁奖→晚宴→抽奖
- 成功要素：提前2周邀请、设置抽奖、准备伴手礼

Step 3: Planner 整合并生成方案
- 选定场地：会议中心B（性价比高）
- 选定商家：餐饮1+搭建2+设备3+摄像4
- 设计流程：基于模板个性化调整
- 预算核算：6万+7.5万+3万+0.5万+0.4万 = 17.4万（在预算内）

Step 4: 输出完整策划文档
```

### 3.4 技术实现

#### 3.4.1 智谱 API 基础调用

```python
from zhipuai import ZhipuAI

# 初始化客户端
client = ZhipuAI(api_key="your-zhipu-api-key")

# 基础对话示例
response = client.chat.completions.create(
    model="glm-4.7",  # 使用 GLM-4.7 模型
    messages=[
        {
            "role": "system",
            "content": "你是一个专业的活动策划助手。"
        },
        {
            "role": "user",
            "content": "帮我策划一个500人的公司年会"
        }
    ],
    temperature=0.7,
    max_tokens=4096,
)

print(response.choices[0].message.content)
```

#### 3.4.2 并行调用多个 Agent

```python
import asyncio
from zhipuai import ZhipuAI

# 初始化各 Agent
planner_client = ZhipuAI(api_key="your-zhipu-api-key")
venue_client = ZhipuAI(api_key="your-zhipu-api-key")
supplier_client = ZhipuAI(api_key="your-zhipu-api-key")
process_client = ZhipuAI(api_key="your-zhipu-api-key")

async def call_search_agent(client, system_prompt, user_message):
    """异步调用搜索 Agent"""
    response = client.chat.completions.create(
        model="glm-4.7",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        temperature=0.5,
        max_tokens=2048,
    )
    return response.choices[0].message.content

async def search_parallel(requirement):
    """并行调用三个搜索 Agent"""
    tasks = [
        call_search_agent(
            venue_client,
            VENUE_SEARCHER_SYSTEM_PROMPT,
            f"搜索场地：{requirement}"
        ),
        call_search_agent(
            supplier_client,
            SUPPLIER_SEARCHER_SYSTEM_PROMPT,
            f"搜索商家：{requirement}"
        ),
        call_search_agent(
            process_client,
            PROCESS_SEARCHER_SYSTEM_PROMPT,
            f"搜索流程参考：{requirement}"
        )
    ]
    
    # 等待所有搜索完成
    venue_result, supplier_result, process_result = await asyncio.gather(*tasks)
    
    return {
        "venue": venue_result,
        "supplier": supplier_result,
        "process": process_result
    }

# 使用示例
import asyncio

async def main():
    user_requirement = "500人公司年会，预算20万，北京朝阳区，下个月中旬"
    
    # 并行搜索
    search_results = await search_parallel(user_requirement)
    
    # 整合结果
    integration_prompt = f"""
    根据以下三类搜索结果，生成完整的活动策划方案：
    
    【场地搜索结果】
    {search_results['venue']}
    
    【商家搜索结果】
    {search_results['supplier']}
    
    【流程参考搜索结果】
    {search_results['process']}
    
    用户需求：{user_requirement}
    
    请生成完整的策划方案，控制在预算范围内。
    """
    
    # Planner 整合生成方案
    final_response = planner_client.chat.completions.create(
        model="glm-4.7",
        messages=[
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": integration_prompt}
        ],
        temperature=0.3,
        max_tokens=8192,
    )
    
    print(final_response.choices[0].message.content)

asyncio.run(main())
```

#### 3.4.3 使用 LangGraph 编排（推荐）

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated, List
import operator

class AgentState(TypedDict):
    """定义智能体状态"""
    user_request: str
    venue_result: str
    supplier_result: str
    process_result: str
    final_plan: str

# 定义节点函数
async def planner_node(state: AgentState) -> AgentState:
    """Planner Agent：需求提取和任务分发"""
    client = ZhipuAI(api_key="your-zhipu-api-key")
    
    response = client.chat.completions.create(
        model="glm-4.7",
        messages=[
            {"role": "system", "content": "提取用户的活动需求信息"},
            {"role": "user", "content": state['user_request']}
        ]
    )
    
    print(f"需求提取完成：{response.choices[0].message.content}")
    return state

async def venue_searcher_node(state: AgentState) -> AgentState:
    """场地搜索 Agent"""
    client = ZhipuAI(api_key="your-zhipu-api-key")
    
    response = client.chat.completions.create(
        model="glm-4.7",
        messages=[
            {"role": "system", "content": VENUE_SEARCHER_SYSTEM_PROMPT},
            {"role": "user", "content": state['user_request']}
        ]
    )
    
    state['venue_result'] = response.choices[0].message.content
    return state

async def supplier_searcher_node(state: AgentState) -> AgentState:
    """商家搜索 Agent"""
    client = ZhipuAI(api_key="your-zhipu-api-key")
    
    response = client.chat.completions.create(
        model="glm-4.7",
        messages=[
            {"role": "system", "content": SUPPLIER_SEARCHER_SYSTEM_PROMPT},
            {"role": "user", "content": state['user_request']}
        ]
    )
    
    state['supplier_result'] = response.choices[0].message.content
    return state

async def process_searcher_node(state: AgentState) -> AgentState:
    """流程参考搜索 Agent"""
    client = ZhipuAI(api_key="your-zhipu-api-key")
    
    response = client.chat.completions.create(
        model="glm-4.7",
        messages=[
            {"role": "system", "content": PROCESS_SEARCHER_SYSTEM_PROMPT},
            {"role": "user", "content": state['user_request']}
        ]
    )
    
    state['process_result'] = response.choices[0].message.content
    return state

async def integrator_node(state: AgentState) -> AgentState:
    """Planner 整合生成方案"""
    client = ZhipuAI(api_key="your-zhipu-api-key")
    
    integration_prompt = f"""
    根据以下三类搜索结果，生成完整的活动策划方案：
    
    【场地搜索结果】
    {state['venue_result']}
    
    【商家搜索结果】
    {state['supplier_result']}
    
    【流程参考搜索结果】
    {state['process_result']}
    
    用户需求：{state['user_request']}
    
    请生成完整的策划方案，控制在预算范围内。
    """
    
    response = client.chat.completions.create(
        model="glm-4.7",
        messages=[
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": integration_prompt}
        ],
        max_tokens=8192
    )
    
    state['final_plan'] = response.choices[0].message.content
    return state

# 构建状态图
workflow = StateGraph(AgentState)

# 添加节点
workflow.add_node("planner", planner_node)
workflow.add_node("venue_searcher", venue_searcher_node)
workflow.add_node("supplier_searcher", supplier_searcher_node)
workflow.add_node("process_searcher", process_searcher_node)
workflow.add_node("integrator", integrator_node)

# 定义边（执行流程）
workflow.set_entry_point("planner")
workflow.add_edge("planner", "venue_searcher")
workflow.add_edge("planner", "supplier_searcher")
workflow.add_edge("planner", "process_searcher")
workflow.add_edge(["venue_searcher", "supplier_searcher", "process_searcher"], "integrator")
workflow.add_edge("integrator", END)

# 编译图
app = workflow.compile()

# 使用示例
async def run_planning(user_input: str):
    initial_state = {
        "user_request": user_input,
        "venue_result": "",
        "supplier_result": "",
        "process_result": "",
        "final_plan": ""
    }
    
    final_state = await app.ainvoke(initial_state)
    return final_state['final_plan']

# 运行
plan = asyncio.run(run_planning("帮我策划一个500人的公司年会，预算20万，地点在北京"))
print(plan)
```

### 3.5 共享工具集设计

#### 3.5.1 向量数据库工具（案例检索）

```python
class CaseRetriever:
    """活动案例检索工具"""
    
    def __init__(self, vector_db_url: str):
        # 初始化向量数据库连接
        self.db = connect_to_vector_db(vector_db_url)
    
    def retrieve_cases(
        self, 
        query: str, 
        activity_type: str = None,
        top_k: int = 10
    ) -> List[dict]:
        """
        检索相似活动案例
        
        Args:
            query: 检索查询文本
            activity_type: 活动类型过滤
            top_k: 返回结果数量
        """
        # 生成查询向量
        query_vector = self._embed(query)
        
        # 构建过滤条件
        filters = {}
        if activity_type:
            filters["activity_type"] = activity_type
        
        # 向量相似度检索
        results = self.db.search(
            collection_name="activity_cases",
            query_vector=query_vector,
            filters=filters,
            limit=top_k
        )
        
        return results
    
    def _embed(self, text: str) -> List[float]:
        """文本向量化"""
        # 可以使用智谱的 embedding API
        pass
```

#### 3.5.2 外部 API 工具

```python
class WeatherAPI:
    """天气查询工具"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    def get_weather(self, city: str, date: str) -> dict:
        """获取指定城市和日期的天气信息"""
        # 调用天气 API
        pass

class VenueAPI:
    """场地查询工具"""
    
    def search_venues(
        self, 
        city: str, 
        capacity: int,
        venue_type: str = None,
        budget_range: tuple = None
    ) -> List[dict]:
        """搜索符合条件的场地"""
        # 调用场地数据库或第三方平台 API
        pass

class SupplierAPI:
    """商家查询工具"""
    
    def search_suppliers(
        self,
        service_type: str,
        city: str,
        budget_range: tuple = None
    ) -> List[dict]:
        """搜索符合条件的商家"""
        # 调用商家数据库或第三方平台 API
        pass
```

### 3.6 工具调用示例（GLM-4.7 Function Calling）

智谱 GLM-4.7 原生支持 Function Calling，可以更精确地控制工具调用：

```python
from zhipuai import ZhipuAI

client = ZhipuAI(api_key="your-zhipu-api-key")

# 定义工具
tools = [
    {
        "type": "function",
        "function": {
            "name": "search_venues",
            "description": "搜索活动场地",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市"},
                    "capacity": {"type": "integer", "description": "容纳人数"},
                    "budget": {"type": "number", "description": "预算上限"}
                },
                "required": ["city", "capacity"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_suppliers",
            "description": "搜索活动商家",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_type": {"type": "string", "description": "服务类型"},
                    "city": {"type": "string", "description": "城市"}
                },
                "required": ["service_type", "city"]
            }
        }
    }
]

# 对话示例
response = client.chat.completions.create(
    model="glm-4.7",
    messages=[
        {"role": "system", "content": "你是活动策划助手"},
        {"role": "user", "content": "帮我在北京找一个能容纳500人的场地，预算10万以内"}
    ],
    tools=tools,
    tool_choice="auto"
)

# 检查是否需要调用工具
if response.choices[0].message.tool_calls:
    for tool_call in response.choices[0].message.tool_calls:
        function_name = tool_call.function.name
        function_args = tool_call.function.arguments
        
        # 执行工具调用
        if function_name == "search_venues":
            result = search_venues(**eval(function_args))
        
        # 将工具结果返回给模型
        response = client.chat.completions.create(
            model="glm-4.7",
            messages=[
                {"role": "system", "content": "你是活动策划助手"},
                {"role": "user", "content": "帮我在北京找一个能容纳500人的场地，预算10万以内"},
                response.choices[0].message,
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result)
                }
            ]
        )
```

---

## 四、业务流程设计

### 4.1 活动策划标准流程

```
开始
  │
  ▼
┌─────────────┐
│ 需求收集阶段 │ ──── 提取：活动类型、主题、规模、时间、地点、预算等
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 需求分析阶段 │ ──── 分析：可行性、风险点、关键约束
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 方案生成阶段 │ ──── 生成：活动流程、人员配置、物料清单、宣传计划
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 资源规划阶段 │ ──── 规划：场地、设备、人员、供应商
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 预算估算阶段 │ ──── 计算：总成本、分项明细、优化建议
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 风险评估阶段 │ ──── 评估：潜在风险、应对措施、备选方案
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 方案输出阶段 │ ──── 输出：策划文档、甘特图、任务清单
└──────┬──────┘
       │
       ▼
     结束
```

### 4.2 详细流程说明

#### 阶段 1: 需求收集
- **输入**: 用户的自然语言描述
- **处理**: 使用 LLM 提取结构化信息
- **输出**: 活动需求 JSON 对象

#### 阶段 2: 需求分析
- **输入**: 活动需求对象
- **处理**: 
  - 检查需求完整性
  - 分析需求合理性
  - 识别冲突约束
- **输出**: 需求分析报告 + 缺失项列表

#### 阶段 3: 方案生成
- **输入**: 活动需求 + 历史案例（RAG）
- **处理**:
  - 检索相似活动案例
  - 基于 LLM 生成个性化方案
  - 多方案对比优化
- **输出**: 活动方案草案

#### 阶段 4: 资源规划
- **输入**: 活动方案 + 资源库
- **处理**:
  - 匹配所需资源
  - 检查资源可用性
  - 生成资源清单
- **输出**: 资源配置方案

#### 阶段 5: 预算估算
- **输入**: 资源清单 + 价格数据库
- **处理**:
  - 分项成本计算
  - 总成本汇总
  - 成本优化建议
- **输出**: 预算明细表

#### 阶段 6: 风险评估
- **输入**: 活动方案 + 历史风险库
- **处理**:
  - 识别潜在风险
  - 评估影响程度
  - 制定应对措施
- **输出**: 风险评估报告

#### 阶段 7: 方案输出
- **输入**: 前述所有阶段成果
- **处理**:
  - 生成策划文档 (Word/PDF)
  - 生成甘特图
  - 生成任务清单
- **输出**: 完整活动策划包

---

## 五、功能模块设计

### 5.1 核心功能模块

| 模块名称 | 功能描述 | 技术实现 |
|---------|---------|---------|
| 智能对话引擎 | 处理用户自然语言输入，保持对话上下文 | 智谱 GLM-4.7 API + 对话历史管理 |
| 需求提取器 | 从对话中结构化提取活动需求信息 | LLM + 结构化输出 |
| 案例检索引擎 | 基于语义相似度检索历史活动案例 | 向量数据库 + Embedding |
| 方案生成器 | 根据需求和案例生成活动方案 | LLM + Chain-of-Thought 推理 |
| 预算计算器 | 自动计算活动各项成本 | 规则引擎 + 价格数据库 |
| 风险分析器 | 识别和评估活动风险 | LLM + 风险知识库 |
| 文档生成器 | 生成标准格式的策划文档 | 模板引擎 + 格式化库 |
| 进度追踪器 | 跟踪活动筹备进度 | 任务管理 + 状态机 |

### 5.2 数据模型设计

#### 活动需求模型 (ActivityRequest)
```json
{
  "activity_type": "企业年会",
  "theme": "共赴未来",
  "scale": {
    "attendee_count": 500,
    "departments": ["市场部", "销售部", "技术部"]
  },
  "time": {
    "start_date": "2025-01-20",
    "duration_hours": 4,
    "prefer_time_range": "下午"
  },
  "location": {
    "city": "北京",
    "prefer_area": "朝阳区",
    "venue_type": "酒店宴会厅"
  },
  "budget": {
    "total": 200000,
    "currency": "CNY",
    "flexible": true
  },
  "requirements": {
    "need_catering": true,
    "need_a_v_equipment": true,
    "need_photography": true,
    "special_needs": ["无障碍设施"]
  }
}
```

#### 活动方案模型 (ActivityPlan)
```json
{
  "plan_id": "pln_20250120_001",
  "activity_name": "公司2025年度盛典",
  "timeline": [
    {
      "stage": "签到",
      "start_time": "14:00",
      "duration": "30min",
      "location": "大厅"
    },
    {
      "stage": "开场致辞",
      "start_time": "14:30",
      "duration": "20min",
      "location": "主会场",
      "responsible": "总经理"
    }
  ],
  "resources": {
    "venue": {...},
    "catering": {...},
    "equipment": [...],
    "personnel": [...]
  },
  "budget_breakdown": {...},
  "risks": [...],
  "checklist": [...]
}
```

---

## 六、实施步骤

### 6.1 第一阶段: 基础搭建 (Week 1-2)

**目标**: 完成项目基础设施和核心智能体框架

**任务清单**:
- [ ] 项目初始化，配置开发环境
- [ ] 搭建 FastAPI 服务框架
- [ ] 集成智谱 API SDK，配置 API 密钥
- [ ] 实现 Planner Agent 基础对话能力
- [ ] 设计数据库表结构并创建
- [ ] 编写基础单元测试

**技术要点**:
```python
# 智谱 API 基础调用示例
from zhipuai import ZhipuAI

client = ZhipuAI(api_key="your-zhipu-api-key")

response = client.chat.completions.create(
    model="glm-4.7",
    max_tokens=4096,
    messages=[
        {"role": "system", "content": "你是一个专业的活动策划助手"},
        {"role": "user", "content": "帮我策划一个500人的公司年会"}
    ]
)

print(response.choices[0].message.content)
```

### 6.2 第二阶段: 搜索 Agent 开发 (Week 3-4)

**目标**: 实现 3 个搜索 Agent 的核心功能

**任务清单**:
- [ ] 实现 Search Agent 1（场地搜索）
- [ ] 实现 Search Agent 2（商家搜索）
- [ ] 实现 Search Agent 3（流程参考搜索）
- [ ] 搭建向量数据库（活动案例）
- [ ] 准备场地和商家数据集
- [ ] 实现并行调用机制

**技术要点**:
```python
# 结构化输出示例（使用 JSON Schema）
tools = [
    {
        "name": "extract_activity_requirements",
        "description": "从用户描述中提取活动需求",
        "input_schema": {
            "type": "object",
            "properties": {
                "activity_type": {"type": "string"},
                "attendee_count": {"type": "integer"},
                "budget": {"type": "number"}
            },
            "required": ["activity_type"]
        }
    }
]
```

### 6.3 第三阶段: 知识库构建 (Week 5-6)

**目标**: 构建活动策划知识库，提升智能体专业性

**任务清单**:
- [ ] 收集活动策划专业知识
- [ ] 整理常见活动类型案例
- [ ] 建立价格数据库
- [ ] 构建风险评估知识库
- [ ] 实现知识库更新机制

**知识库内容**:
- 活动类型及标准流程
- 场地信息数据库
- 供应商资源库
- 常见问题及解决方案
- 预算参考标准

### 6.4 第四阶段: 流程编排与工具集成 (Week 7-8)

**目标**: 实现完整的活动策划流程，集成所有工具

**任务清单**:
- [ ] 实现流程编排器
- [ ] 集成外部 API（天气、地图等）
- [ ] 开发文档生成工具
- [ ] 实现进度追踪功能
- [ ] 添加错误处理和重试机制

**技术要点**:
```python
# LangGraph 编排示例
from langgraph.graph import StateGraph, END

# 构建智能体状态图
workflow = StateGraph(AgentState)
workflow.add_node("planner", planner_node)
workflow.add_node("venue_searcher", venue_searcher_node)
workflow.add_node("supplier_searcher", supplier_searcher_node)
workflow.add_node("process_searcher", process_searcher_node)
workflow.add_node("integrator", integrator_node)

# 定义并行执行
workflow.set_entry_point("planner")
workflow.add_edge("planner", "venue_searcher")
workflow.add_edge("planner", "supplier_searcher")
workflow.add_edge("planner", "process_searcher")
workflow.add_edge(["venue_searcher", "supplier_searcher", "process_searcher"], "integrator")
workflow.add_edge("integrator", END)

app = workflow.compile()
```

### 6.5 第五阶段: 用户界面开发 (Week 9-10)

**目标**: 开发用户友好的交互界面

**任务清单**:
- [ ] 设计 UI/UX 原型
- [ ] 开发 Web 前端界面
- [ ] 实现实时对话功能
- [ ] 开发方案展示页面（可视化流程、预算图表）
- [ ] 添加文档下载功能（PDF、Word）

### 6.6 第六阶段: 测试与优化 (Week 11-12)

**目标**: 全面测试并优化系统性能

**任务清单**:
- [ ] 功能测试（4 个 Agent 的独立测试和集成测试）
- [ ] 性能测试（并行调用效率）
- [ ] 压力测试（高并发场景）
- [ ] 提示词优化（各 Agent 的 System Prompt）
- [ ] 准确率评估（方案生成质量）

---

## 七、关键技术与难点

### 7.1 技术难点及解决方案

| 难点 | 解决方案 |
|-----|---------|
| 复杂需求理解 | Planner Agent 使用 Chain-of-Thought 提示词，分步提取需求 |
| 案例检索准确性 | 优化 Embedding 模型（智谱 embedding），混合检索（向量+关键词） |
| 方案个性化 | 结合用户历史偏好，动态调整 Planner 生成策略 |
| 预算准确性 | 建立地区价格数据库，实时更新商家报价 |
| 并行调用协调 | 使用 asyncio 实现高效并行调用 3 个搜索 Agent |
| 结果冲突解决 | Planner 使用权重算法和规则引擎解决场地、商家、流程之间的冲突 |

### 7.2 优化建议

1. **Prompt Engineering**
   - 为每个 Agent 定制专属 System Prompt
   - 使用 Few-Shot 示例提升各 Agent 输出质量
   - 实施动态提示词，根据活动类型调整

2. **性能优化**
   - 利用 GLM-4.7 的大上下文能力（128K tokens）
   - 实现请求批处理和连接池
   - 添加结果缓存层（场地、商家信息）
   - 使用 LangGraph 实现高效的状态管理

3. **可靠性增强**
   - 实现多轮验证机制（Planner 自动检查方案完整性）
   - 添加人工审核环节
   - 建立异常处理和降级策略

4. **成本优化**
   - 优化并行调用策略，减少冗余请求
   - 对常用查询结果进行缓存
   - 根据场景选择合适的 GLM 模型版本（GLM-4/ GLM-4-Flash）

---

## 八、数据准备

### 8.1 训练数据需求

| 数据类型 | 数据量 | 来源 | 用途 |
|---------|-------|------|------|
| 活动案例 | 1000+ 条 | 企业内部/公开数据 | 案例检索、方案生成 |
| 活动流程文档 | 500+ 份 | 专业策划公司 | 知识库构建 |
| 价格数据 | 实时更新 | 多平台爬取/人工整理 | 预算计算 |
| 风险案例 | 300+ 条 | 历史记录/行业报告 | 风险评估 |

### 8.2 数据结构示例

**活动案例**:
```markdown
# 活动案例：科技公司年度客户答谢会

## 基本信息
- 活动类型：客户答谢会
- 参与人数：200人
- 预算：15万元
- 时长：4小时
- 地点：上海某五星级酒店

## 活动流程
1. 13:30-14:00 签到与茶歇
2. 14:00-14:15 开场致辞
3. 14:15-15:00 产品发布
4. 15:00-15:30 中场休息
5. 15:30-16:30 客户分享
6. 16:30-17:30 晚宴与抽奖

## 成功要素
- 提前2周发送正式邀请
- 准备客户伴手礼
- 设置互动抽奖环节
- 安排摄影师记录

## 经验教训
- 签到流程需要增加人手
- 音响设备需提前测试
```

---

## 九、成本估算

### 9.1 开发成本

| 项目 | 成本 |
|-----|------|
| 开发人力 (2人×3个月) | 30-40万元 |
| 智谱 API 费用 | 0.3-0.5万元/月 |
| 服务器与基础设施 | 0.5-1万元/月 |
| 向量数据库 | 0.1-0.3万元/月 |
| 其他第三方服务 | 0.2-0.5万元/月 |

### 9.2 运营成本（月度）

| 项目 | 成本 |
|-----|------|
| 智谱 API 调用费用 | 0.3-0.6万元（按量付费，性价比高） |
| 服务器费用 | 0.5-1万元 |
| 维护与优化 | 1-2万元 |
| 数据更新 | 0.2-0.5万元 |

### 9.3 智谱 API 定价说明

参考智谱 AI 定价（具体以官网为准）：
- **GLM-4.7**: 约 ¥0.1-0.2/千 tokens（输入），约 ¥0.2-0.4/千 tokens（输出）
- **GLM-4-Flash**: 更便宜，约 ¥0.05/千 tokens（输入），约 ¥0.1/千 tokens（输出）

单次活动策划调用成本估算：
- Planner Agent: ~2000 tokens
- 3 个搜索 Agent: 各 ~1000 tokens
- Planner 整合: ~3000 tokens
- 总计: ~7000 tokens = ~¥0.7-1.4/次

日均处理 100 次查询，月成本约 ¥2100-4200

---

## 十、风险评估与应对

| 风险 | 影响 | 概率 | 应对措施 |
|-----|------|------|---------|
| LLM 输出不准确 | 高 | 中 | 添加人工审核，建立验证机制 |
| API 成本超支 | 中 | 中 | 实施请求限流，优化提示词 |
| 数据安全泄露 | 高 | 低 | 加密存储，权限控制 |
| 系统性能不足 | 中 | 中 | 水平扩展，缓存优化 |
| 知识库过时 | 中 | 高 | 建立自动更新机制 |

---

## 十一、后续迭代方向

### 11.1 短期优化 (3-6个月)
- 增加更多活动类型支持
- 优化预算计算准确性
- 提升方案个性化程度
- 添加协作功能

### 11.2 中期规划 (6-12个月)
- 集成供应商系统
- 实现自动化采购
- 添加活动效果分析
- 支持多语言

### 11.3 长期愿景 (1-2年)
- 构建活动策划生态平台
- 实现端到端活动管理
- 引入 VR/AR 技术预览
- AI 预测活动效果

---

## 附录

### A. 相关资源
- **智谱 AI 开放平台**: https://open.bigmodel.cn
- **智谱 API 文档**: https://open.bigmodel.cn/dev/api
- **GLM-4.7 模型介绍**: https://open.bigmodel.cn/dev/howuse/model
- **LangChain 文档**: https://python.langchain.com
- **LangGraph 文档**: https://langchain-ai.github.io/langgraph
- **FastAPI 文档**: https://fastapi.tiangolo.com

### B. 参考项目
- AutoGPT（多智能体协作）
- CrewAI（智能体编排）
- LangGraph（状态机式智能体工作流）

### C. 联系方式
如有疑问或需要技术支持，请联系项目团队。

---

**文档版本**: v2.0  
**创建日期**: 2025-01-01  
**最后更新**: 2025-01-01  
**更新说明**: 将 LLM 模型改为智谱 GLM-4.7，采用 3 个搜索 Agent + 1 个 Planner Agent 的多智能体架构