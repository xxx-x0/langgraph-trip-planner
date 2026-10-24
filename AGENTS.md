# AGENTS.md

本文件为 Codex (Codex.ai/code) 在此仓库中工作时提供指引。

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

图定义在 [graph.py](backend/app/agents/langgraph_agent/graph.py)，实际API与图边见 [架构说明](docs/architecture.md)。

- **`create_trip_planner_graph()`**：兼容完整规划图，START并行search_attractions/search_weather，在gather_search汇聚，cluster后并行search_hotels_by_day/search_food，随后plan_route → macro_planner → Send按天生成 → reduce_assemble → global_synthesizer → 兼容历史观察提取/保存。14个节点，不含偏好加载。
- **`create_discovery_graph()`**：START并行search_attractions_discovery/search_weather，在gather_discovery汇聚。景点节点内部使用缓存及高德查询，3个节点。
- **`create_planning_graph()`**：从本次选择进入cluster_from_selections，并行search_dining_pool/search_hotels_by_day，macro_planner后save_draft，5个节点。每日装配、编辑、叙述与定稿不在此图中执行。

当前没有start_interactive_plan/submit_feedback或AsyncSqliteSaver检查点执行模式。兼容完整规划入口为plan_trip和plan_trip_stream；当前页面使用发现、骨架、草稿API与独立finalize流水线。

### API 路由

在 [main.py](backend/app/api/main.py) 注册trip_lg、其discover_router、trip_draft、trip_history、map_lg、poi_lg、admin、multi_trip、tickets，均以/api为前缀；另有根路径与/health。已提交3b3a93c的OpenAPI共52个路径，实际方法见运行时/openapi.json；LTP-8的35路径盘点仅为历史证据。

当前页面通过 `/api/trip/draft/from-selections/stream` 创建草稿，逐日调用assemble/recompute/narrative/ai-rearrange，再调用finalize保存；旧 `/api/trip/plan/from-selections/stream` 兼容路径也返回draft_id。HelloAgents旧路由不注册，旧依赖已从新安装移除，用户本地参考文件不自动删除。

### 外部服务（MCP 协议）

主要外部数据源通过 Model Context Protocol 适配器接入：
- **高德地图 (AMap)** — 地图、POI、天气、地理编码、路线规划（[services/langchain_amap_tools.py](backend/app/services/langchain_amap_tools.py)）
- **AIGoHotel** — 酒店搜索，经由 ModelScope（[services/aigohotel_mcp_service.py](backend/app/services/aigohotel_mcp_service.py)）
- **Bing** — 网页搜索，经由 ModelScope（[services/bing_mcp_service.py](backend/app/services/bing_mcp_service.py)）

三个MCP服务经 [mcp_gateway.py](backend/app/services/mcp_gateway.py) 返回受控工具，共用 [external_calls.py](backend/app/services/external_calls.py) 的总期限、取消、有限重试、并发、缓存、错误解析和脱敏观测；总期限含排队与重连，不额外叠加SDK或图重试。Open-Meteo与异步Unsplash也经过公共边界。实际调用点、期限及生命周期见 [外部服务说明](docs/external-services.md)。

其他服务：[trip_history_service.py](backend/app/services/trip_history_service.py) 封装行程历史 CRUD；[unsplash_service.py](backend/app/services/unsplash_service.py) 从 Unsplash 拉取景点封面图；[preferences_service.py](backend/app/services/preferences_service.py) 负责偏好加权合并与持久化。

### LLM 配置

默认LLM为DeepSeek，通过OpenAI兼容API接入（配置在 `backend/.env`）。[llm_service.py](backend/app/services/llm_service.py) 使用 `LLM_STRUCTURED_OUTPUT_MODE` 显式选择json_prompt（默认）、auto或function_calling；按实际请求有界探测结构化能力，不使用模型名黑名单，必要时在同一期限回退JSON解析。`EXTERNAL_LLM_TIMEOUT` 默认60秒；认证和网络失败不能当作能力不支持。

### 状态管理

- **后端**：TripPlannerState、DiscoveryState、DayPlanLocalState唯一声明在 [models/state.py](backend/app/models/state.py)，原agents路径仅重导出同一对象。errors/messages及按天、景点收集字段使用operator.add；其他列表按新值替换。SSE汇总遵守同一累加/替换语义。
- **前端**：无 Vuex/Pinia。使用组件局部 `ref`/`reactive` 状态，全局主题通过 `useTheme` composable 管理（持久化到 localStorage）。

### 关键模式

- **降级与失败**：[utils/parsing.py](backend/app/agents/langgraph_agent/utils/parsing.py) 为旧生成路径提供部分数据降级；估算路线须明确标记。普通草稿重算遇地图失败保留已保存状态，AI重排或定稿失败不写部分修改/历史，不能把降级结果标为完整验证成功。
- **本次意图与历史观察**：用户确认停用所有隐式历史偏好加载/提示注入，以当前表单、勾选和编辑为规划依据；空标签不补旧兴趣。既有API和数据保留，主动预填留后续。兼容自动统计只记历史观察、不参与规划；不覆盖source=explicit的记录。非explicit观察仍沿用原事务及重复计数保护，不能视为用户长期喜欢或真实消费。术语见 [CONTEXT.md](CONTEXT.md)。
- **SSE 流式传输**：[services/api.ts](frontend/src/services/api.ts) 共用 [services/sse.ts](frontend/src/services/sse.ts)，以fetch/ReadableStream解析事件，期限覆盖响应体；完成前EOF明确失败，完整终止事件后关闭。发现页会话快照和创建请求ID支持响应丢失重试，已定稿草稿跳转只读历史。

### 数据库

异步SQLAlchemy + aiosqlite：
- `backend/data/trips.db` — 行程历史和用户偏好（ORM 模型在 [models/db_models.py](backend/app/models/db_models.py)）
- `backend/data/checkpoints.db` — 如本机存在则保留的旧文件；当前无检查点执行链，不自动删除或迁移

## 前端

路由在 [frontend/src/main.ts](frontend/src/main.ts)：`/`（Home）、`/result`（Result）、`/discover`（DiscoverView）、`/my-trips`（MyTrips）、`/trip/:id`（Result复用，props模式）、`/draft/:id`（按需加载DraftView）、`/multi-trip/:id?`（多城市工作台）。UI 库使用 Ant Design Vue。

### Result 视图拆分

[views/Result.vue](frontend/src/views/Result.vue) 仅作为外壳（Hero + Tab Bar + Transition），实际内容拆入 [components/result/](frontend/src/components/result/)：`ResultHero`、`TabOverview`、`TabItinerary`、`TabBudget`、`TabMap`、`TabWeather`。导出图片 / PDF 时会切到 `isExporting` 将所有 Tab 同时渲染。

### 发现 → 规划流

[views/DiscoverView.vue](frontend/src/views/DiscoverView.vue) 调用 discovery SSE 接口，分批展示景点；[components/DiscoveryMap.vue](frontend/src/components/DiscoveryMap.vue) 负责地图可视化，[components/SelectableAttractionCard.vue](frontend/src/components/SelectableAttractionCard.vue) 支持勾选与按天分配；用户确认后调用骨架接口进入DraftView，逐日装配/编辑后定稿进入Result。

## 无认证

应用使用简单的 `user_id` 字符串（默认 `"default"`）进行偏好追踪，无认证层。

## 当前本机验证与草稿编辑规则

正式依据见 Nexo 已确认决策（本机内部记录，链接未公开）。本阶段为本机单用户；暂缓账号、多人协作和公开部署，保留用户未提交代码，不擅自提交。

锁定保护当前日内排序；手动与 AI 重排都须尊重锁定，移动或删除前先解锁。删除前项可让序号自然缩减。删除状态在重算、强制装配和 AI 重排后保留，只有用户明确恢复才重新加入。失败保留上次成功保存状态，页面提示本次修改尚未保存。

`backend/tests/conftest.py` 为普通 pytest 运行提供临时 SQLite；显式传入 `DATABASE_URL` 时使用指定数据库，因此测试应指定临时路径。外部服务 smoke test 默认跳过，需 `RUN_SMOKE_TESTS=1` 才运行。不要把模拟服务验证当成真实外部调用结果。LTP-3 证据、复验步骤与后续待办见 [交接文档](docs/ltp3-handoff.md)。

2026-10-13 的真实两日核心旅程及运行配置见 [LTP-5 交接](docs/ltp5-handoff.md)：后端176项、前端36项回归通过，另4项smoke跳过。DeepSeek V4交互默认禁用思考，可通过 `LLM_THINKING_MODE` 配置；AI筛选60秒后回退并释放选择。AI选中的餐厅应沿用真实候选坐标、价格和来源。已保存结果只读，编辑在定稿前草稿完成。门票未知、酒店晚数、用餐时段和文案一致性限制仍须接手，不应宣称建议质量或价值假设已通过。

2026-10-14 LTP-6 后端200项、前端41项回归通过，另4项smoke跳过；见 [交接](docs/ltp6-handoff.md)。后端安装由 requirements.txt 引用 requirements.lock.txt，保留前端 package-lock（用 npm ci 复现），未升级框架。未知票价使用null，明确免费为0，住宿按N−1晚；预算缺项不得声称在上限内。每日和最终结果共用保存的timeline_schedule；全局费用、餐次缺项与天气由结构化事实生成，模型仅生成标语。定稿历史/草稿/偏好同事务，重复返回原历史，期间草稿改变则拒绝旧快照，已定稿不可编辑。原SQLite表结构不变，新增字段只进JSON；验证一律用隔离库。

2026-10-14按用户后续授权推进LTP-2/7，未等待或代替LTP-6用户验收；后端236项、前端49项通过，4项smoke跳过，构建通过。真实两日规划、编辑、定稿及幂等回读53项通过，Bing实际拒绝请求不能计为可用性通过。实现、配置、故障注入与真实证据分别见 [交接](docs/ltp2-ltp7-handoff.md) 和 [外部服务说明](docs/external-services.md)。

2026-10-14 LTP-8用户确认停用隐式历史偏好注入，主动预填留后续；已统一图状态并清理旧依赖。新隔离环境锁75项（原134项移除59项，保留版本未升级），后端246项、前端49项通过，4项smoke跳过；真实两日58项核对通过，规划无历史读取、explicit记录原样保留。原环境134包、业务库、CV及旧成果未变；见 [交接](docs/ltp8-handoff.md)。既有JSON preferred_*字段名为兼容保留，不表示已启用自动用户画像。

完整后续建议及LTP-7～10见 [路线图](docs/refactor-roadmap.md)，既有USER验收仍待用户判断。LTP-10已接入随保存安排自动更新的事实说明、逐日快照比较和旧记录只读投影；复杂营业日、预约和建议质量继续保留限制。Nexo是用户开发中的应用，使用中所有问题按 [台账规则](docs/nexo-usage-log.md)记录具体操作、预期/实际、影响、复现、脱敏证据和状态；区分产品/体验/环境/代理操作问题，不自行修改Nexo。未经用户授权不创建Git提交。

2026-10-14 LTP-10：重算、删除/恢复、改时间/用餐、AI重排及强制装配均同步更新事实说明，定稿/历史保存共用投影；旧草稿和历史读取不写原数据。description_source/narrative_source仅增加JSON字段，ORM不变。叙述与定稿标题不额外调用模型，narrative兼容接口在页面为“刷新行程说明”；来源不明的旧说明不直接展示，外部名称按纯文本呈现。所有每日API写入在事务内检查该天原JSON，迟到结果409，前端回读最新；定稿仍检查整份快照和幂等保存。旧Result本地编辑入口已关闭，编辑在DraftView完成。框架和依赖锁不变，证据、USER验收状态及限制见 [交接](docs/ltp10-handoff.md)。

LTP-11用餐规则：删除手动用餐依赖的景点后按原时间轴就近保留间隙，无前置景点则首景点前；auto餐次继续自动安排。AI保护当前已安排正餐数量/餐次，不补原本未安排或已明确删除餐次；只从候选/当前餐厅取事实，有效插入位置保留。真实路线后检查餐次/营业时段，最多一次保留旧安排核对，不能保留则拒绝写入；全AI共享110秒。meal_adjustments只进入JSON，同步当前说明与定稿，不改ORM。后端300/前端58通过、4 smoke跳过，实际两日18项编辑/38项最终检查及旧漏餐规则重放分开留证；见 [交接](docs/ltp11-handoff.md)。

2026-10-15 LTP-9已完成仓库外隔离评估，当前运行依赖保持原锁。baseline/adapter/ecosystem/migration四组各300通过、4 smoke跳过，前端58及构建通过；基线/新MCP真实两日各34项及候选事实/旧环境只读24项核对通过，回退重建300通过。新MCP为langchain1.4.6/FastMCP4.1/MCP2.3原型，仅副本；httpx2异常分类仍有失败、酒店GET405/DELETE404等会话兼容待处理，不可直接迁移或宣称完整兼容。原75、候选75/78/111包冻结、成本、回退、证据局限与USER状态见 [交接](docs/ltp9-handoff.md)。未经后续授权不切换运行环境，保留既有未提交成果与业务库。

2026-10-15 LTP-9后续仅在隔离副本修复httpx/httpx2空消息异常、HTTPStatusError响应状态、SDK因果链与酒店会话语义；固定111候选，未改当前运行源码/75锁。新增60项故障后最终360通过/4 smoke跳过，前端58/构建通过；最终真实两日34及旧75环境只读事实28通过、回退重建300通过。酒店GET405仅一次能力探测、DELETE404/405保留实际清理状态，POST认证/限流/服务故障及会话过期仍正确失败或有限重连。兼容transport依赖MCP2.3部分内部接口，后续升级需复验，不直接套入其他服务；见 [交接](docs/ltp9-compat-handoff.md)。

2026-10-15 LTP-12～14：第一阶段已建立六任务价值基线、酒店入住条件/房型报价及来源评估。新增Hotel.quote仅存JSON，旧estimated_cost不再当作住宿报价；整段均价按分分配、退房日不计费，条件/单位不明保持未知。儿童/多房实测回显不一致时不得计入预算；税费未知及往返大交通缺项须明确提示。后端339/前端62及构建通过，4 smoke跳过；3种真实旅程与77项记录重放分开留证。真人价值及登录后同条件落地价未验证，USER验收不代办。锁、ORM及业务库保持，见 [第一阶段交接](docs/ltp12-ltp14-handoff.md)、[价值基线](docs/phase1-value-baseline.md)、[数据源评估](docs/data-source-evaluation.md)。


2026-10-15 LTP-15/16（确认方案P04/P05）：酒店按游玩区域距离优先、保留分店名与报价限制；餐饮新增本次每餐预算/饮食要求/顺路或专程选择，按午晚餐前后活动搜索和解释，预算缺候选补简餐、有限详情查询兼顾两类。草稿可换餐厅/按当前安排重新查找，价格位置等沿用服务端来源，关闭/营业冲突拒绝新店保存；查询的天快照与候选快照在事务内检查，迟到结果409、失败保留。AI保留手动餐厅和位置，不补删除餐次。说明为当前事实的重点/节奏/取舍，待确认独立展示，草稿新增可展开时间安排；无额外文案模型/历史注入。JSON字段含trip_intent/pending_confirmations/recommendation，ORM及依赖不变。后端354、前端65及构建通过，4 smoke跳过；真实两日、预算换店5项和AI/定稿回读7项分证，20餐厅8场景为P03样本回放。直线绕路非导航、商户更新时间/份量/菜系/儿童设施未知，真人理解与采纳仍NOT_VERIFIED，USER验收待判断。见 [交接](docs/ltp15-ltp16-handoff.md)。

2026-10-15 LTP-15后续/LTP-17（P06）：长空档改为赴餐厅前的未安排时间，提供用户主动采用的晚出发建议，经餐次/已知营业/交通窗口检查；真实固定样本246→126分钟，剩余空档不冒充解决。新增手动journey去返班次、时区/跨日、价格来源/同行总价、可编辑接驳缓冲，travel_window约束每日保存和定稿，交通预览确认不移动现有活动。交通变更与每日/餐厅/定稿均检查请求快照，旧结果409；酒店报价按抵离日期，缓冲不重复算酒店办理。JSON新增Budget.total_intercity等，无ORM/锁变更；历史投影同步费用/待确认/交通，读不写。旧完整规划含journey须转草稿流程。后端380/前端68及构建通过，4 smoke跳过；固定真实样本、实际地图重算、手动示例票价分证，P07/P08与真人价值仍待后续。见[交接](docs/ltp17-handoff.md)。

2026-10-16 LTP-18/19（P07/P08）：新增手动往返备选比较，逐项税费/行李/接驳/途中住宿、报价时效及门到门时间；舒适度只解释早晚跨日/中转/接驳，未知不评分。选择预览支持同步可容纳日程，保持锁定排序/删除/餐次，放不下保留并列冲突；请求+每日JSON事务快照保护，预算/住宿/叙述/定稿一致。相邻日期可比较，采用超范围日期需新建规划。RollingGo实际401，无票务凭据；聚合817/818等仅文档评估待申请，未接通真实票价、未完成六组票务实查。后端392/前端74及构建通过，4 smoke跳过；9项留样保存/定稿核对非新地图调用，业务库/ORM/锁不变。见[交接](docs/ltp18-ltp19-handoff.md)与[申请清单](docs/transport-source-evaluation.md)。

2026-10-16 LTP-25按用户授权暂停付费票务接入。草稿页使用12306/携程带日期起终点跳转、条件复制和浏览器本地文字导入，复用P08比较/预览/保存。原文不进入API，确认后的票价为user_quote，记录时间为导入时间；未知附加费用保留，不能声称实时验证。铁路静态站名表3404条，航班35城市，未知地点回退网站与复制；网站人数/票种需再确认。前端97项、交通后端38项及构建通过，实际网站两条预填与隔离人工票价闭环分开留证；详见[交接](docs/ltp25-handoff.md)。不要求用户申请密钥，旧来源探测API仅兼容保留，USER验收另行判断。

2026-10-16 多城市阶段 LTP-21～23：`/multi-trip/:id?` 支持5～10天、2～3城市，票务复用LTP-25查票与文字导入。`models/multicity.py` 定义停留/住宿/相邻交通，`services/multicity.py` 统一投影预算、夜晚和每日窗口；`/api/multi-trips` 用既有TripDraft JSON的`multi_city_v1`聚合与`mc_`前缀，无ORM迁移。城市工作副本须显式同步，整趟保存快照；preview token和revision在单事务校验，已保存版本只读，旧TTL不得清理整趟记录。日期/人数改变时旧安排保留但不沿用报价；手动住宿优先计费且酒店变化须核对路线。多城市允许空白休息日，正餐仍列待办。后端413/前端105回归、4 smoke跳过；真实苏杭数据与人工票价示例分开留证，完整两条真实多城价格和已订票验收未由此替代。见[交接](docs/ltp21-ltp23-handoff.md)与[快照决策](docs/adr/0001-whole-trip-snapshots.md)。

2026-10-19 LTP-22/23后续：rest_periods 将休息落实为固定每日时间轴区间；用户主动获取建议、编辑、预览确认，重算/交通联动保持活动时长、锁定、删除与餐次，放不下拒绝写入。跨城市同日休息检查重叠，纯休息日仍列住宿/正餐缺项；休息仅在当前区域，不伪造回酒店路线。两条七天苏杭/津济真实地图酒店餐饮与12306六段网页报价，经原文字导入完成120项核对，独立模拟无房10项；后端431/前端107、4 smoke跳过、构建通过。天津真实酒店查询失败、两条返程晚餐未安排、费用仍不完整；已订/延误/无房测试明确模拟，USER验收与真人体验未代办。无房未知amount优先保留unavailable原因；ORM/依赖/业务库未改。见[交接](docs/ltp22-ltp23-rest-handoff.md)。

2026-10-19 LTP-25修复12306原始查询逗号被编码为%2C导致站点未识别，实页预填复核通过。LTP-26按用户选择提供Chrome/Edge本机查票扩展源码与zip、只读候选AI排序和单/多城一键采用预览；需要用户安装一次，尚未实装跨标签验证。候选只取限定直达列表字段，模型只选已有ID；列表参考价不当同行总价，预算未知保留，采用仍须预览确认。447后端/130前端及构建通过、4 smoke跳过；真实模型处理手工转录网站留样后隔离API保存回读通过，非扩展采集或新实时核价。依赖/ORM/业务库不改，无Git提交；见[交接](docs/ltp26-handoff.md)与[安装说明](browser-extension/README.md)。

2026-10-19 LTP-26实装后续：用户手动安装并重载0.1.1。修复无tabs权限时读取Tab.url导致错误拒绝回传，改为原页顶层请求ID/origin握手，不增权限。Chrome真实12306读取53候选→真实AI推荐3班→采用G2→预览→草稿确认→只读版本保存回读22项通过；多城空白隔离案例，非复杂日程/购票验收。携程同条件无结果并要求登录，应用空结果提示/不修改已验证，飞机AI至保存待用户登录后继续，不能称全链路通过。前端136及构建通过，后端沿用447/4 smoke跳过；最新证据和限制见[交接](docs/ltp26-handoff.md)。

2026-10-19 LTP-26飞机续验：用户自行登录后，从应用重新查询，Chrome0.1.1自动读取3条可识别直达候选，真实AI首选MU5183；采用自动预览首日无游玩窗口，UI确认草稿/只读保存/刷新回读21项通过。加高铁22项共43项核对，查询→AI→回填→预览→保存两类均实装通过；非全航班覆盖/复杂既有日程推荐质量/购票/真人验收。未知同行总价不计预算，部分卡片无航班号跳过，Edge及全部实站边界未验证。见[交接](docs/ltp26-handoff.md)，无Git提交或业务库/ORM/锁改动。

2026-10-19 LTP-26完整安排续验：复用真实苏杭7景点/13正餐/2酒店/6晚及休息快照，Chrome默认AI高铁G1862/飞机CA8367早班都冲突。当前推荐API只有query+candidates，无草稿安排上下文，自动适配FAILED；预览保留原活动并列冲突，允许冲突草稿，最终保存UI禁用/服务端409。人工在网站限定18点后再带回AI选G46/JD5907，UI预览/保存/刷新及167项事实核对通过，不能冒充自动适配通过。市内来源为旧真实快照、站场缓冲仍估计，无新地图/酒店核价、无运行代码变更。见[续验交接](docs/ltp26-existing-itinerary-handoff.md)，后续应在推荐前服务端按草稿快照检查可容纳性；此升级尚未实现。

2026-10-20 LTP-27：推荐前在服务端按已存单城/多城日程和缓冲过滤冲突，再让AI仅选可容纳候选ID；事实窗口、保留活动与排除原因不由模型编造。多城revision/edge、单城请求+每日事实快照及模型后回读保护；采用预览传schedule_basis，旧basis409，确认保存沿用原CAS。0.2.0铁路全天均匀采样80、航班有界自动加载，权限不增。真实苏杭默认查询无需人工时段筛选：铁路80排48首选G3106/飞机74排53首选MU5192，UI预览保存刷新194项事实核对通过。自定义缓冲不缩短，原7景点13餐2酒店6晚/休息与时间轴保留；接驳仍估计、票价总额未知、部分列表非全站最优。后端460+4smoke跳过/前端140及构建通过，无ORM/依赖/业务库变更或Git提交，USER验收待用户判断；见[交接](docs/ltp27-handoff.md)。

2026-10-20 LTP-26/27后续：扩展源码/zip为0.2.1，航班在累计80条后仍按原16轮/稳定3轮边界继续加载，最后均匀采样；虚拟列表合并后重建唯一ID。推荐显示当前已保存缓冲外的实际余量，<=30分钟提示紧张，不自动加减缓冲或保证赶得上。扩展错误撤销旧推荐并拒绝迟到模型结果，偏好改变清理旧排除信息，旧扩展有更新入口。后端465/前端145及构建通过、4 smoke跳过；旧真实快照离线46项通过，无本轮新外部调用。0.2.0真实194项不冒充0.2.1重新实装，后者待用户手动更新重载；USER验收保留。依赖/ORM/业务库不变，无Git提交，见[最新交接](docs/ltp26-ltp27-followup.md)。

2026-10-20用户重载0.2.1后继续实测：新隔离副本默认铁路80排48/G3106、飞机74排53/MU5192，真实模型与UI采用预览/草稿/只读保存/刷新239项字段核对通过，无人工网站时段预筛。原隔离后端未热重载，重启18026并对刚读取候选重新筛选后，新余量3/10分钟提示实际显示；首次旧后端输出不计新版说明。7景点13正餐2酒店6晚/休息/路线/锁定删除/原缓冲及未知预算保留，原只读成果未变。满80航班后的加载、虚拟索引、无票/断线/全部冲突仍按模拟范围，不冒充全部实站边界；市内沿旧真实快照，无新地图/酒店核价，未购票或代USER验收。新增只读成果与版本范围见同一最新交接，依赖/ORM/业务库不变，无Git提交。

2026-10-20 多日旅行UI：多城市前端改为总览/城市住宿/城际交通/费用待办四个工作区，城市和日期选择展示保存时间轴，按需展开输入，未保存操作条与跨区预览保留原确认规则；单城草稿增加日期定位、收起查票比较，公共导航增加多日入口。151项前端回归及构建通过；Chromium桌面/小屏/暗色与模拟保存交互分别留证，原18026成果仅只读，非新外部数据或真实保存验证。后端/ORM/依赖/业务库未改，无Git提交；新版临时预览15174，旧15173未替换。见[界面交接](docs/multiday-ui-handoff.md)，真人体验与USER验收待判断。

2026-10-20新版界面实走：在18026隔离库通过真实浏览器新建苏杭5日旅行，真实景点/酒店/餐饮/地图、逐日编辑、锁定删除恢复、换餐厅、城市同步和只读保存刷新完成；新成果sample-trip-03版本6。修复日期错误定位、休息建议展开、景点等待/停止重试、底部同步与返回城市、冲突草稿解释、待办分组、手机展开时间轴横向溢出。前端163/构建通过，保存回读86项通过；手工冲突交通示例已撤回，不算真实票价，最终交通/酒店配置/门票早餐仍待核对。无后端/ORM/依赖锁/业务库改动或Git提交；详见[实际走查交接](docs/multiday-ui-flow-handoff.md)。

2026-10-21 苏杭五日交通实走：Chrome助手0.2.1真实12306三段各80候选，采用G1212/G8359/G1388，副本最终revision7只读保存与73项回读通过；原revision6未改。按用户后续要求新增主动“按此班次调整两侧当天安排”：预览重算两城抵离日，明确取消放不下的景点/本城餐次/休息，锁定与游览时长不减，确认后交通/休息/两城快照CAS同事务。最多每城4轮地图、总110秒；服务端预览缓存32份/15分钟，过期/重启/并发拒绝。换城保留苏州拙政园和午餐、杭州晚餐，明确取消胡雪岩旧居/重复两餐/苏州下午休息，非全部活动保留或跨日最优重排。新增日期直达/回原交通段、预览班次核对与撤销、手动缓冲直接预览和输入保护。后端474+4smoke跳过/前端171及构建通过；新高德市内路线与旧酒店/餐厅事实分证。站场接驳仍估计、票价总额未知，无购票/ORM/依赖/业务库变更或Git提交；见[交接](docs/multiday-ticket-flow-handoff.md)。

2026-10-23 多日界面视觉与动效续改：多城市页改为旅行手册式排版，新增可点击路线封面、城市目录/日期书签、按已存时长展示的全天节奏条，点色块可展开定位路程，折叠不修改安排；景点资料图沿用已存来源并处理失败。补封面描线、工作区滑动指示、日期翻页过渡、时间轴逐项展开与定位反馈、预览/保存条入场，支持减少动态效果，无新增依赖。前端173及构建通过，浏览器桌面/390手机亮暗色、键盘、实时过渡状态及隔离副本编辑预览保存验证；原revision7与快照未改，新体验副本sample-trip-08 revision2只改名称，9项回读通过。无新票务/地图/酒店实查、后端/ORM/锁/业务库改动或Git提交；审美与USER体验验收待用户判断，见[交接](docs/multiday-editorial-ui-handoff.md)。

2026-10-23 旅行工作台改版：按用户选定A视觉/B阶段/C信息组织，深炭灰半透明封面、城市日期卡与节奏条、停留分配滑块、同行步进、渐进设置、出发前/在途中/抵达后真实日程联动、缓冲快捷预览及双城时间轴，动画支持减少动态效果；多城每日编辑视觉统一。Chrome0.2.1真实查苏杭换城80候选，采用G1659，105分钟接驳冲突撤销、75分钟保存，苏州08:10编辑同步、只读revision7刷新及43项事实回读通过；首尾班次沿旧快照，无购票/重新酒店核价。前端179项与构建通过。原只读成果未变，体验副本sample-trip-13；后端/ORM/锁/业务库不变，无Git提交。详见[交接](docs/multiday-journey-desk-handoff.md)，审美及USER验收待用户判断。

## 2026-10-24 提交与复验口径

既有旅行功能与源码测试收尾已分批提交至 `3b3a93c`。该提交对应隔离后端623通过、4 smoke跳过，前端239通过且构建通过；不将之后未提交的观测实现算入此基线。上文带日期的“无Git提交”、端口、测试数及USER状态只表示当时快照；当前验收以用户明确判断为准。生成ZIP由predev/prebuild打包且不入库；原output、浏览器证据、简历及业务库保留。手动脚本仅按各自运行说明在隔离进程使用，不能将演示或离线回放当新外部实测。
