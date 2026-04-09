# 智能旅行规划助手 🌍✈️

基于 **LangGraph + LangChain** 框架构建的智能旅行规划助手，通过 MCP 协议接入高德地图云服务，提供个性化的多日旅行计划生成。

> **重构说明**：本项目原始版本基于 [HelloAgents](https://github.com/jjyaoao/HelloAgents) 框架构建，现已完整重构为 LangGraph + LangChain 技术栈。重构涵盖 Agent 工作流、MCP 工具调用层、API 路由层，实现了从同步到异步、从单 Agent 到多节点协作图的架构升级。

## ✨ 功能特点

- 🧩 **LangGraph 多节点协作**：景点搜索、天气查询、酒店推荐并行执行，路线规划依赖前置节点，最终汇总生成计划
- 🔌 **LangChain 原生 MCP 适配**：通过 `langchain-mcp-adapters` 连接高德官方 MCP 云服务（SSE 传输），无需本地安装 uvx/Node.js
- 🤖 **LLM 驱动的工具调用**：各节点 LLM 自动选择并调用 MCP 工具（`bind_tools` + `tool_calls`），获取实时 POI、路线和天气数据
- 🛡️ **健壮性设计**：异步锁单例、工具调用重试（3 次递增等待）、SSE 连接超时配置、备用计划生成
- 🎨 **现代化前端**：Vue 3 + TypeScript + Vite，响应式设计，流畅的用户体验
- 📱 **完整功能**：包含住宿、交通、餐饮和景点游览时间推荐

## 🔄 重构对比

| 维度 | 旧版 (HelloAgents) | 新版 (LangGraph) |
|---|---|---|
| Agent 框架 | HelloAgents `SimpleAgent` | LangGraph `StateGraph` |
| 工作流 | 4 个 Agent 顺序执行 | 3 节点并行 + 1 路线节点 + 1 汇总节点 |
| MCP 工具 | `hello_agents.MCPTool`（Stdio） | `langchain-mcp-adapters`（SSE 云服务） |
| 调用方式 | 同步 `agent.run()` | 异步 `await graph.ainvoke()` |
| LLM | `HelloAgentsLLM` | LangChain `ChatOpenAI` |
| 路线工具 | `*_by_address`（传地址文本） | `maps_direction_*`（传经纬度坐标 + 自动 geocode） |
| 并发能力 | 顺序执行，无并发 | 景点/天气/酒店三节点并行 |
| 错误处理 | 基础 try/catch | 重试机制 + 超时配置 + 备用计划 |

## 🏗️ 技术栈

### 后端
- **Agent 框架**: LangGraph（多节点状态图）
- **MCP 适配**: langchain-mcp-adapters（SSE 传输 → 高德官方云服务）
- **LLM**: LangChain ChatOpenAI（支持 OpenAI / DeepSeek 等）
- **API**: FastAPI
- **语言**: Python 3.10+，全异步

### 前端
- **框架**: Vue 3 + TypeScript
- **构建工具**: Vite
- **UI 组件库**: Ant Design Vue
- **地图服务**: 高德地图 JavaScript API
- **HTTP 客户端**: Axios

## 📁 项目结构

```
helloagents-trip-planner/
├── backend/                        # 后端服务
│   ├── app/
│   │   ├── agents/                 # Agent 实现
│   │   │   └── langgraph_agent.py  # LangGraph 多节点工作流
│   │   ├── api/                    # FastAPI 路由
│   │   │   ├── main.py             # 应用入口
│   │   │   └── routes/
│   │   │       ├── trip_lg.py      # 旅行规划路由 (LangGraph)
│   │   │       ├── map_lg.py       # 地图服务路由 (LangChain MCP)
│   │   │       └── poi_lg.py       # POI 路由 (LangChain MCP)
│   │   ├── services/               # 服务层
│   │   │   ├── langchain_amap_tools.py  # LangChain MCP 服务封装
│   │   │   ├── llm_service.py      # LLM 服务 (ChatOpenAI)
│   │   │   └── unsplash_service.py # Unsplash 图片服务
│   │   ├── models/
│   │   │   └── schemas.py          # Pydantic 数据模型
│   │   └── config.py               # 配置管理
│   ├── requirements.txt
│   └── .gitignore
├── frontend/                        # 前端应用
│   ├── src/
│   │   ├── components/             # Vue 组件
│   │   ├── services/               # API 服务
│   │   ├── types/                  # TypeScript 类型
│   │   └── views/                  # 页面视图
│   ├── package.json
│   └── vite.config.ts
└── README.md
```

## 🔧 LangGraph 工作流

```
                    ┌─────────────────┐
                    │     START       │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
     ┌────────────┐  ┌────────────┐  ┌────────────┐
     │ search_poi │  │search_weather│  │search_hotel│
     │  景点搜索   │  │  天气查询    │  │  酒店搜索   │
     └──────┬─────┘  └──────┬─────┘  └──────┬─────┘
            │               │               │
            └───────────────┼───────────────┘
                            ▼
                   ┌─────────────────┐
                   │   plan_route    │
                   │   路线规划       │
                   └────────┬────────┘
                            ▼
                   ┌─────────────────┐
                   │  generate_plan  │
                   │   生成计划       │
                   └────────┬────────┘
                            ▼
                   ┌─────────────────┐
                   │      END        │
                   └─────────────────┘
```

- **并行节点**：景点搜索、天气查询、酒店搜索同时执行，缩短响应时间
- **依赖节点**：路线规划等待前三个节点完成后执行，利用景点和酒店地址规划路线
- **汇总节点**：整合所有信息，由 LLM 生成结构化的旅行计划

## 🚀 快速开始

### 前提条件

- Python 3.10+
- Node.js 16+
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
uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```

### 前端安装

1. 进入前端目录
```bash
cd frontend
```

2. 安装依赖
```bash
npm install
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

1. 在首页填写旅行信息：
   - 目的地城市
   - 旅行日期和天数
   - 交通方式偏好
   - 住宿偏好
   - 旅行风格标签

2. 点击"生成旅行计划"按钮

3. 系统将通过 LangGraph 工作流：
   - 并行搜索景点、查询天气、推荐酒店
   - 规划景点间交通路线
   - 汇总所有信息生成完整行程

4. 查看结果：
   - 每日详细行程
   - 景点信息与地图标记
   - 交通路线规划
   - 天气预报
   - 餐饮推荐

## 🔧 核心实现

### LangGraph 工作流

```python
from langgraph.graph import StateGraph, START, END

workflow = StateGraph(TripPlannerState)

# 添加节点
workflow.add_node("search_poi", search_poi_node)
workflow.add_node("search_weather", search_weather_node)
workflow.add_node("search_hotel", search_hotel_node)
workflow.add_node("plan_route", plan_route_node)
workflow.add_node("generate_plan", generate_plan_node)

# 并行执行：景点/天气/酒店同时搜索
workflow.add_edge(START, "search_poi")
workflow.add_edge(START, "search_weather")
workflow.add_edge(START, "search_hotel")

# 路线规划依赖前置节点
workflow.add_edge("search_poi", "plan_route")
workflow.add_edge("search_hotel", "plan_route")
workflow.add_edge("search_weather", "plan_route")

# 汇总生成计划
workflow.add_edge("plan_route", "generate_plan")
workflow.add_edge("generate_plan", END)

app = workflow.compile()
```

### LangChain MCP 工具调用

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

# 通过 SSE 连接高德官方 MCP 云服务
client = MultiServerMCPClient({
    "amap": {
        "transport": "sse",
        "url": "https://mcp.amap.com/sse?key=your_api_key",
        "timeout": 60,
        "sse_read_timeout": 300
    }
})

# 自动加载所有 MCP 工具
tools = await client.get_tools()

# LLM 绑定工具并调用
llm_with_tools = llm.bind_tools([search_tool, weather_tool])
response = await llm_with_tools.ainvoke([HumanMessage(content="搜索北京的景点")])

if response.tool_calls:
    result = await tool.ainvoke(response.tool_calls[0]["args"])
```

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
- `POST /api/trip/plan` - 生成旅行计划（LangGraph 工作流）
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
