# 前端（Vue 3 + Vite）

活动策划多智能体系统的 Web 前端，提供**策划主页面**：
- 自然语言需求输入（含示例请求、字数校验）
- SSE 流式策划输出（打字机效果，中文标题/表格/代码渲染）
- 执行日志 + 注意事项面板
- 需求摘要 chips + 场地/商家/流程详情折叠面板
- 复制方案、保存到案例库
- 顶部健康状态角标（自动轮询 / 点击刷新）

## 技术栈

- Vue 3（Composition API + `<script setup>`）+ Vite
- marked + DOMPurify（markdown 渲染与消毒）
- 手写 fetch + ReadableStream 的 SSE 解析（无 UI 组件库、无 Pinia）

## 启动

前置：后端已启动（项目根目录 `uvicorn backend.api.app:app --reload --port 8000`）。

```bash
cd frontend
npm install      # 首次
npm run dev      # 开发服务器，http://localhost:5173
```

Vite dev 代理把 `/api` 转发到 `http://127.0.0.1:8000`，保持同源、规避 CORS。
如需直连后端（不走代理），复制 `.env.local.example` 为 `.env.local` 并填 `VITE_API_BASE`。

## 目录结构

```
frontend/
├── index.html
├── vite.config.js            # /api → 127.0.0.1:8000 代理
├── .env.local.example        # VITE_API_BASE 逃生舱
└── src/
    ├── main.js / App.vue / constants.js
    ├── api/                  # http 封装 + health / plan(SSE) / cases
    ├── composables/          # usePlanner（状态机）/ useHealth / useToast
    ├── utils/                # sse 帧解析 / markdown 渲染 / 格式化
    ├── styles/main.css
    └── components/           # HealthBadge / PlanningInput / PlanViewer / LogPanel / ToastHost
```

## 说明

- 流式接口 POST `/api/v1/plan/stream` 只推 `chunk`，`messages/errors/详情` 在 `done` 事件返回，因此日志面板在流式期间显示占位动画、完成后一次性填充。
- SSE 无心跳，后端搜索阶段可能静默 30~60s，前端采用 150s 无数据超时（有帧即续命）。
- 后端接口契约与响应结构见项目根目录 [README.md](../README.md)。
