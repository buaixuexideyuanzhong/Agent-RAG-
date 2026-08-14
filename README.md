# 活动策划多智能体系统

基于 **LangGraph** 和 **智谱 AI GLM-4.7** 的活动策划多智能体协作系统。

## 🏗️ 架构设计

采用 **3 个搜索 Agent + 1 个 Planner Agent** 的多智能体协作架构：

```
用户请求 → 需求提取 → [并行搜索] → 方案整合 → 输出
                     ↙     ↓     ↘
                 场地   商家   流程
                 搜索   搜索   参考
```

### 智能体说明

| Agent | 职责 | 模型 |
|-------|------|------|
| **Planner Agent** | 需求提取、任务分发、结果整合、方案生成 | GLM-4.7 |
| **场地搜索 Agent** | 搜索合适的活动场地（酒店、会议中心等） | GLM-4.7 |
| **商家搜索 Agent** | 搜索供应商和商家（餐饮、搭建、设备等） | GLM-4.7 |
| **流程参考 Agent** | 检索相似活动案例和流程模板 | GLM-4.7 |

## 🏃 整体运行流程

系统为**三层架构**：`Docker 基础设施`（数据/向量/缓存）→ `后端 FastAPI`（业务 + 多智能体）→ `前端 Vue`（Web 界面）。启动必须**自底向上**（基础设施 → 后端 → 前端），停止**自顶向下**。

```
┌───────────────────────────────────────────────────────────────┐
│ 前端  Vue 3 + Vite  :5173     http://localhost:5173           │
│   需求输入 → SSE 流式输出 → 方案查看/复制 → 保存到案例库      │
│   /api/* 由 Vite 代理转发到 127.0.0.1:8000（同源免 CORS）     │
├───────────────────────────────────────────────────────────────┤
│ 后端  FastAPI + LangGraph  :8000                              │
│   /api/v1/health · /plan · /plan/stream(SSE) · /cases         │
│   多智能体：需求提取 → 3 个搜索并行 → 方案整合                 │
├───────────────────────────────────────────────────────────────┤
│ 基础设施  Docker Compose（5 容器）                            │
│   MySQL 3306  案例全文+元数据      Redis 6379  缓存层          │
│   Milvus 19530 案例向量检索(RAG)   etcd+minio  Milvus 依赖    │
└───────────────────────────────────────────────────────────────┘
```

### 第 1 步：启动基础设施（Docker）

```bash
docker compose up -d    # 项目根目录
docker compose ps       # 5 个容器应全部 Up
```

| 容器 | 端口 | 用途 |
|------|------|------|
| mysql:8.0 | 3306 | 案例库（root/123456，库 event_planner） |
| redis:7 | 6379 | LLM/工具/embedding/热案例缓存 |
| milvus:v2.3.3 | 19530 / 9091 | 案例向量检索（standalone 依赖 etcd+minio） |
| etcd | 2379 | Milvus 元数据 |
| minio | 9000 | Milvus 对象存储 |

数据持久化在 Docker volume，`docker compose down` 不丢数据。

### 第 2 步：启动后端（FastAPI）

后端依赖安装在 conda 环境 `huodongcehua`（Python 3.10），**不要用默认 `python`**（会指向 base 环境导致缺包）：

```bash
conda activate huodongcehua
uvicorn backend.api.app:app --port 8000     # 开发可加 --reload
```

验证：访问 http://127.0.0.1:8000/api/v1/health 返回 `{"status":"ok",...}`。

### 第 3 步：启动前端（Vue 3 + Vite）

```bash
cd frontend
npm install      # 仅首次
npm run dev      # http://localhost:5173
```

打开 **http://localhost:5173** 即可使用。

### 完整请求数据流

```
页面输入需求
 → POST /api/v1/plan/stream（SSE）
 → 需求提取节点（GLM → 活动类型/人数/预算/城市…）
 → 三个搜索 Agent 并行（LangGraph 并行节点）
     场地：高德/百度 POI   商家：高德/百度   流程：RAG 案例检索 + 博查 + LLM 兜底
 → 方案整合节点（GLM 流式生成完整方案）
 → SSE chunk 逐字推回前端，done 事件带完整 PlanResponse
 → 前端渲染 markdown 方案 + 需求摘要 + 场地/商家/流程详情
 → 用户"保存到案例库" → POST /api/v1/cases
     → MySQL 全文 + Milvus 向量 + Redis 热案例
 → 下次策划时 RAG 检索同类型案例，流程参考更精准
```

### 停止 / 重启

```bash
docker compose down            # 停基础设施（volume 数据保留）
docker compose up -d           # 重启基础设施

# 重启后端 / 前端：Ctrl+C 后重新执行第 2/3 步命令即可
```

> 💡 后端对 MySQL/Milvus 采用 **30 秒冷却自动重探**：即使后端先于 Docker 启动，基础设施就绪后 30 秒内自动重连，无需重启进程。

## 🏭 生产部署（Nginx 负载均衡）

> 开发形态（单后端 + Vite 代理）适合日常开发；对外发布时用本方案：**Nginx 统一入口**（前端静态托管 + `/api` 反向代理 + 负载均衡），后端多 worker / 多副本。

```
浏览器 ── http://localhost:8080
  │
  ▼
nginx 容器 (:8080)
  ├── /      → 前端静态产物（frontend/dist）
  └── /api   → 后端负载均衡
                 ├── backend 容器（uvicorn --workers N，多进程）
                 ├── …（--scale backend=N 时可加多个副本，nginx 自动轮询）
                 └── 基础设施复用 dev 的容器（mysql/redis/milvus，同网络）
```

### 启动步骤

```bash
# 0) 前置：基础设施已起（未起则先）
docker compose up -d

# 1) 构建前端静态产物（nginx 托管的就是这个）
cd frontend
npm run build

# 2) 构建并启动生产栈
cd ..
docker compose -f compose.prod.yml up -d --build

# 3) 访问
http://localhost:8080
```

### 关键机制

- **负载均衡两层**：每节点 `uvicorn --workers N`（默认 2，`UVICORN_WORKERS` 可调）多进程并行；跨节点由 nginx 通过 Docker 内嵌 DNS 对 `backend` 服务名轮询解析（`resolver 127.0.0.11 valid=1s`）——`docker compose -f compose.prod.yml up -d --scale backend=3` 即可横向扩容，无需改配置。分发模型是"按 1s 缓存窗口切换节点"：SSE 长连接全程粘在同一节点（必要），间隔数秒的新会话才会轮转到不同副本，适合本系统的长流式负载。
- **SSE 兼容**：`/api/v1/plan/stream` 在 nginx 中关闭了缓冲（`proxy_buffering off`），流式内容逐字实时透传，读超时给足 300s。
- **配置注入**：宿主 `.env` 经 `env_file` 整体注入后端容器；容器内网络地址在 `compose.prod.yml` 里覆盖为服务名（`DB_HOST=mysql`、`REDIS_URL=redis://redis:6379/0`、`VECTOR_DB_URL=http://milvus:19530`）。
- **静态缓存**：带 hash 的 js/css 资源 `expires 7d` + `immutable`；SPA 路由回退 `index.html`。

### 说明与注意事项

| 事项 | 说明 |
|---|---|
| 镜像体积 | 后端镜像含 CPU 版 torch（sentence-transformers 依赖），约 2-3GB，首次构建慢；国内 pip 慢时加 `--build-arg PIP_INDEX_URL=<镜像源>` |
| 内存 | 每个 uvicorn worker 会各自加载一份 BGE embedding 模型（约 100-250MB），`--workers` 和 `--scale` 别开太大 |
| BGE 模型 | 首次调用时从 HuggingFace 下载，走 `.env` 的 `HF_ENDPOINT` 镜像 |
| 与 dev 共存 | 生产栈复用基础设施容器、共享默认网络，不冲突；nginx 占 8080 端口 |
| 更新前端 | 重新 `npm run build` 后 `docker compose -f compose.prod.yml restart nginx` 即可 |
| 更新后端 | 改代码后重新 `docker compose -f compose.prod.yml up -d --build backend` |

## 📦 项目结构

```
huodongcehua/
├── backend/               # 后端代码（FastAPI + 多智能体 + 存储）
│   ├── api/               #   API 层：app.py（FastAPI 入口）
│   ├── core/              #   基础：config / models / state
│   ├── agents/            #   多智能体：agents / workflow
│   ├── storage/           #   存储：cache / database / embedder /
│   │                      #          external_tools / rag_knowledgebase
│   └── cli/               #   CLI：main.py（控制台入口）
├── frontend/              # 前端（Vue 3 + Vite，策划主页面）
│   ├── src/components/    #   PlanningInput / PlanViewer / LogPanel / HealthBadge…
│   ├── src/composables/   #   usePlanner / useHealth / useToast
│   └── src/api/           #   plan(SSE) / cases / health / http 封装
├── docker-compose.yml     # 基础设施：redis / mysql / etcd / minio / milvus
├── compose.prod.yml       # 生产部署：nginx + 多 worker 后端 + 前端托管（见「生产部署」）
├── deploy/
│   └── nginx/             # Nginx 镜像：nginx.conf（前端托管 + /api 负载均衡 + SSE 透传）
├── backend/Dockerfile     # 后端生产镜像（Python 3.10 + torch/BGE）
├── requirements.txt       # Python 依赖包
├── shuomingwendang.md     # 技术方案文档
└── README.md              # 项目说明（本文件）
```

## 🧪 快速开始（CLI 模式）

> Web 方式（浏览器策划）的完整启动流程见上文「🏃 整体运行流程」；本节为命令行模式。

### 1. 安装依赖

```bash
conda activate huodongcehua        # Python 3.10 环境
pip install -r requirements.txt
```

### 2. 配置 API Key

获取智谱 AI API Key：https://open.bigmodel.cn

设置环境变量：

```bash
# Linux/Mac
export LLM_API_KEY=your_api_key_here

# Windows PowerShell
$env:LLM_API_KEY="your_api_key_here"

# Windows CMD
set LLM_API_KEY=your_api_key_here
```

或直接在 [backend/core/config.py](backend/core/config.py) 中修改：

```python
LLM_API_KEY: str = "your_api_key_here"
```

### 3. 运行程序

#### 交互式对话模式（推荐）

```bash
python -m backend.cli.main
```

#### 单次请求模式

```bash
python -m backend.cli.main --mode single --request "帮我策划一个500人的公司年会，预算20万，地点在北京"
```

#### 使用预设示例

```bash
python -m backend.cli.main --mode example --example-index 1
```

#### 查看工作流信息

```bash
python -m backend.cli.main --workflow-info
```

#### 生成工作流可视化图

```bash
python -m backend.cli.main --visualize
```

## 🌐 后端 API（FastAPI，前后端分离）

后端以 FastAPI 提供 HTTP API，前端已实现（Vue 3 + Vite，见 `frontend/`）。后端完整暴露当前系统的能力：策划（普通 JSON + SSE 流式）、案例知识库、健康检查。Web 页面经 Vite 代理调用，也可用 curl / Postman 直连。

### 启动后端

```bash
# 安装依赖（需 fastapi / uvicorn / python-multipart）
pip install -r requirements.txt

# 启动开发服务器（自动重载）
uvicorn backend.api.app:app --reload --port 8000
```

启动后：
- Swagger 文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/v1/health

### API 端点一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/health` | 服务状态、API key、工具 key、基础设施开关 |
| POST | `/api/v1/plan` | 单次策划，返回完整 JSON |
| POST | `/api/v1/plan/stream` | SSE 流式策划（方案实时推送） |
| GET | `/api/v1/cases` | 案例列表（`?limit=`） |
| POST | `/api/v1/cases` | 保存案例到知识库 |
| DELETE | `/api/v1/cases/{case_id}` | 删除案例 |
| POST | `/api/v1/cases/import` | 上传文件批量导入（json/txt/md） |
| GET | `/api/v1/workflow` | 工作流结构信息 |

### 调用示例

```bash
# 单次策划
curl -X POST http://127.0.0.1:8000/api/v1/plan \
  -H "Content-Type: application/json" \
  -d '{"request":"帮我策划一个100人的客户答谢会，预算10万，广州天河"}'

# SSE 流式策划（-N 实时观察 chunk）
curl -N -X POST http://127.0.0.1:8000/api/v1/plan/stream \
  -H "Content-Type: application/json" \
  -d '{"request":"策划一个200人的产品发布会，预算50万，上海浦东"}'

# 保存案例
curl -X POST http://127.0.0.1:8000/api/v1/cases \
  -H "Content-Type: application/json" \
  -d '{"plan_text":"完整方案正文","metadata":{"activity_type":"年会","city":"北京","attendee_count":500}}'

# 文件导入案例
curl -X POST http://127.0.0.1:8000/api/v1/cases/import \
  -F "file=@sample_cases.json"
```

### 流式事件格式

`POST /api/v1/plan/stream` 返回 `text/event-stream`，事件为 JSON：

```json
data: {"type":"chunk","delta":"方案生成中的一段文本"}
data: {"type":"done","result":{ "success": true, "plan": "完整方案", "requirements": {...}, ... }}
```

## 💡 使用示例

```python
import asyncio
from backend.cli.main import ActivityPlanner

async def main():
    planner = ActivityPlanner()

    result = await planner.plan(
        "帮我策划一个500人的公司年会，"
        "预算20万，地点在北京朝阳，"
        "时间是下个月中旬"
    )

    if result["success"]:
        print("策划方案:")
        print(result["plan"])
    else:
        print("策划失败:", result["error"])

asyncio.run(main())
```

## 📋 输出格式

系统会生成完整的活动策划方案，包含：

1. **活动概述** - 主题、目标、时间、地点
2. **详细流程安排** - 时间轴
3. **场地配置方案** - 推荐场地详情
4. **商家资源配置** - 各类供应商信息
5. **预算明细表** - 分项成本明细
6. **任务清单** - 负责人和时间节点
7. **风险提示** - 注意事项和避坑指南

## 🔧 配置说明

在 [backend/core/config.py](backend/core/config.py) 中可以配置：

- `LLM_API_KEY`: LLM API 密钥（OpenAI 兼容端点，默认智谱开放平台）
- `LLM_API_BASE`: LLM API 地址（可选，默认 `https://open.bigmodel.cn/api/paas/v4`）
- `PLANNER_MODEL`: Planner Agent 使用的模型（默认：glm-4.7）
- `SEARCHER_MODEL`: 搜索 Agent 使用的模型（默认：glm-4.7）
- `ENABLE_PARALLEL`: 是否启用并行调用
- `LOG_LEVEL`: 日志级别（DEBUG/INFO/WARNING/ERROR）

## 📚 技术栈

- **LLM**: 智谱 AI GLM（glm-4.6v）
- **多智能体框架**: LangGraph
- **后端**: FastAPI + Uvicorn（Python 3.10+，conda 环境 `huodongcehua`）
- **前端**: Vue 3 + Vite（JavaScript）
- **基础设施**: Docker Compose（MySQL 8 / Redis 7 / Milvus 2.3 / MinIO / etcd）
- **并发**: asyncio

## 🎯 预设示例

1. 500人公司年会，预算20万，北京
2. 200人产品发布会，预算50万，上海
3. 100人客户答谢会，预算10万，广州
4. 300人培训会，预算15万，深圳

## 📖 相关文档

- [技术方案文档](shuomingwendang.md)
- [智谱 AI 文档](https://open.bigmodel.cn/dev/api)
- [LangGraph 文档](https://langchain-ai.github.io/langgraph)

## 🐛 问题反馈

如遇到问题，请检查：

1. API Key 是否正确配置
2. 网络连接是否正常
3. 依赖包是否完整安装

## 📝 开发计划

- [x] 集成真实的场地和商家数据 API（高德 / 百度 POI / 博查搜索）
- [x] 添加向量数据库支持案例检索（Milvus + 本地 BGE embedding）
- [x] 开发 Web 前端界面（Vue 3，SSE 流式策划）
- [ ] 实现多轮对话和方案修改
- [ ] 案例库管理页（列表 / 检索 / 删除）
- [ ] 添加方案导出功能（PDF/Word）

## 📄 许可证

MIT License