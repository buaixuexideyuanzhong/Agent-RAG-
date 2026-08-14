"""
活动策划多智能体系统 - 配置文件
"""
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# 基于 __file__ 定位项目根目录的 .env，避免启动目录（CWD）不同导致加载失败
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
class Config:
    """系统配置类"""

    # LLM API 配置（OpenAI 兼容端点，默认智谱开放平台）
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_API_BASE: str = os.getenv("LLM_API_BASE", "https://open.bigmodel.cn/api/paas/v4")

    # 模型配置
    PLANNER_MODEL: str = "glm-4.6v"
    SEARCHER_MODEL: str = "glm-4.6v"

    # 并行调用配置
    ENABLE_PARALLEL: bool = True

    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "activity_planner.log"

    # ===== 高并发抗 429：错峰派发 + 自适应重试 + 流式输出 =====
    # 错峰间隔（秒）：两次 LLM 调用之间的最小间隔，把并行搜索的瞬时尖峰摊平
    STAGGER_INITIAL_INTERVAL: float = 0.5   # 初始间隔
    STAGGER_MIN_INTERVAL: float = 0.2       # 成功后逐步降到此值（加性恢复吞吐）
    STAGGER_MAX_INTERVAL: float = 4.0       # 遇 429 后退避上限（乘性增加）
    STAGGER_RECOVERY_STEP: float = 0.05     # 每次成功后间隔减小量
    # 429 自适应重试
    LLM_MAX_RETRIES: int = 4                # 429 最大重试次数
    LLM_RETRY_BASE_DELAY: float = 0.5       # 重试基础延迟（指数退避基数）
    LLM_RETRY_MAX_DELAY: float = 10.0       # 单次重试最大延迟
    # 流式输出：整合节点生成方案时实时打印到控制台
    ENABLE_STREAM_OUTPUT: bool = True

    # ===== 外部工具接入（真实数据检索）=====
    # 高德 MCP（场地搜索）
    AMAP_API_KEY: str = os.getenv("AMAP_API_KEY", "")
    AMAP_MCP_URL: str = "https://mcp.amap.com/sse"  # 拼接 ?key= 后使用
    # 百度地图 POI（商家搜索）
    BAIDU_MAP_AK: str = os.getenv("BAIDU_MAP_AK", "")
    BAIDU_PLACE_ENDPOINT: str = "https://api.map.baidu.com/place/v2/search"
    # 博查 AI 搜索（流程参考）
    BOCHA_API_KEY: str = os.getenv("BOCHA_API_KEY", "")
    BOCHA_ENDPOINT: str = "https://api.bocha.cn/v1/web-search"
    # 工具开关 / 超时 / 降级
    ENABLE_REAL_TOOLS: bool = True       # False 时全部退回纯 LLM 生成
    TOOL_TIMEOUT: int = 15               # 单次工具调用超时(秒)
    TOOL_MAX_ROUNDS: int = 5             # Function Calling 最大轮数
    MCP_READ_TIMEOUT: int = 90           # 高德 MCP SSE 读超时(秒)，防止连接挂死

    # ===== Redis 缓存层 =====
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    REDIS_ENABLED: bool = True           # False 时完全关闭缓存
    LLM_CACHE_TTL: int = 604800          # LLM 响应缓存(秒)，7天
    TOOL_CACHE_TTL: int = 86400          # 工具结果缓存(秒)，1天
    CASE_CACHE_TTL: int = 3600           # 热案例缓存(秒)，1小时
    ENABLE_LLM_CACHE: bool = True        # 搜索/提取节点 LLM 响应缓存（整合节点不开）
    ENABLE_TOOL_CACHE: bool = True       # 外部工具结果缓存

    # ===== MySQL 结构化存储层 =====
    DB_ENABLED: bool = True              # False 时关闭案例库
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "3306"))
    DB_USER: str = os.getenv("DB_USER", "root")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "123456")
    DB_NAME: str = os.getenv("DB_NAME", "event_planner")

    # ===== RAG 知识库 =====
    ENABLE_RAG: bool = True
    # Embedding：本地 fastembed BGE 小模型（免费离线，HuggingFace 下载）
    KB_EMBEDDING_MODEL: str = "BAAI/bge-small-zh-v1.5"   # 512 维
    KB_EMBEDDING_DIM: int = 512
    # Milvus 向量库
    MILVUS_URI: str = os.getenv("VECTOR_DB_URL", "http://localhost:19530") or "http://localhost:19530"
    MILVUS_COLLECTION: str = "activity_cases"
    # 检索参数
    KB_TOP_K: int = 3
    KB_SIMILARITY_THRESHOLD: float = 0.35   # 低于此分数的案例不返回
    KB_ATTENDEE_RANGE: int = 300            # 人数过滤区间 ±范围

    # 向量数据库配置 (可选)
    VECTOR_DB_URL: Optional[str] = os.getenv("VECTOR_DB_URL", None)

    # 外部 API 配置 (可选)
    WEATHER_API_KEY: Optional[str] = os.getenv("WEATHER_API_KEY", None)
    VENUE_API_KEY: Optional[str] = os.getenv("VENUE_API_KEY", None)

    @classmethod
    def validate(cls) -> bool:
        """验证配置是否完整（企业级：启动时列出所有缺失项及影响）"""
        missing: list = []

        # 核心：LLM 必须
        if not cls.LLM_API_KEY:
            missing.append(("LLM_API_KEY", "LLM 调用，必须配置"))
        # 工具 key：缺失时该工具降级为 LLM 生成
        if not cls.AMAP_API_KEY:
            missing.append(("AMAP_API_KEY", "高德场地搜索，缺失时场地降级"))
        if not cls.BAIDU_MAP_AK:
            missing.append(("BAIDU_MAP_AK", "百度商家搜索，缺失时商家降级"))
        if not cls.BOCHA_API_KEY:
            missing.append(("BOCHA_API_KEY", "博查流程搜索，缺失时流程降级"))
        # 基础设施：缺失时案例库不可用（不影响主流程）
        infra = []
        if not cls.REDIS_ENABLED:
            infra.append("Redis 缓存")
        if not cls.DB_ENABLED:
            infra.append("MySQL 案例库")
        if not cls.ENABLE_RAG:
            infra.append("RAG 知识库")

        if missing:
            print("\n⚠️  配置缺失告警：")
            for key, impact in missing:
                print(f"  - {key}: {impact}")
        if infra:
            print(f"  - 已关闭: {'、'.join(infra)}")
        if not missing and not infra:
            print("✅ 配置完整")

        # 仅当核心 LLM key 缺失时视为不可用；工具 key 缺失走降级，不阻断
        return bool(cls.LLM_API_KEY)


# System Prompt 配置
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

# 预设示例请求
EXAMPLE_REQUESTS = [
    "帮我策划一个500人的公司年会，预算20万，地点在北京朝阳，时间是下个月中旬",
    "策划一个200人的产品发布会，预算50万，上海浦东，需要高端场地",
    "组织一场100人的客户答谢会，预算10万，广州天河，注重用户体验",
    "安排一个300人的培训会，预算15万，深圳南山，需要完善的设备",
]