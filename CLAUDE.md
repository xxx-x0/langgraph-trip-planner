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

`run.py` 启动的是 [backend/app/api/main.py](backend/app/api/main.py) 中的 FastAPI 应用。

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

### 后端三个 LangGraph StateGraph

所有图定义在 [backend/app/agents/langgraph_agent/graph.py](backend/app/agents/langgraph_agent/graph.py)。节点实现拆分在 `nodes/`（cluster / discovery / food / generate / preferences / route / search），公共工具在 `utils/`（geo / parsing / route）。

- **`create_trip_planner_graph()`** — 主流程。从 START 并行扇出 `web_search_attractions` / `search_weather` / `search_hotel`，网页搜索后顺序 `extract_attractions` → `geocode_attractions`，在 `gather_search` 扇入汇聚；随后 `cluster_attractions` → `search_food` → `plan_route` → `macro_planner` → `day_plan_subgraph`（通过 LangGraph `Send` API 按天并行生成）→ `reduce_assemble` → `global_synthesizer` → `extract_preferences` → `save_preferences`。三种执行模式：一次性生成（`plan_trip`）、SSE 流式（`plan_trip_stream`）、人机交互（`start_interactive_plan` / `submit_feedback`，通过 `interrupt_before` 在反馈节点设置检查点）。

- **`create_discovery_graph()`** — 发现页专用。大量搜索景点并分批流式输出给前端供用户勾选：`web_search_attractions` → `extract_attractions_expanded` → `geocode_dispatch` → `geocode_batch`（分批循环）+ 并行的 `search_weather`，最后在 `gather_discovery` 汇聚。

- **`create_planning_graph()`** — 接收用户在发现页的勾选，跳过搜索直接从 `cluster_from_selections` 开始，后续合流主流程的 macro/day_plan/synthesizer 环节。

### API 路由

所有新路由以 `/api` 为前缀注册在 [backend/app/api/main.py](backend/app/api/main.py)：

- [routes/trip_lg.py](backend/app/api/routes/trip_lg.py) — 行程规划（一次性、SSE 流式、交互反馈、发现/基于选择的规划）
- [routes/poi_lg.py](backend/app/api/routes/poi_lg.py) — POI 查询
- [routes/map_lg.py](backend/app/api/routes/map_lg.py) — 地图、地理编码、路线
- [routes/trip_history.py](backend/app/api/routes/trip_history.py) — 行程历史 CRUD

旧 HelloAgents 框架的 `trip` / `poi` / `map` 路由和 `trip_planner_agent.py` 已弃用（在 `.gitignore` 中忽略，保留文件仅供参考）。

### 外部服务（MCP 协议）

所有外部数据源通过 Model Context Protocol 适配器接入：
- **高德地图 (AMap)** — 地图、POI、天气、地理编码、路线规划（[services/langchain_amap_tools.py](backend/app/services/langchain_amap_tools.py)）
- **AIGoHotel** — 酒店搜索，经由 ModelScope（[services/aigohotel_mcp_service.py](backend/app/services/aigohotel_mcp_service.py)）
- **Bing** — 网页搜索，经由 ModelScope（[services/bing_mcp_service.py](backend/app/services/bing_mcp_service.py)）

三个 MCP 服务共享相同的弹性模式：模块级异步单例、`asyncio.Lock` 线程安全、连接错误自动重连、`asyncio.wait_for` 超时控制。

其他服务：[trip_history_service.py](backend/app/services/trip_history_service.py) 封装行程历史 CRUD；[unsplash_service.py](backend/app/services/unsplash_service.py) 从 Unsplash 拉取景点封面图；[preferences_service.py](backend/app/services/preferences_service.py) 负责偏好加权合并与持久化。

### LLM 配置

默认 LLM 为 DeepSeek，通过 OpenAI 兼容 API 接入（配置在 `backend/.env`）。[llm_service.py](backend/app/services/llm_service.py) 中的 `is_structured_output_supported()` 会检测不支持结构化输出的模型（DeepSeek、Qwen 等），自动回退到 JSON-in-prompt 解析。

### 状态管理

- **后端**：`TripPlannerState` 与 `DiscoveryState` TypedDict（[state.py](backend/app/agents/langgraph_agent/state.py)），使用 `Annotated` 字段配合 `operator.add` reducer 实现并发安全的列表累加。交互模式通过 `AsyncSqliteSaver` 将状态检查点存入 SQLite。
- **前端**：无 Vuex/Pinia。使用组件局部 `ref`/`reactive` 状态，全局主题通过 `useTheme` composable 管理（持久化到 localStorage）。

### 关键模式

- **降级方案生成**：[utils/parsing.py](backend/app/agents/langgraph_agent/utils/parsing.py) 在 LLM/MCP 调用失败时，始终能从已收集的部分数据生成降级行程。
- **偏好学习循环**：每次行程结束后，通过 LLM 提取用户偏好，与已有偏好加权合并（`preferences_service.py`），下次规划时由 `load_user_preferences_node` 自动加载。
- **SSE 流式传输**：前端使用原生 `fetch` + `ReadableStream` 解析后端流式端点返回的 `data:` 行（[services/api.ts](frontend/src/services/api.ts)）。

### 数据库

异步 SQLAlchemy + aiosqlite，两个 SQLite 数据库：
- `backend/data/trips.db` — 行程历史和用户偏好（ORM 模型在 [models/db_models.py](backend/app/models/db_models.py)）
- `backend/data/checkpoints.db` — LangGraph 交互模式状态检查点

## 前端

路由在 [frontend/src/main.ts](frontend/src/main.ts)：`/`（Home）、`/result`（Result）、`/discover`（DiscoverView）、`/my-trips`（MyTrips）、`/trip/:id`（Result 复用，props 模式）。UI 库使用 Ant Design Vue。

### Result 视图拆分

[views/Result.vue](frontend/src/views/Result.vue) 仅作为外壳（Hero + Tab Bar + Transition），实际内容拆入 [components/result/](frontend/src/components/result/)：`ResultHero`、`TabOverview`、`TabItinerary`、`TabBudget`、`TabMap`、`TabWeather`。导出图片 / PDF 时会切到 `isExporting` 将所有 Tab 同时渲染。

### 发现 → 规划流

[views/DiscoverView.vue](frontend/src/views/DiscoverView.vue) 调用 discovery SSE 接口，分批展示景点；[components/DiscoveryMap.vue](frontend/src/components/DiscoveryMap.vue) 负责地图可视化，[components/SelectableAttractionCard.vue](frontend/src/components/SelectableAttractionCard.vue) 支持勾选与按天分配；用户确认后调用 planning 接口进入 Result。

## 无认证

应用使用简单的 `user_id` 字符串（默认 `"default"`）进行偏好追踪，无认证层。
