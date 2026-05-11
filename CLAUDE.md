# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此仓库中工作时提供指引。

## 开发命令

### 后端 (Python/FastAPI)
```bash
cd backend
pip install -r requirements.txt          # 安装依赖
python run.py                             # 启动开发服务器 (uvicorn, 端口 8000, 热重载)
pytest                                    # 运行全部测试
pytest tests/agents/test_trip_planner.py  # 运行单个测试文件
pytest -k "test_parse"                    # 按名称匹配运行测试
```

### 前端 (Vue 3/Vite)
```bash
cd frontend
npm install                # 安装依赖
npm run dev                # 启动开发服务器 (端口 5173, /api 代理到后端 8000)
npm run build              # 类型检查 (vue-tsc) + 生产构建，输出到 dist/
npm run preview            # 预览生产构建
```

前后端需同时运行。Vite 开发服务器会将所有 `/api` 请求代理到后端。

## 架构

两层架构：Vue 3 SPA 前端 → FastAPI 后端，核心由 LangGraph Agent 编排行程规划。

### 后端核心：LangGraph StateGraph

规划工作流是一个 DAG，定义在 `backend/app/agents/langgraph_agent/graph.py`。执行流程：

1. 从 START **并行扇出**：`web_search_attractions`、`search_weather`、`search_hotel` 并发执行
2. `extract_attractions` → `geocode_attractions`（网页搜索后顺序执行）
3. 在 `gather_search` **扇入汇聚**
4. `cluster_attractions` → `search_food` → `plan_route`
5. `macro_planner` → `day_plan_subgraph`（通过 LangGraph `Send` API 按天并行生成）→ `reduce_assemble`
6. `global_synthesizer` → `extract_preferences` → `save_preferences`

三种执行模式：一次性生成（`plan_trip`）、SSE 流式（`plan_trip_stream`）、人机交互（`start_interactive_plan` / `submit_feedback`，通过 `interrupt_before` 在反馈节点设置检查点）。

### 外部服务（MCP 协议）

所有外部数据源通过 Model Context Protocol 适配器接入：
- **高德地图 (AMap)** — 地图、POI、天气、地理编码、路线规划（`backend/app/services/langchain_amap_tools.py`）
- **AIGoHotel** — 酒店搜索，经由 ModelScope（`backend/app/services/aigohotel_mcp_service.py`）
- **Bing** — 网页搜索，经由 ModelScope（`backend/app/services/bing_mcp_service.py`）

三个 MCP 服务共享相同的弹性模式：模块级异步单例、`asyncio.Lock` 线程安全、连接错误自动重连、`asyncio.wait_for` 超时控制。

### LLM 配置

默认 LLM 为 DeepSeek，通过 OpenAI 兼容 API 接入（配置在 `backend/.env`）。`backend/app/services/llm_service.py` 中的 `is_structured_output_supported()` 会检测不支持结构化输出的模型（DeepSeek、Qwen 等），自动回退到 JSON-in-prompt 解析。

### 状态管理

- **后端**：`TripPlannerState` TypedDict（`backend/app/agents/langgraph_agent/state.py`），使用 `Annotated` 字段配合 `operator.add` reducer 实现并发安全的列表累加。交互模式通过 `AsyncSqliteSaver` 将状态检查点存入 SQLite。
- **前端**：无 Vuex/Pinia。使用组件局部 `ref`/`reactive` 状态，全局主题通过 `useTheme` composable 管理（持久化到 localStorage）。

### 关键模式

- **降级方案生成**：`backend/app/agents/langgraph_agent/utils/parsing.py` 在 LLM/MCP 调用失败时，始终能从已收集的部分数据生成降级行程。
- **偏好学习循环**：每次行程结束后，通过 LLM 提取用户偏好，与已有偏好加权合并（`backend/app/services/preferences_service.py`），下次规划时自动加载。
- **SSE 流式传输**：前端使用原生 `fetch` + `ReadableStream` 解析后端流式端点返回的 `data:` 行（`frontend/src/services/api.ts`）。

### 数据库

异步 SQLAlchemy + aiosqlite，两个 SQLite 数据库：
- `backend/data/trips.db` — 行程历史和用户偏好（ORM 模型在 `backend/app/models/db_models.py`）
- `backend/data/checkpoints.db` — LangGraph 交互模式状态检查点

### 无认证

应用使用简单的 `user_id` 字符串（默认 `"default"`）进行偏好追踪，无认证层。
