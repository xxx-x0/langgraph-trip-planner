# LangGraph Trip Planner · 智能旅行规划助手

一个可以在本地运行的 AI 旅行规划 Web 应用，面向国内单城与多城市自由行。把景点、每天的游玩安排、餐厅、酒店和城际交通放到同一份可编辑行程中，帮助你从“想去哪里”逐步整理出一趟旅行。

你可以让 AI 协助筛选景点、调整顺序和比较车次，再在地图与时间轴上检查结果、手动修改，最后保存一份只读行程。地点、路线和报价来自外部数据源或你录入的信息；未知费用和安排冲突会单独提示。

**当前支持本机单用户使用：单城市行程，以及 5～10 天、2～3 个城市的多城市旅行。** 需要自行配置模型和地图服务，酒店查询另需配置酒店服务入口。

## 能做什么

| 功能 | 使用方式 |
| --- | --- |
| 发现与选择景点 | 按目的地、日期和本次兴趣查找景点，在地图上查看位置，手动勾选或让 AI 协助筛选、分配日期。 |
| 编辑每日行程 | 查看游览、路程、用餐和休息时间，调整开始时间与顺序，锁定景点、删除或恢复活动，也可请求 AI 重排。 |
| 安排住宿与餐饮 | 按游玩区域查找酒店；设置入住人数、房间与日期，查看报价条件。按每餐预算和饮食要求找餐厅，并在草稿中换店。 |
| 规划多城市旅行 | 分配城市停留天数，分别编辑城市行程，再同步到整趟旅行，汇总住宿、跨城交通、时间轴与费用。 |
| 比较往返与跨城交通 | 免扩展后台查询 12306／携程，结合已保存日程筛选并预览采用；保留网站跳转、文字导入和扩展备用方式。 |
| 核对预算与待办 | 汇总已有金额，区分未知票价、报价条件和缺失项目；预算不完整时明确提示。 |
| 保存与查看结果 | 单城定稿、多城保存只读版本，之后重新打开查看；单城结果页支持导出图片和 PDF。 |

例如，规划一趟“苏州两天、杭州三天”的旅行：先分配两座城市的停留日期，选择各自想去的景点，调整午晚餐和休息，再比较苏州到杭州的车次。采用班次前可以预览它对两侧日程的影响，确认后同步到整趟旅行。

## 使用流程

```text
填写城市、日期、同行人数与本次需求
                 ↓
       发现景点 → 勾选与分配日期
                 ↓
       创建草稿 → 逐日生成与编辑
                 ↓
       核对住宿、用餐、交通和预算
                 ↓
        预览变化 → 确认保存行程
```

多城市旅行从页面导航中的多日旅行入口开始；每个城市仍可以进入自己的发现与草稿流程，编辑完成后显式同步到整趟旅行。

规划以**本次填写、选择和编辑**为依据，不会自动把过去行程当作你的长期偏好。AI 调整需尊重已有锁定与删除状态；无法满足时间约束时会显示冲突，失败时保留上次成功保存的安排。

## 本地运行

### 准备环境

- Python 3.12（依赖安装验证基线为 macOS / Python 3.12.13）。
- Node.js 22 与 npm，前端按仓库中的 `package-lock.json` 安装。
- 一个支持 OpenAI 兼容接口的模型服务 API Key，示例配置使用 DeepSeek。
- 高德地图 Web 服务 Key，以及用于前端地图显示的 Web 端 JS API Key。

模型和部分外部服务可能产生费用，由各服务提供方计费。本项目不附带共享密钥或可直接使用的酒店服务地址。

### 1. 获取项目

```bash
git clone https://github.com/xxx-x0/langgraph-trip-planner.git
cd langgraph-trip-planner
```

### 2. 启动后端

在仓库根目录打开终端：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Windows 下激活虚拟环境使用 `.venv\Scripts\activate`。依赖通过 `requirements.lock.txt` 约束版本，其他平台的安装兼容性仍需验证。

编辑 `backend/.env`，至少填写：

```dotenv
AMAP_API_KEY=your_amap_web_service_key
LLM_API_KEY=your_llm_api_key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL_NAME=deepseek-chat
```

按需配置以下服务：

| 配置项 | 用途 |
| --- | --- |
| `AIGOHOTEL_MCP_URL` | AIGoHotel 酒店查询的私有 MCP 连接地址。不配置时无法使用该来源查询酒店。 |
| `UNSPLASH_ACCESS_KEY` | 景点封面图片。 |
| `BING_MCP_URL` | 可选网页搜索服务；当前景点发现流程不依赖 Bing。 |

完整选项见 [后端配置示例](backend/.env.example) 和 [外部服务说明](docs/external-services.md)。密钥和私有 MCP 地址只放在本地 `.env`，不要写入源码或提交到 Git。

配置完成后启动：

```bash
python -m uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000
```

后端 API 文档：[http://localhost:8000/docs](http://localhost:8000/docs)。

### 3. 启动前端

另开一个终端，从仓库根目录执行：

```bash
cd frontend
npm ci
cp .env.example .env
```

编辑 `frontend/.env`：

```dotenv
VITE_AMAP_WEB_JS_KEY=your_amap_web_js_key
```

这个 Key 用于浏览器地图，与后端 Web 服务 Key 的用途不同。前端环境变量会进入浏览器代码，不要在其中填写模型密钥或私有 MCP 地址。

```bash
npm run dev
```

打开 [http://localhost:5173](http://localhost:5173)。开发服务器会把 `/api` 请求代理到本机 8000 端口，前后端需要同时运行。`npm run dev` 和 `npm run build` 会调用 Python 3 打包查票扩展，请确保当前终端能找到 `python3`。

默认数据保存在本地 `backend/data/trips.db`，可通过 `DATABASE_URL` 修改位置。

### 旅行记录与相册

导航中的「旅行记录」进入 `/travel-records`：以地球足迹回看实际到访，保存旅行文字、相册和回忆片段。可直接记录，也可从单城已保存行程或多城只读版本补记；城市和日期须主动确认，原计划不会变成已发生的经历。日期支持年、月、日或未知，重复到访会分别保留。

照片原件保存在 `backend/data/travel-memory-media/`，可用 `TRAVEL_MEMORY_STORAGE_DIR` 修改目录；数据库只保存元数据和关联。浏览器保留未提交的编辑及待上传照片。旅行、照片和片段均可从回收站恢复。页面底部提供完整 ZIP 备份、恢复预览和冲突另存副本。第一版支持 JPEG / PNG / WebP，单张20 MiB及4000万像素以内、每次旅行500张以内；完整 ZIP 备份最多512 MiB、2000条记录。HEIC 需先导出 JPEG。

更新后安装依赖并重启后端，会自动创建独立的 `travel_memories` 表；既有行程表不迁移。使用与验证说明见 [第一版交接](docs/travel-memories-v1.md)。

### 交通与景点一起规划

新建单城旅行时，填写出发城市后，AI 自动查询并搭配往返班次，再按抵离和接驳后的可用时间推荐景点。可比较铁路与飞机，或只查一种；综合推荐支持默认 AI 和 Jev，最低参考价与最短乘坐时间按规则比较。已有车票仍可在展开项中录入。未知交通保持暂定，不再默认空出整个首日和末日。

选景点时可以重新搭配交通，保留原选择并更新日期分配；草稿采用有冲突的班次或初次装配放不下时，会进入交通与景点的联动预览，核对跨日移动、用餐与休息取消后确认保存。锁定、固定预约及手动用餐受保护；仍放不下的景点进入待安排清单，可选日期预览加入或明确不再安排，清单处理完才能定稿。细节与真实验证范围见 [交通与景点联动规划](docs/transport-first-planning.md)。

### 免扩展查票

默认入口为“后台查询火车票／机票”。12306 由后端请求网站查询接口；携程由后端运行独立浏览器读取直达列表。仅支持本机单用户使用，查询不会下单、支付或直接修改行程。

铁路无需新增依赖。机票浏览器运行组件在启动后端的 Python 环境安装一次（不是用户浏览器扩展）：

```bash
cd backend
python -m pip install -r requirements-ticket-browser.txt
python -m playwright install chromium
```

携程首次需要登录或验证时，在应用点击“打开登录／验证窗口”，处理后点击“已完成处理，继续读取”。浏览器使用独立本机目录，默认 `~/.local/share/langgraph-trip-planner/ticket-browser`，不会自动继承日常 Chrome 登录；登录有效性及后台读取不能保证。完整运行、失败回退和验证范围见 [免扩展查票说明](docs/background-ticket-search.md)。

### 可选：查票扩展备用方式

在 Chrome 或 Edge 的扩展管理页打开开发者模式，选择“加载已解压的扩展程序”，加载仓库中的 `browser-extension/` 目录，然后刷新规划页面。

扩展可以把本次发起查询的可识别直达车次或航班带回应用。应用先检查与已保存日程的冲突，再根据本次偏好比较候选；采用前仍需预览确认。正常后台查询不需要安装此扩展。

安装步骤、权限和网站适配范围见 [查票扩展说明](browser-extension/README.md)。扩展不提供下单、支付或自动购票。

## 技术架构

前端使用 **Vue 3 + TypeScript + Vite + Ant Design Vue**，后端使用 **FastAPI + LangGraph + LangChain**，通过 **SQLAlchemy + SQLite** 保存草稿和历史。

```text
Vue Web 界面
    │ HTTP / SSE 流式响应
    ▼
FastAPI
    ├── LangGraph：景点发现、规划骨架
    ├── 草稿服务：每日装配、编辑、路线与约束检查
    ├── 多城市服务：城市快照、交通衔接、整趟预算
    └── 定稿与版本保存 → SQLite
              │
              ├── OpenAI 兼容模型服务
              └── 外部数据：高德 / AIGoHotel / 可选 Bing、Unsplash
```

MCP（Model Context Protocol）用于将地图、酒店等外部工具接入后端。模型参与选择与规划，地点坐标、路线、价格等事实由数据源提供；每日行程说明根据已保存安排生成。

```text
backend/
  app/agents/langgraph_agent/   规划图、每日装配与定稿
  app/api/                     HTTP 与 SSE 接口
  app/models/                  请求、行程与数据库模型
  app/services/                外部服务、草稿与多城市逻辑
  tests/                       后端回归与手动验证脚本
frontend/
  src/views/                   发现、草稿、结果与多城市工作台
  src/components/              地图、时间轴、酒店与餐饮等组件
  src/services/                API 与流式响应处理
browser-extension/             查票扩展源码
scripts/                       扩展打包等辅助脚本
docs/                          架构、服务配置及开发记录
```

进一步了解实现：[架构说明](docs/architecture.md) · [外部服务与超时配置](docs/external-services.md) · [领域术语](CONTEXT.md)。

## 开发与测试

后端测试从 `backend/` 执行，使用独立临时数据库：

```bash
# 先激活后端虚拟环境
TEST_DIR=$(mktemp -d)
DATABASE_URL="sqlite+aiosqlite:///$TEST_DIR/trips.db" RUN_SMOKE_TESTS=0 python -m pytest
```

前端从 `frontend/` 执行：

```bash
npm test
npm run build
```

外部服务 smoke 测试默认跳过；显式设置 `RUN_SMOKE_TESTS=1` 才会运行对应测试，并需要有效服务配置。更多人工验证步骤见 [手动验证说明](backend/tests/manual/README.md)。

<a id="verification-baseline"></a>

2026-11-01 上传前隔离回归结果：后端 **1017 项通过、4 项外部 smoke 跳过**，前端 **267 项通过**，类型检查与生产构建通过。后端使用既有 75 包锁定环境和独立临时数据库，本轮未重新调用模型、地图、酒店或票务网站。这些结果不表示所有外部服务、网站页面或实时价格都已验证。`docs/` 中的阶段记录保留各自日期与验证范围，不代表当前服务可用性。

开发记录中的 `${PROJECT_ROOT}`、`${EVIDENCE_ROOT}`、`${USER_HOME}` 和 `${USER_CONFIG_DIR}` 分别表示本机仓库、证据归档、用户目录与私有配置目录，需按自己的环境设置。原始证据、登录数据与凭据不随仓库发布，克隆后无法直接打开这些本机证据链接。

## 当前限制

- **面向本机单用户。** 没有账号认证或多用户数据隔离，不适合直接作为公开在线服务部署。
- **旅行信息需要核对。** 营业时间、预约、路线、天气及酒店报价可能变化；儿童、多房、早餐、税费和退改条件以供应方实际页面为准。
- **预算可能不完整。** 未知费用不会当成免费，未确认的酒店或同行交通总价不会充当完整预算；应用不保证最终消费低于预算上限。
- **查票结果只是部分候选。** 铁路后台查询依赖网站接口及格式，携程后台浏览器和扩展依赖页面及登录状态，均不能保证覆盖全部班次或找到最低价；参考价不等于可成交的同行总价。扩展历史验证范围与本轮免扩展实测分开，见各自说明。
- **安排冲突仍需取舍。** 跨城衔接、接驳缓冲和固定休息可能使活动放不下；预览会列出影响，需要你决定保留或取消哪些安排。

## 许可与致谢

项目沿用 **CC BY-NC-SA 4.0** 许可声明。

本项目起源于 HelloAgents 旅行助手实践，现使用 LangGraph / LangChain 实现。感谢 [Hello-Agents](https://github.com/datawhalechina/Hello-Agents)、[HelloAgents 框架](https://github.com/jjyaoao/HelloAgents)、[LangGraph](https://github.com/langchain-ai/langgraph)、[langchain-mcp-adapters](https://github.com/langchain-ai/langchain-mcp-adapters) 和 [高德地图开放平台](https://lbs.amap.com/)。
