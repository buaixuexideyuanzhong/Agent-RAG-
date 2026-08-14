# 活动策划多智能体系统 - 问题排查记录

> 按时间顺序整理项目开发过程中遇到的所有问题、根因与解决方案，方便回顾。
> 目录：代码 / 环境 / API / LangGraph / 高并发 / 外部工具 / RAG / Docker

---

## 一、代码问题

### 1.1 导入语句语法错误（SyntaxError）
**报错**：
```python
# agents.py
from config import Config  (    # ← 括号放错位置
    PLANNER_SYSTEM_PROMPT, ...
)
# test_workflow.py
from config import Config, (    # ← 逗号+括号混用
```
**根因**：多行导入的左括号必须紧跟 `import` 关键字之后，不能中途插入已命名的导入项。
**解决**：
```python
from config import (
    Config,
    PLANNER_SYSTEM_PROMPT,
    ...
)
```

### 1.2 AI 生成代码对象名写错
**现象**：AI 生成的代码出现属性/参数名拼写错误，最常见的是**驼峰/蛇形命名混用**。
**案例**：
- `mcp` SDK 的 `Tool` 对象属性是 `input_schema`（蛇形），写成 `inputSchema`（驼峰）→ AttributeError。
- **教训**：调用第三方 SDK 时，先用 `inspect.signature()` 或 `dir()` 确认真实属性名，不要凭记忆猜。

---

## 二、LangGraph 问题

### 2.1 并行节点状态冲突
**报错**：
```
At key 'user_request': Can receive only one value per step.
Use an Annotated key to handle multiple values. (INVALID_CONCURRENT_GRAPH_UPDATE)
```
**根因**：三个并行搜索节点（场地/商家/流程）都 `return state` 返回**完整状态字典**，其中包含只读未改的 `user_request` 等字段 → 同一 superstep 内非 Annotated 字段收到多个并发值。
**解决**：改为 **partial update**——每个节点只返回自己更新的 key：
```python
return {
    "venue_result": result,
    "messages": ["..."],   # messages/errors 用 operator.add 自动合并
}
```
> 关键：
> - 并行节点绝不返回未修改的共享字段（`user_request`、`extracted_requirements` 等只读字段不返回）
> - `messages`/`errors` 是 `Annotated[..., operator.add]`，返回**新列表**让 reducer 追加，不会重复
> - 不要就地 `state["xxx"].append()`——那是修改共享状态，并行下不可靠

---

## 三、环境与依赖问题

### 3.1 requirements.txt 不匹配
- `asyncio>=3.4.3` **错误**：asyncio 是 Python 标准库（3.4+ 自带），PyPI 上同名包是老版本 backport，不该装。
- `langchain` / `langchain-community` / `pydantic` 未直接 import，由 langgraph 传递依赖，无需显式列出。
- **解决**：只保留代码实际 import 的包 + Python 版本说明（>=3.10）。

### 3.2 默认 python 与 conda 环境不一致
**现象**：`python main.py` 报 `ModuleNotFoundError: langgraph`。
**根因**：默认 `python` 指向 base anaconda（`E:\Program Files\anaconda\python.exe`），未装 langgraph。
**解决**：必须激活 conda 环境：`conda activate huodongcehua`。

### 3.3 fastembed 安装异常 → 换 LangChain
**现象**：`import fastembed` 后 `__file__` 为 None，`from fastembed import TextEmbedding` 报 `ImportError (unknown location)`。
**根因**：fastembed 0.1.1 老旧版本 + 安装不完整（namespace 包异常）。
**解决**：卸载 fastembed，改用 LangChain 框架 `langchain-huggingface` + `sentence-transformers`。
> 注意：`langchain-huggingface` 的 `HuggingFaceEmbeddings` 需要**单独**安装 `sentence-transformers`（它是可选依赖，不会自动装）。

---

## 四、智谱 AI 相关问题

### 4.1 API Key 失效（401 令牌已过期或验证不正确）
**根因**：智谱 API Key 失效（过期/被吊销/账户变动）。
**解决**：登录 open.bigmodel.cn 控制台重新生成 key，替换 `.env` 的 `LLM_API_KEY`。

### 4.2 速率限制（429 code 1302）
**现象**：`您的账户已达到速率限制，请您控制请求频率`。
**根因**：3 个搜索 Agent 并行 → 同一毫秒打出 3 个请求，触发瞬时 QPS/并发墙（账户 2.9M token 但 RPM 受限）。
**解决**：错峰派发 + 自适应重试 + 流式输出（见第五节）。

### 4.3 Embedding 额度不足（429 code 1113）
**现象**：`余额不足或无可用资源包,请充值`（embedding-3 / embedding-2）。
**根因**：glm-4.6v 的 290 万 token 额度**不覆盖** embedding 模型，需要单独资源包。
**解决**：改用本地开源 embedding——LangChain `HuggingFaceEmbeddings` + `BAAI/bge-small-zh-v1.5`（512 维，免费离线，HF 镜像下载）。

### 4.4 glm-4.6v 视觉模型支持 function calling
**验证**：glm-4.6v 支持 `tools` 参数，测试返回 `tool_calls`，FC 方案可行。

### 4.5 glm-4.6v 推理模型耗尽 max_tokens → 输出截断/为空
**现象**：需求提取、LLM judge 返回空字符串或截断的 JSON（`Unterminated string`）；实测 content 为空、`finish_reason=length`。
**根因**：glm-4.6v 是**推理模型**，流式响应先输出大量 `reasoning_content`，真正的正文 `content` 在最后。`max_tokens` 太小（1024/300）时推理就把预算耗尽，正文从未发出。
**解决**：需要结构化/长输出的调用 `max_tokens` 提到 4096（需求提取节点 1024→4096；LLM judge 300→4096，且 judge 绕过缓存——`on_chunk` 传空回调）。
**效果**：截断/空响应消失。
> 判别法：返回空/截断时优先怀疑 max_tokens 而非 prompt；`finish_reason=length` 即预算耗尽信号。

---

## 五、高并发抗 429 设计

**方案组合**：错峰派发 + 自适应重试 + 流式输出（不换模型）。

### 5.1 错峰派发（AdaptiveStagger 类，agents.py）
- 全局共享限速器，所有 LLMClient 实例共用一个，对同一账户统一节流。
- 两次 LLM 调用间至少间隔 `interval` 秒，3 个并行请求实测发出时刻 `[0.0, 0.5, 1.0]` 秒。
- 把「3 请求/0 秒」摊平成「3 请求/1 秒」，避开 QPS/并发墙，仅多花 ~1 秒。

### 5.2 自适应重试（AIMD 机制，agents.py chat()）
- 429 检测：异常类型 → HTTP 状态码（429）→ 错误文本（`速率限制`/`rate limit`）三重兜底。
- **乘性退避**：遇 429 间隔翻倍（0.5→1.0→2.0→4.0），并立即暂停后续调用。
- **加性恢复**：每次成功间隔减小 0.05s，缓慢回升吞吐。
- 指数退避重试（0.5→1→2→4s + 随机抖动），最多 4 次。
- **安全网**：已实时输出过部分内容则放弃重试，避免重复输出。

### 5.3 流式输出（_stream_collect，agents.py）
- 智谱 SDK 无异步客户端，`create(stream=True)` 返回同步迭代器。
- 用「executor 线程生产 + asyncio.Queue 消费」桥接到异步循环，实现实时回调。
- 整合节点生成最终方案时实时打印到控制台（最长 ~8192 token），体感速度大幅提升。

### 5.4 关键配置（config.py）
```python
STAGGER_INITIAL_INTERVAL=0.5  STAGGER_MIN_INTERVAL=0.2
STAGGER_MAX_INTERVAL=4.0      STAGGER_RECOVERY_STEP=0.05
LLM_MAX_RETRIES=4             LLM_RETRY_BASE_DELAY=0.5
ENABLE_STREAM_OUTPUT=True
```

---

## 六、外部工具接入问题

### 6.1 高德 MCP：TaskGroup 包装的真实错误
**现象**：`unhandled errors in a TaskGroup (1 sub-exception)`，看似连接错误。
**真因**：`_load_amap_tools` 里 `t.inputSchema` 写成驼峰，SDK 属性是 `input_schema` → AttributeError 被任务组包装。
**解决**：`t.inputSchema` → `t.input_schema`。
> 教训：MCP/TaskGroup 包装的异常要递归展开子异常（`e.exceptions`）才能看到真因。

### 6.2 高德 key 平台类型不匹配
**报错**：`USERKEY_PLAT_NOMATCH`（错误码 10009）。
**根因**：key 绑定的平台不是「Web服务」类型（MCP 网关接受连接，但底层 POI 搜索调 Web 服务 API 被拒）。
**解决**：高德控制台新建「Web服务」类型 key。

### 6.3 高德 MCP SSE 连接挂死
**现象**：`Error in post_writer` 后进程挂起 5 分钟才退出（255）。
**根因**：`mcp.client.sse.sse_client` 默认 `sse_read_timeout=300`（5 分钟），连接异常时长时间等待。
**解决**：
```python
async with sse_client(url, timeout=Config.TOOL_TIMEOUT, sse_read_timeout=Config.MCP_READ_TIMEOUT):
# 配合 asyncio.wait_for(..., timeout=...) 整体兜底 → 失败快速降级
```

### 6.4 博查无额度
**现象**：`403 You do not have enough money or package quota`（`.cn` 和 `.comai` 两个域名都返回）。
**根因**：key 鉴权通过但账户余额/套餐额度为 0，需充值。
**解决**：保持降级到 LLM；充值后自动恢复。

### 6.5 百度 POI 正常（无坑）
百度 POI API 直接可用，返回真实商家数据。

---

## 七、RAG 知识库问题（原生 pymilvus + LangChain embedding）

### 7.1 pymilvus 3.0.1：index_params 类型
**报错**：`expected type: [Index Params], got type: [dict]`。
**解决**：
```python
from pymilvus.milvus_client.index import IndexParams
ip = IndexParams()
ip.add_index(field_name="embedding", index_type="HNSW",
             metric_type="COSINE", params={"M":16,"efConstruction":256})
```

### 7.2 Milvus 集合需索引 + 加载
**报错**：`collection not loaded`（search/query 失败）。
**根因**：用 schema 建集合后，索引和加载不会自动完成。
**解决**：`_ensure_collection` 显式 `create_index` + `load_collection`（幂等）。

### 7.3 MySQL 行映射索引越界
**现象**：插入成功但 `list_cases` 返回空。
**根因**：`_row_to_case` 里 `created_at` 用了 `row[11]`，而表只有 **11 列**（索引 0-10），越界 → IndexError 被 except 吞掉返回空列表。
**解决**：`row[11]` → `row[10]`。
> 教训：`SELECT *` + 位置索引易错，建议用列清单或 dict cursor。

### 7.4 案例向量相似度过高（embedding 区分度差）
**现象**：案例向量两两相似度高达 0.66~0.75，检索命中错误案例。
**根因**：`build_embed_text` 里 `plan_text[:500]` 占大头，方案正文结构高度相似（都有【活动概述】【流程安排】…），淹没了「年会/发布会/答谢会 北京/上海/广州」等区分性强的结构化字段。
**解决**：embed_text 改为**结构化字段为主**，方案正文只取首行 80 字。
> 修复后：北京年会检索 0.822 精准命中、上海发布会 0.809 排第一。

### 7.5 Milvus 插入后立即检索为空
**现象**：同一进程内导入后立即检索返回空；新进程检索正常。
**根因**：Milvus 插入的数据未落盘/建索引完成，存在最终一致性窗口。
**解决**：插入后调用 `client.flush(collection)` 强制落盘。

### 7.6 向量库选型波折
- 最初选 Milvus（原生）→ 用户要求「用 langchain 框架做 RAG」→ 用 `langchain-milvus` → 用户反馈「milvus 不适用 langchain 框架，用原生的」→ **最终定案**：原生 pymilvus（向量存储/检索）+ LangChain `HuggingFaceEmbeddings`（embedding）。

### 7.7 Milvus 检索空结果报 Unsupported field type: 0
**现象**：搜索**无命中（0 条结果）**时 `search_cases` 抛 `MilvusException: (code=Unsupported field type: 0)`（pymilvus 的 HybridHits 解析空响应失败），被 try/except 捕获降级返回空；有结果时正常。
**根因**：**客户端 pymilvus 3.0.1/2.6.x 与服务器 Milvus 2.3.3 版本不匹配**（docker-compose 固定 2.3.3）。空结果响应结构让新客户端读到 type=0。
**解决**：pymilvus 降级到 2.4.15（requirements 固定 `pymilvus>=2.4.0,<2.5`）；连带 grpcio→1.67.1、setuptools→80.10.2（2.4.x 的 `__init__.py` 依赖 pkg_resources，setuptools≥81 已移除）；卸载多余且冲突的 `langchain-milvus`（要求 pymilvus≥3，项目未使用）。
**效果**：空结果检索正常返回 0 条，不再打异常日志。
> 版本对应：Milvus 2.3.x ↔ pymilvus 2.4.x；Milvus 2.5+ ↔ pymilvus 3.x。

---

## 八、优雅降级设计（所有外部依赖统一策略）

**原则**：任何外部依赖（Redis/MySQL/Milvus/工具 API）不可用时，对应层全部 no-op（返回 None/空），主流程不被拖死。

| 依赖 | 不可用时表现 |
|---|---|
| Redis | 缓存跳过（首次探测失败标记 `_available=False`，不再重试） |
| MySQL | CRUD 返回 None/空 |
| Milvus | 检索返回空 → process 节点自动走博查/LLM 兜底 |
| 外部工具 | 工具调用失败 → 降级为 LLM 回答，errors 记录降级原因 |

**降级策略**：工具调用失败情况下，降级为 LLM 回答（用户可见提示）。

---

## 九、Docker 问题

### 9.1 拉取镜像 TLS 超时（国内网络）
**现象**：`docker compose up` 拉镜像时报 `net/http: TLS handshake timeout`。
**根因**：国内网络访问 Docker Hub（registry-1.docker.io）不稳定。
**解决**：Docker Desktop 的 daemon.json 配置国内镜像加速，改完**重启 Docker Desktop** 生效：
```json
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.1ms.run",
    "https://docker.xuanyuan.me",
    "https://dockerproxy.net"
  ]
}
```

### 9.2 基础设施容器清单（docker-compose.yml）
```
redis(6379) + mysql(3306) + milvus(19530) + etcd(2379) + minio(9000)
启动：docker compose up -d
```
Milvus standalone 依赖 etcd（元数据）+ minio（对象存储），必须一起起。

### 9.3 aiomysql 连接池关闭告警
**现象**：进程退出时报 `RuntimeError: Event loop is closed`。
**根因**：MySQL 连接池 / Redis 连接未在事件循环关闭前释放。
**解决**：`_run_and_cleanup()` 统一在入口关闭 `RedisCache.close()` + `CasesDB.close()`。

---

## 十、HF 模型下载

### 10.1 国内下载 HuggingFace 模型慢/被墙
**解决**：`.env` 配置镜像，`load_dotenv` 加载后 huggingface_hub 自动走镜像：
```
HF_ENDPOINT=https://hf-mirror.com
```
BGE 模型首次加载会下载（~100MB），之后本地缓存。

---

## 十一、复盘要点（经验总结）

1. **LangGraph 并行**：节点只返回自己更新的 key，绝不返回完整 state。
2. **MCP/TaskGroup 异常**：包装后的异常要递归展开子异常定位真因。
3. **国产 API 三个坑**：key 平台类型（高德）、账户额度分模型（智谱 embedding）、RPM 墙（429）。
4. **AI 生成代码**：调用第三方 SDK 前先用 `inspect.signature()`/`dir()` 确认真实属性名，别凭记忆猜（驼峰/蛇形最易错）。
5. **embedding 质量**：检索文本要结构化字段为主，长正文会稀释区分度。
6. **Milvus 三件套**：建集合 → 建索引 → 加载；插入后要 flush。
7. **位置索引脆弱**：`SELECT *` 映射用列清单或 dict cursor。
8. **国内网络**：Docker 镜像加速 + HF 镜像 必备。
9. **优雅降级**：所有外部依赖都要有 no-op 降级路径，主流程不被拖死。
10. **glm-4.6v 是推理模型**：先输出大量 reasoning_content，需要结构化/长输出的调用 max_tokens 要给足（1024 会截断，提取节点已改 4096）。
11. **空/坏 LLM 响应不要缓存**：`chat()` 的 `set_llm` 加 `text.strip()` 守卫，否则坏结果污染 Redis 7 天并掩盖后续修复。
12. **Milvus 客户端与服务器版本必须匹配**：2.3.x 服务器 ↔ pymilvus 2.4.x；2.4.x 依赖 pkg_resources（需 setuptools<81）。
13. **前后端契约**：响应用 `response_model` 显式化 + API 版本化（`/api/v1`），后端演进才不破坏前端。
14. **Docker DNS + nginx 缓存**：`resolver 127.0.0.11 valid=1s` 是「时间窗口切换」式分发，SSE 长连接天然粘节点，不是严格逐请求轮询。
15. **生产容器内地址**：访问基础设施必须用服务名（`DB_HOST=mysql` 等），宿主 `.env` 的 localhost 靠 `environment` 优先级覆盖。
16. **CPU 版 torch**：纯 CPU 推理（BGE embedding）绝不装 CUDA torch——镜像 2.24GB vs 5-8GB。
17. **SSE 反代必须关缓冲**：`proxy_buffering off` + `proxy_cache off`，否则流式内容被缓冲不实时。
18. **SDK 内建重试会绕过应用层限流**：openai SDK 默认对 429 内建重试 2 次（`max_retries=2`），会绕过本项目自己的 AdaptiveStagger/AIMD 退避造成不一致。换 SDK 时留意「应用层已做的重试/限流」与 SDK 内建重试的叠加。
19. **换 LLM SDK 优先走 OpenAI 兼容端点**：智谱 / 通义 / DeepSeek / Moonshot 均收 OpenAI 兼容 function calling 格式，用官方 openai SDK + `base_url` 指向各家端点即可，工具定义与代码无需按厂商改。

---

## 十二、前后端分离与目录规整（2026-08-06）

### 12.1 FastAPI 后端（前后端分离）
- **原因**：项目从 CLI 单机改为前后端分离，后端用 FastAPI 提供 HTTP API，前端暂不制作（预留 `frontend/` 目录）。
- **内容**：
  - 新增 `backend/api/app.py`（FastAPI 应用，8 个接口：health / workflow / plan / plan/stream(SSE) / cases 列表·保存·删除·导入）。
  - 为支持 SSE 流式：`state.py` 的 `AgentState` 增加 `stream_queue`/`console_output` 字段；`agents.py` 的 integrator 节点流式输出改为「有队列则推入队列，否则打印控制台」；`main.py` 的 `ActivityPlanner.plan()` 增加可选参数。
  - `requirements.txt` 追加 `fastapi` / `uvicorn[standard]` / `python-multipart`。
- **效果**：HTTP API + SSE 流式可用；CLI 行为不变（不传新参数走默认回退）。

### 12.2 目录规整（backend/ 细分包）
- **原因**：12 个 Python 模块扁平堆在根目录，需规整进文件夹。
- **内容**：移入 `backend/` 细分包（`api` / `core` / `agents` / `storage` / `cli`），全部跨模块 import 改相对导入（`from ..core.config import ...`，含函数内懒加载）；`config.py` 的 `.env` 加载改为基于 `__file__` 定位根目录；启动命令改为 `uvicorn backend.api.app:app` / `python -m backend.cli.main`。
- **效果**：结构清晰；`.env` 加载不再依赖启动目录。
- **附带修复**：`test_workflow.py` 预先存在的 bug——对工作流对象调用 `get_workflow_info()`（正确方法名是 `get_graph_info()`；`get_workflow_info` 是 `ActivityPlanner` 的包装方法）。

## 十三、质量评估工具（evaluation/，2026-08-06）

- **原因**：需要衡量整体策划系统质量（用户需求的召回率/准确率）。
- **内容**：
  - `evaluation/test_cases.json`：12 条测试需求 + 约束真值（覆盖信息缺失、特殊需求、极端规模、预算敏感、强时间约束等边界）。
  - `evaluation/seed_cases.json`：20 条种子案例（扩充知识库，导入后 23 条）。
  - `evaluation/run_evaluation.py`：逐条跑真实策划，自动算客观指标（需求提取准确率、方案约束召回率/准确率、工具真实命中率、结构完整性）；质量维度用 GLM 评分（`--judge llm`）。
- **运行**：`python -m evaluation.run_evaluation --judge llm`（全量 12 条约 40-60 分钟，消耗 token）；结果输出到 `evaluation/results/<时间戳>/`。
- **效果**：可自动化评测、调参前后对比。
- **注意**：约束匹配是关键词+数值容差启发式；GLM 自评存在乐观偏差，需人工抽查校准。

## 十四、评测暴露的问题与修复（稳定性加固，2026-08-06）

### 14.1 空/坏响应被 Redis 缓存 7 天污染
- **现象**：`LLMClient.chat()` 无论结果好坏都 `set_llm` 缓存（TTL 7 天）。一次空/截断响应被缓存后，后续所有相同请求持续拿到坏结果，甚至掩盖修复（改 max_tokens 后验证仍失败，清缓存才恢复）。
- **解决**：`chat()` 的 `set_llm` 加 `and text.strip()` 守卫——空/纯空白响应不写缓存。
- **效果**：坏结果不再污染缓存，偶发失败是单次的。

### 14.2 需求提取 JSON 解析失败自动重试
- **现象**：`requirement_extractor_node` 解析 LLM 输出失败（空/截断/带围栏）直接降级 `raw_extract`，导致提取字段为 None。
- **解决**：解析失败时带纠错提示（"你上一次的输出不是合法 JSON，请只输出合法 JSON 对象"，拼在 user_message 尾部构成新缓存键避免命中坏缓存）重试一次，仍失败才降级。
- **效果**：格式异常大概率一次自愈。

### 14.3 LLM judge 的三个坑（evaluation/run_evaluation.py）
- prompt 里的 JSON 示例花括号 `{...}` 被 `str.format()` 当成字段 → KeyError；需转义 `{{...}}`。
- glm-4.6v 推理模型，max_tokens=300/1024 会被 reasoning_content 耗尽 → 正文为空/截断，需 4096。
- judge 输出带推理不稳定，应绕过缓存（`on_chunk` 传空回调）。

## 十五、API 契约与版本化（2026-08-06）

### 15.1 响应契约（response_model，P0）
- **原因**：接口响应无 schema，前端只能拿"自由结构"，后端改字段名/结构前端必断。
- **内容**：7 个 JSON 接口补 `response_model`（`HealthResponse` / `PlanResponse` / `CaseListResponse` 等）；`CaseOut` 过滤掉内部 `embed_text`。
- **效果**：OpenAPI 生成准确 schema，前端可用 `openapi-typescript` 等生成类型安全 client；字段变更在编译期暴露。

### 15.2 API 版本化（/api/v1，P1）
- **原因**：让后端未来做不兼容变更时不破坏使用旧版的前端。
- **内容**：`APIRouter(prefix="/api/v1")` 承载全部路由，`app.include_router(v1)`；旧路径 `/api/*` 返回 404。
- **效果**：未来新增 `v2` router 平行共存，用 v1 的前端零改动。

## 十六、基础设施先降级后恢复不自愈（冷却重探，2026-08-07）

### 16.1 连接失败被永久缓存为不可用（"重启才能恢复"）
- **现象**：后端先于 Docker 启动时，MySQL/Milvus 探测失败 → `_available=False` 被永久缓存；随后 Docker 全部拉起、MySQL 存活，保存案例仍返回 `400 案例保存失败（MySQL/Milvus 不可用）`，只有重启后端进程才能恢复（即用户说的"治标不治本"）。
- **根因**：`CasesDB._get_pool()` / `CaseStore._get_milvus()` 首次探测失败后 `_available=False` 只写不销，后续每次调用直接短路返回 None，**没有重探机制**。
- **解决**：失败后进入 30s 冷却（`_next_probe_at = time.monotonic() + 30`），冷却期内快速短路返回（不重复等 connect_timeout=5s），冷却结束下一次调用自动重连：
  ```python
  if cls._available is False and time.monotonic() < cls._next_probe_at:
      return None
  # 连接成功后：cls._available = True
  # 失败后：     cls._available = False; cls._next_probe_at = time.monotonic() + cls._PROBE_COOLDOWN
  ```
  涉及 `backend/storage/database.py`（CasesDB，`_PROBE_COOLDOWN=30.0`）+ `backend/storage/rag_knowledgebase.py`（CaseStore，同样式）。
- **效果**：先起后端、后起 Docker，30 秒内 MySQL/Milvus 自动重连，案例库功能恢复，无需重启进程。
- **已知遗留**：`RedisCache._get_client()`（backend/storage/cache.py）仍是"首次失败不再重试"的旧式（无冷却重探）。因 Redis 仅作缓存、不可用时 no-op（不阻塞保存/检索主功能），暂未改，后续可统一。
- **教训**：优雅降级不能只看"失败时不拖死主流程"，还要考虑"恢复后能否自愈"——单进程长驻服务里，连接失败状态要有时间失效机制（冷却重探/熔断半开），否则基础设施恢复后必须重启进程。

---

## 十七、生产部署：Nginx 负载均衡 + 多 worker 后端（2026-08-07 ~ 08-10）

### 17.1 部署架构与新增文件
- **新增**：`compose.prod.yml`（生产编排）、`deploy/nginx/nginx.conf` + `Dockerfile`、`backend/Dockerfile`、根目录 `.dockerignore`；README 补「整体运行流程」「生产部署」两章。
- **架构**：三层不变（Docker 基础设施 → FastAPI 后端 → Vue 前端），生产栈加 Nginx：**前端静态托管**（Vite 产物挂载只读卷）+ **`/api` 反向代理**。访问入口 http://localhost:8080。
- **负载均衡两层**：单容器内 `uvicorn --workers N`（多进程并行）；跨容器 `--scale backend=N` + nginx 轮询解析。
- **SSE 专线**：`/api/v1/plan/stream` 单独 location，`proxy_buffering off` + `proxy_cache off` + `proxy_read_timeout 300s`——流式内容必须逐字实时透传，不能进缓冲。

### 17.2 后端镜像 CPU 版 torch（体积 2.24GB vs 5-8GB）
- **现象**：直接 `pip install -r requirements.txt` 构建，镜像 5-8GB。
- **根因**：默认 pypi 的 `torch` 是 CUDA 构建，连拉数 GB `nvidia-*` 库；但 BGE embedding 是**纯 CPU 推理**，用不到 CUDA。
- **解决**：`backend/Dockerfile` 先用 `TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu` 单独装 CPU 版 torch，再装 requirements（sentence-transformers 依赖自动满足，不会再拉 CUDA 版）。镜像降到 **2.24GB**。
- **注意**：pymilvus 2.4.x 运行时依赖 `pkg_resources`，镜像内先 `pip install "setuptools<81"` 固定（同 7.7）。

### 17.3 容器内网络地址必须覆盖为服务名
- **现象**：后端容器内连不上 MySQL/Milvus/Redis。
- **根因**：宿主 `.env` 是 `DB_HOST=localhost` 等，经 `env_file` 注入容器后指向容器自身。
- **解决**：`compose.prod.yml` 的 `environment` 里覆盖：`DB_HOST=mysql`、`REDIS_URL=redis://redis:6379/0`、`VECTOR_DB_URL=http://milvus:19530`（compose 中 `environment` 优先级高于 `env_file`）。

### 17.4 nginx 对 Docker DNS 按 valid 缓存 → "时间窗口切换"式分发
- **机制**：`resolver 127.0.0.11 valid=1s ipv6=off`。Docker DNS 本身按副本轮询解析，但 nginx 会按 `valid` 缓存结果，缓存过期才重新解析换节点。
- **结论**：分发是**时间窗口切换**式（`--scale backend=2` 实测 172.18.0.7↔172.18.0.9），**不是严格逐请求轮询**。SSE 长连接天然全程粘一个节点（必须），间隔数秒的新会话才轮转——属正常，README 已如实说明。

### 17.5 SSE 经 nginx 全链路验证
- 探针 POST `http://localhost:8080/api/v1/plan/stream`：HTTP 200、1651 chunk、总耗时 39.9s、`done.success=True`、activity_type 答谢会——流式策划全链路经 nginx 无丢失无截断。

### 17.6 生产栈复用 dev 基础设施容器（同项目名共享网络）
- 两套 compose 同项目名 `huodongcehua`、共享默认网络：生产栈**直接复用**已运行的 mysql/redis/etcd/minio/milvus，不重复启动、不占宿主端口（这些端口留给 dev 栈 :5173/:8000 之外）。
- 启动顺序：`docker compose up -d`（基础设施）→ `cd frontend && npm run build` → `docker compose -f compose.prod.yml up -d --build`；停止自顶向下。

### 17.7 健康检查与启动顺序
- backend：`healthcheck`（GET `/api/v1/health`，15s/5s×5，start_period 30s）；nginx `depends_on backend: condition: service_healthy`——后端就绪前 nginx 不启动，避免流量打到未就绪副本。

### 17.8 横向扩容/缩容与内存（--scale + workers）
- 扩容：`docker compose -f compose.prod.yml up -d --scale backend=3`。
- **内存注意**：每 worker 各载一份 BGE 模型（~几百 MB）。默认 1 副本 × `--workers 2`；`--scale backend=2` 时 4 份模型。**2026-08-10 已缩回 1 副本**（`--scale backend=1`，backend-2 容器移除，生产栈保持运行）——用户决策：1 副本×2 worker 够用、省内存，多副本容灾当前阶段用不上。

### 17.9 冷启动首 chunk 慢
- **现象**：容器重启（Exited 2 天后重拉）后首次 SSE，首个 chunk 约 110s（正常 9s）。
- **根因**：容器冷启动，BGE 模型重新从镜像加载 + RAG 冷缓存（Milvus 连接初始化等）一次性成本，后续请求恢复。
- **结论**：属正常，不影响链路正确性；在线升级时此窗口无流式输出，可接受。

### 17.10 orphan 容器告警（正常现象）
- `docker compose ps`（dev）会把生产栈容器报为 orphan；反之 `compose.prod.yml` 把基础设施容器报为 orphan。两套 compose 共享项目名所致。
- **切勿**加 `--remove-orphans`——会误删另一套栈的容器。

### 17.11 已知事项与决策
- **文档模型名**：README/shuomingwendang 写 GLM-4.7，代码实际用 glm-4.6v（config 默认值/agents/evaluation 全部 4.6v，health 返回亦 4.6v）。**2026-08-10 用户决策暂不动**，保持现状。
- 临时探针 `_sse_probe.py` / `_sse_probe_result.txt` 已清理。

---

## 十八、工具统一注册表 + OpenAI 兼容客户端迁移（2026-08-14）

**背景**：工具无统一注册表——百度/博查各有一份手写 schema dict + `if/elif` executor，高德 MCP 动态加载自成一套；LLM 客户端直接用 `zhipuai` SDK（`ZhipuAI(api_key=...)`），且 `Config.ZHIPU_API_BASE` 定义了从未使用。目标：工具定义 provider 无关化 + LLM 客户端换官方 openai SDK。

### 18.1 工具统一注册表（backend/storage/external_tools.py）
- 新增 `ToolDef`（name / description / 纯 JSON Schema parameters / executor），单一 `_TOOLS` 注册表，两个工具一行绑定。
- 边界适配 `to_provider_tools(names)`：把注册表转成 OpenAI 兼容 `{"type":"function","function":{...}}`；`names` 可限定单节点可见工具，**未注册名抛 ValueError（fail-fast，接线配错应爆）**。
- 统一分派 `dispatch_tool(name, args)`：按名查注册表执行；**未知名返回错误串 `未知工具: {name}`（让 LLM 自纠，不抛异常）**。
- 删除两个手写 executor（`baidu_tool_executor` / `bocha_tool_executor`）与旧 schema dict（`BAIDU_POI_TOOL` / `BOCHA_SEARCH_TOOL`）。
- 高德 MCP 是会话内动态加载的工具，**不走静态注册表**，保持特殊路径；AMap 局部变量/措辞 `zhipu_tools`→`openai_tools`。

### 18.2 LLM 客户端换 openai SDK（backend/agents/agents.py）
- 导入守卫 `try: import openai; OPENAI_AVAILABLE = True`（删 zhipuai 子导入）。
- `LLMClient.__init__`：`openai.OpenAI(api_key=Config.LLM_API_KEY, base_url=Config.LLM_API_BASE, max_retries=0)`。
- **`max_retries=0` 关键**：openai SDK 默认对 429/5xx 内建重试 2 次，会绕过应用层 AdaptiveStagger/AIMD 退避造成不一致；关闭后限流完全由本层重试循环接管（见复盘 18）。
- `_is_rate_limit_error` 重映射：优先 `isinstance(exc, openai.RateLimitError)`，兜底 status_code==429 + 错误文本匹配（`429`/`速率限制`/`rate limit`），删 `_RATE_LIMIT_TYPES`/`_rate_limit_error_types()`。
- `_stream_collect` 流式桥零改动：openai **同步** `create(stream=True)` 返回同步迭代器，仍走「executor 线程 + asyncio.Queue」桥接。
- 两处调用点改注册表 API：supplier 节点 `to_provider_tools(["baidu_poi_search"])` + `dispatch_tool`；process 节点 `to_provider_tools(["bocha_search"])` + `dispatch_tool`。AMap 调用点不动。

### 18.3 配置改名（ZHIPU_* → LLM_*）
- `ZHIPU_API_KEY`→`LLM_API_KEY`、`ZHIPU_API_BASE`→`LLM_API_BASE`（env 可覆盖，默认 `https://open.bigmodel.cn/api/paas/v4`）。
- 涉及 config.py / .env / app.py（lifespan + health）/ cli/main.py（告警文案）/ test_workflow.py / PlanningInput.vue（文案）/ README / trouble.md 4.1。
- 全仓确认无 `ZHIPU_` 源码残留；仅 `frontend/dist` 构建产物含旧名（历史版本，重建 dist 后消失）。

### 18.4 兼容性确认（风险点验证）
- **reasoning_content 额外字段**：glm-4.6v 流式 delta 带 `reasoning_content`，openai 1.x 响应模型 pydantic `extra="allow"` 正常保留而非报错；推理阶段 `content=None` 已被现有 `if delta:` 跳过——live 实测无异常。
- **空 key 报错文案不同**：`openai.OpenAI(api_key="")` 构造即抛；正常入口已先 `Config.validate()` / lifespan 守卫。
- **Redis 缓存兼容**：缓存键按 model 不变，zhipuai 时代缓存仍有效（wire 格式相同），无需清。

### 18.5 验证结果（conda env `huodongcehua`，2026-08-14）
| 验证项 | 结果 |
|---|---|
| openai 1.109.1 安装 | ✅ |
| import + 注册表冒烟（fail-fast / dispatch 错误串） | ✅ |
| Config 改名检查（ZHIPU_* 已清除） | ✅ |
| live `chat()`（15 chunks 流式 + 真实返回） | ✅ |
| live `chat_with_tools()` + 百度 POI（FC 两轮循环，reasoning_content 无异常） | ✅ |
| `test_workflow.py` | ✅ 4/4 |

### 18.6 部署注意（下次部署时执行）
- **生产镜像需重建**：requirements 换成了 openai，旧镜像带 zhipuai、缺 openai，部署前必须 `docker compose -f compose.prod.yml build backend`。
- **前端 dist 需重建**：PlanningInput.vue 文案改了 `LLM_API_KEY`，`npm run build` 后旧名残留才消失。
