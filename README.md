# 智能旅行规划助手 🌍✈️

基于 **LangGraph + LangChain** 框架构建的智能旅行规划助手，通过 MCP 协议接入高德地图云服务，提供个性化的多日旅行计划生成。

当前支持本机单用户的单城市旅行，以及5～10天、2～3城市的整趟旅行；多城市入口为 `/multi-trip/:id?`。正式目标和首批待办见 Nexo LTP（本机内部记录，链接未公开），景点锁定、删除、恢复规则及模拟故障证据见 [LTP-3 交接](docs/ltp3-handoff.md)。2026-10-13 已用真实 DeepSeek、高德和酒店服务完成苏州两日发现至历史回读，运行前提、耗时、修复及五类建议质量限制见 [LTP-5 交接](docs/ltp5-handoff.md)。两项均留待用户判断；没有代用户通过验收，预算与旅行建议仍须核对。

2026-10-14 已完成 LTP-6 依赖锁定、未知费用/住宿晚数、实际用餐时段及定稿原子保存，详见 [LTP-6 交接](docs/ltp6-handoff.md)。后端200项、前端41项回归通过，另4项外部smoke跳过；真实两日行程已复验，费用仍有缺项。LTP-3/5/6 由用户验收，尚未自动认定通过。后续顺序与验收条件见 [重构路线图](docs/refactor-roadmap.md)，Nexo使用故障和体验反馈见 [台账](docs/nexo-usage-log.md)。

同日按用户授权完成LTP-2/7外部服务统一与失败恢复，见 [交接](docs/ltp2-ltp7-handoff.md) 和 [调用配置](docs/external-services.md)。后端236项、前端49项通过，4项smoke跳过，类型检查与构建通过；真实两日规划、编辑、定稿及重复请求53项对照通过。Bing上游实际拒绝请求、网页抓取未实测，不能据此认定所有外部服务可用。保留所有未提交改动，USER验收以Nexo记录为准。

LTP-8按用户确认停用隐式历史偏好注入，本次选择为规划依据；统一图状态与入口，清理旧依赖，见 [交接](docs/ltp8-handoff.md)。全新隔离环境锁定75项且保留版本未升级，后端246项、前端49项通过，4项smoke跳过；真实两日58项核对通过，冲突历史未读入规划、明确偏好未被覆盖。主动采用的表单预填留后续。

LTP-10已修复编辑后旧叙述沿用：说明随保存的顺序、时刻、天气和费用缺项自动更新，定稿再核对；迟到的同日修改返回冲突并加载最新草稿。旧结果页编辑统一迁至草稿，旧记录只读投影，框架和锁定依赖保持不变，见 [交接](docs/ltp10-handoff.md)。

LTP-11继续修复删除后的用餐位置和AI漏餐：保留原手动用餐间隙与auto餐次，AI不默默减少已有正餐，有效位置保留；实际路线核对失败保留旧安排并明确提示。新增或减少餐次仍由用户在草稿中选择，见 [交接](docs/ltp11-handoff.md)。

2026-10-19修复12306站点分隔符导致的预填故障，并提供本机浏览器查票助手开发版：限定列表字段带回、AI筛选及一键采用预览，见[LTP-26交接](docs/ltp26-handoff.md)与[扩展安装说明](browser-extension/README.md)。扩展需手动安装；0.1.1已在Chrome完成高铁及登录后航班的查询→真实AI→自动回填→预览→保存回读。回归、早期模型留样与真实实装分开留证；仅覆盖部分直达候选。旧版适配缺口见[失败实测](docs/ltp26-existing-itinerary-handoff.md)；2026-10-20 LTP-27已在推荐前按已存日程与缓冲过滤冲突，0.2.0实装同一苏杭样本默认查询无需手动筛晚班即可采用保存，见[修复交接](docs/ltp27-handoff.md)。后续0.2.1修复80条后航班加载、合并ID及旧推荐撤销，并显示当前缓冲外时间余量；465后端/145前端及构建通过，旧事实离线回放46项通过。用户重载0.2.1后默认铁路80/航班74条，经实际AI和UI采用保存刷新239项字段核对通过；满80航班等边界仍为模拟，真人体验由用户判断，见[最新交接](docs/ltp26-ltp27-followup.md)。

<a id="verification-baseline"></a>
## 当前维护与验证基线（2026-10-24）

本文档按已提交源码 `3b3a93c` 核对；API有52个OpenAPI路径（不是HTTP方法数），三个图节点数为14/3/5。对应隔离源码验证为后端623通过、4项外部smoke跳过，前端239通过、构建通过；本轮文档审查没有重做网站、模型、酒店或地图实测，也不把历史通过数字改成新的实时结果。

源码扩展版本为0.2.2；0.2.1真实Chrome实装证据与0.2.2隔离自动化边界测试分开，Edge和0.2.2重新实装未在本轮完成。生成ZIP由前端predev/prebuild自动打包并忽略；本机现存旧ZIP保留，不由文档检查覆盖。

各LTP交接、价值基线、路线图和Nexo台账是带日期的历史记录，其中“无Git提交”、端口、测试数及USER状态只表示当时情况；不据此推断当前仍未提交或用户已验收。`output/`、`.playwright-cli/`、仓库外本机路径和localhost链接仅是本地证据/应用位置，克隆仓库不会自动取得；本轮仅核对可用本机证据，不将代理记录当独立真人验收。第二批不纳入正在独立进行的观测/评估源码及其两份新文档。

公开文档保留架构、配置和历史验证结论；本机绝对路径、内部工作项链接及实例 ID 已脱敏。`${PROJECT_ROOT}` 表示自行设置的仓库根目录，`${EVIDENCE_ROOT}` 表示未公开的本机证据归档目录，`${USER_HOME}` 表示用户目录；涉及这些变量的历史命令需配置实际路径和隔离环境后使用。`sample-trip-*` / `sample-draft-*` / `internal-record-*` 仅为跨文档对应标签，不是可调用的真实 ID。私有 Nexo 工具示例的 `${NEXO_BASE_URL}` 需自行设置。原始证据、设计提示词与生成产物不随仓库发布。

酒店与 Bing MCP 没有共享默认地址；需要使用时，在本地 `backend/.env` 设置自己的 `AIGOHOTEL_MCP_URL`、`BING_MCP_URL`，不要提交真实服务入口。未配置时沿用现有的配置缺失及降级处理。

手动验证的保留脚本、作用范围和排除脚本见[运行说明](backend/tests/manual/README.md)。在线API脚本不自动执行，普通回归与本机业务数据库保持隔离。

> **重构说明**：本项目原始版本基于 [HelloAgents](https://github.com/jjyaoao/HelloAgents) 框架构建，现已完整重构为 LangGraph + LangChain 技术栈。重构涵盖 Agent 工作流、MCP 工具调用层、API 路由层，实现了从同步到异步、从单 Agent 到多节点协作图的架构升级。

## ✨ 功能特点

- 🧩 **LangGraph 多节点协作**：发现图并行查景点和天气；骨架图并行查餐饮与酒店，后续由草稿编辑和定稿流水线完成行程
- 🔌 **LangChain 原生 MCP 适配**：通过 `langchain-mcp-adapters` 连接高德官方 MCP 云服务（SSE 传输），无需本地安装 uvx/Node.js
- 🤖 **LLM 驱动的工具调用**：LLM参与编排、AI选景/重排和候选推荐；地点、路线、天气及报价事实来自受控外部工具。每日说明与定稿标题直接投影结构化事实
- 🛡️ **失败恢复**：统一调用总期限、取消、最多2次尝试、连接恢复与脱敏观测；流中断明确提示，保留选择与已保存草稿，重试避免重复历史
- 🎨 **现代化前端**：Vue 3 + TypeScript + Vite，响应式设计，流畅的用户体验
- 📱 **完整功能**：包含住宿、交通、餐饮和景点游览时间推荐

## 🔄 重构对比

| 维度 | 旧版 (HelloAgents) | 新版 (LangGraph) |
|---|---|---|
| Agent 框架 | HelloAgents `SimpleAgent` | LangGraph `StateGraph` |
| 工作流 | 旧Agent顺序执行 | 完整规划图、发现图、骨架图，另有草稿编辑与独立定稿流水线 |
| MCP 工具 | `hello_agents.MCPTool`（Stdio） | `langchain-mcp-adapters`（AMap/Bing为SSE，酒店为Streamable HTTP） |
| 调用方式 | 同步 `agent.run()` | 异步 `await graph.ainvoke()` |
| LLM | `HelloAgentsLLM` | LangChain `ChatOpenAI` |
| 路线工具 | `*_by_address`（传地址文本） | `maps_direction_*`（传经纬度坐标 + 自动 geocode） |
| 并发能力 | 顺序执行，无并发 | 景点/天气并行；酒店/餐饮并行；完整规划图按天Send |
| 错误处理 | 基础 try/catch | 重试机制 + 超时配置 + 备用计划 |

## 🏗️ 技术栈

### 后端
- **Agent 框架**: LangGraph（多节点状态图）
- **MCP 适配**: langchain-mcp-adapters（SSE 传输 → 高德官方云服务）
- **LLM**: LangChain ChatOpenAI（支持 OpenAI / DeepSeek 等）
- **API**: FastAPI
- **语言**: Python；本机安装/回归验证基线为3.12.13，全异步

### 前端
- **框架**: Vue 3 + TypeScript
- **构建工具**: Vite
- **UI 组件库**: Ant Design Vue
- **地图服务**: 高德地图 JavaScript API
- **HTTP 客户端**: Axios

## 📁 项目结构

```text
langgraph-trip-planner/
├── backend/
│   ├── app/
│   │   ├── agents/langgraph_agent/
│   │   │   ├── graph.py          # 完整规划、发现、骨架三个图
│   │   │   ├── nodes/            # 图节点
│   │   │   ├── assemble/         # 草稿路线、时段、预算、叙述
│   │   │   └── finalize/         # 定稿流水线
│   │   ├── api/main.py          # 注册当前API
│   │   ├── api/routes/          # trip_lg、trip_draft、trip_history等
│   │   ├── models/state.py      # 唯一图状态声明
│   │   ├── models/schemas.py    # API与行程模型
│   │   └── services/            # 外部调用、草稿/历史/兼容观察保存
│   ├── requirements.txt
│   └── requirements.lock.txt
├── frontend/src/                 # Vue页面、组件及SSE客户端
├── CONTEXT.md                    # 本次选择、明确偏好与历史观察术语
└── docs/architecture.md          # 当前图、API、状态和保存边界
```

## 🔧 LangGraph 工作流

当前页面走“本次需求 → 发现与选择 → 骨架草稿 → 每日装配/编辑 → 定稿 → 历史”。三个实际图、API入口及兼容路径见 [架构说明](docs/architecture.md)。所有规划入口均停用隐式历史偏好注入，空标签不继承旧兴趣；当前旅行可以探索不同体验。既有记录保留，主动采用的表单预填留后续。

## 🚀 快速开始

### 前提条件

- Python 3.12.13为当前验证基线
- 使用与前端package-lock兼容的Node.js版本
- 高德地图 API 密钥（[申请地址](https://lbs.amap.com/)）
- LLM API 密钥（OpenAI / DeepSeek 等）

### 后端安装

1. 进入后端目录
```bash
cd backend
```

2. 创建虚拟环境并安装依赖
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

`requirements.txt` 已引用 `requirements.lock.txt`，锁定本机 macOS / Python 3.12.13 的已验证依赖；本阶段不升级框架。前端使用现有 package-lock，复现依赖时运行 `npm ci`。跨平台安装与框架迁移另行验证。

3. 配置环境变量
```bash
# 复制示例配置文件
cp .env.example .env
# 编辑 .env 文件，填入你的 API 密钥
```

`.env` 文件需要配置以下内容：
```env
# 高德地图 API Key（必填）
AMAP_API_KEY=your_amap_api_key

# LLM 配置（必填）
LLM_API_KEY=your_llm_api_key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL_NAME=deepseek-chat
```

4. 启动后端服务
```bash
uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000
```

### 前端安装

1. 进入前端目录
```bash
cd frontend
```

2. 安装依赖
```bash
npm ci
```

3. 配置环境变量
```bash
cp .env.example .env
# 填入高德地图 Web 端 JS API Key
```

4. 启动开发服务器
```bash
npm run dev
```

5. 打开浏览器访问 `http://localhost:5173`

## 📝 使用指南

1. 在首页填写本次旅行的城市、日期、交通、住宿、兴趣及额外要求。
2. 进入发现页勾选景点，确认每天分配与游览时长；AI筛选仅协助本次候选选择。
3. 创建骨架草稿，逐日装配和调整景点、餐饮、开始时间；锁定保护日内排序，移动或删除前先解锁。
4. 调整后按需刷新每日叙述，核对实际时段、天气与费用缺项。
5. 定稿后从“我的行程”重新查看只读结果；失败时保留上次成功状态，按提示重试。

## 🔧 核心实现

[图与保存架构](docs/architecture.md)列出实际入口、并行节点与状态声明；[外部调用说明](docs/external-services.md)列出MCP/LLM期限、取消、重试、能力配置与降级范围。节点获取的工具已由公共网关包装，运行代码通过公共helper调用，保留超时与重连边界。

### MCP 工具列表

通过 `langchain-mcp-adapters` 自动加载的高德地图 MCP 工具：

| 工具名 | 功能 | 关键参数 |
|---|---|---|
| `maps_text_search` | 关键词搜索 POI | keywords, city |
| `maps_weather` | 查询天气 | city |
| `maps_geo` | 地址转经纬度 | address, city |
| `maps_direction_walking` | 步行路线规划 | origin, destination |
| `maps_direction_driving` | 驾车路线规划 | origin, destination |
| `maps_direction_transit_integrated` | 公交路线规划 | origin, destination, city, cityd |
| `maps_search_detail` | POI 详情 | id |
| `maps_around_search` | 周边搜索 | keywords, location, radius |

## 📄 API 文档

启动后端服务后，访问 `http://localhost:8000/docs` 查看完整的 API 文档。

主要端点：

- `POST /api/trip/discover/stream` - 发现景点与天气
- `POST /api/trip/draft/from-selections/stream` - 根据本次选择创建骨架草稿
- `POST /api/trip/draft/{id}/finalize` - 定稿并原子保存历史
- `GET /api/trips/{id}` - 回读历史
- `POST /api/trip/plan` - 兼容一次性完整规划图
- `GET /api/map/poi` - 搜索 POI
- `GET /api/map/weather` - 查询天气
- `POST /api/map/route` - 规划路线
- `GET /api/poi/detail/{poi_id}` - 获取 POI 详情
- `GET /api/poi/search` - 搜索 POI

## 🤝 贡献指南

欢迎提交 Pull Request 或 Issue！

## 📜 开源协议

CC BY-NC-SA 4.0

## 🙏 致谢

- [HelloAgents](https://github.com/datawhalechina/Hello-Agents) - 智能体教程（本项目原始框架）
- [HelloAgents 框架](https://github.com/jjyaoao/HelloAgents) - 原始版本使用的 Agent 框架
- [LangGraph](https://github.com/langchain-ai/langgraph) - 当前使用的 Agent 工作流框架
- [langchain-mcp-adapters](https://github.com/langchain-ai/langchain-mcp-adapters) - LangChain 官方 MCP 适配器
- [高德地图开放平台](https://lbs.amap.com/) - 地图服务及 MCP 云服务
- [amap-mcp-server](https://github.com/sugarforever/amap-mcp-server) - 高德地图 MCP 服务器

---

**智能旅行规划助手** - 基于 LangGraph 的多节点协作旅行规划 🌈

### 第一阶段：价值基线与酒店报价（2026-10-15）

住宿规划新增房间数、每房成人及儿童年龄；酒店卡展示本次房型报价的入住日期、早餐/税费/退改与来源。无法核对的报价不计入已知小计，历史星级估价不再充当可订价格。该阶段预算尚不含往返大交通；当前单城journey与多城transfer可计入已录入的全体同行交通金额，未知费用仍不完整。真实样本发现儿童/多房回显存在限制；用户价值与登录后价格一致性仍待验证。详见 [交接与复验](docs/ltp12-ltp14-handoff.md)、[六任务基线](docs/phase1-value-baseline.md)、[数据源取舍](docs/data-source-evaluation.md)。
