# LTP-8 本次意图、图状态与旧依赖交接

> 历史快照：本页的版本、测试数、端口、未提交/无Git提交与验收状态对应页内日期，不代表当前状态。当前源码和回归口径见[维护基线](../README.md#verification-baseline)；本机证据未随仓库发布。

2026-10-14，本机单用户、单城市多日旅行。[LTP-8](http://127.0.0.1:3000/issues/476d5756-2553-4099-ba71-a3dfee03cd18)，来源codex-ltp，执行会话 `eb378b32-ca40-45fb-baf9-5b4973fe31c7` 已COMPLETED v5，无活跃会话，USER请求已提交并回读PENDING。沿用原main工作区，HEAD仍为 `57bd8a46f5d4ea3c638ca23998f78bed19806f3e`，无新增Git提交。起点85项改动均备份，保留原业务库、原虚拟环境与既有成果。未升级框架、迁移业务库或修改Nexo。

## 用户确认的偏好边界

用户指出当初放弃加载偏好，是因为每次规划前已有明确选择，而且新旅行可能探索不同体验。2026-10-14明确确认：“采用建议：停用隐式注入，主动预填留后续”。因此本轮修复的目标是让入口行为一致，不是补一条偏好加载连线。

三种概念见 [CONTEXT](../CONTEXT.md)：本次旅行选择、明确保存的偏好、历史行程观察。所有规划入口只依据本次表单、勾选和编辑；空兴趣不补旧兴趣，旧酒店或菜系不作为系统消息或提示夹带。长期习惯以后如有价值，应由用户主动采用为可见、可改的表单预填，本轮不新增该功能。

已有记录和CRUD接口保留。为兼容原定稿保存，非explicit记录仍可累积历史行程观察，但完全不参与下一次规划；AI安排不是用户确认喜欢，也不是消费或旅行已经发生的证明。新增保护使source=explicit记录的内容、来源、置信度和更新时间不被自动观察覆写。其total_trips也原样保留，不能把该兼容字段当作真实出行次数统计。

## 本次实现

| 部分 | 改动 |
| --- | --- |
| 偏好入口 | 删除主图不可达加载节点和骨架图实际加载节点；移除节点提示拼接及状态通道，不隐式读取历史 |
| 观察保存 | 旧图与草稿定稿共用事务内观察保存；explicit记录不写，非explicit保留原兼容行为；深拷贝合并避免修改已加载对象 |
| 唯一状态 | 以models/state.py声明TripPlannerState、DiscoveryState、DayPlanLocalState，agents旧路径仅重导出同一对象；清理无人使用的旧中间DTO/包导出 |
| 并行错误 | 两条并行分支同时失败原先可能触发InvalidUpdateError；errors补operator.add并做真实图执行故障回归 |
| SSE汇总 | 只对声明的累加字段合并，其他选择/候选列表替换，不再一律extend或修改初始列表 |
| 图与进度 | 主图14、发现3、骨架5节点；五步骨架完成事件与前端标签一致，酒店/餐饮同级进度；健康检查从实际图生成清单，明确隐式记忆关闭 |
| 旧依赖 | 删除hello-agents、aiohttp、loguru、fastmcp、uv、python-dateutil、huggingface_hub这7项无运行引用的直接依赖，清理仅为它们需要的传递闭包；锁134→75，保留版本不变 |
| 文档 | README/AGENTS与 [架构](architecture.md) 按实际入口更新；当前无交互反馈API或SQLite检查点执行模式；原agents状态导入路径兼容 |

运行代码AST盘点没有HelloAgents导入，当前本机也未发现被gitignore的旧参考文件；如果其他检出仍有用户本地参考文件，不自动删除。仍保留的旧LangGraph辅助函数不表示它们是实际图节点。API Pydantic响应字段和ORM表结构均未改。

## 自动、环境与保留验证

本机证据目录：`/Users/finn/.local/share/nexo-codex/handoffs/2026-10-14-ltp8/`。以下路径均相对此目录。

起点baseline.patch/baseline-files/baseline-manifest.json与最终final.patch/final-files/final-manifest.json均保存；final.patch包含既有未提交成果，task-changes.patch专门对照本次起点。最终99项文件带SHA；凭据扫描无匹配，未复制.env或连接凭据文件，第三方clean-venv安装文件不纳入成果凭据扫描。

| 验证 | 最终结果与证据 |
| --- | --- |
| 新环境全量后端 | **246通过、4跳过**，`backend-tests-final-246.log`；跳过为默认关闭的外部smoke |
| 原环境首轮 | 244通过、4跳过，`backend-tests-existing-env.log`；随后增加空兴趣不回填历史的参数用例和酒店先于餐饮完成时进度不回退用例，新环境最终为246 |
| 前端/类型/构建 | **49通过、14文件**，构建通过；`frontend-tests.log`、`frontend-build.log`，保留原地图导入和大分包告警 |
| 偏好行为 | 冲突历史和空兴趣均不加载、不入prompt、不改保存的当前请求；两种观察写入路径不覆写explicit；见test_current_trip_policy.py、test_preference_boundaries.py |
| 图故障与状态 | 实际主图/发现图并行失败保留两条错误；流汇总替换选择、累加日程且不污染初始值；骨架持久化、逆序完成进度不回退与健康图清单通过 |
| 全新环境安装 | clean-venv无system-site-packages，从requirements安装75项；pip check通过，59项被移除包均未安装，框架及其他保留版本不变；`install-plan.json`、`install-actual.json`、`clean-env-audit.json` |
| 架构盘点 | OpenAPI35路径，图节点14/3/5，旧agents与canonical类型对象相同，运行HelloAgents导入0；`architecture-inventory.json` |
| 保留审计 | 原85文件备份SHA相同、原业务库所有行及表结构相同、3条旧历史可读、CV/前端lock/HEAD未变、原环境134版本未变；`preservation-audit.json` |

依赖验证基线为macOS/Python3.12.13、Node22.22.2。干净环境中core1.4.0、openai1.1.9、LangGraph1.2.4、checkpoint-sqlite3.1.0、MCP adapters0.2.2、MCP1.27.2均保持原版本。原 `.venv`仍有旧包，本次没有对它做卸载；今后复现应新建环境按锁安装。其他平台/Python版本尚未验证，框架迁移仍属LTP-9。

## 真实两日链路

真实服务运行在上述clean-venv，后端18004、前端5178，数据库为证据目录validation.db。观测器live-observer.py原样转发高德、酒店和模型请求，记录脱敏元数据、SQL读取计数及模型请求是否含历史哨兵；没有模拟外部服务。

先通过既有API为测试用户ltp8-current-trip保存source=explicit的历史样本（高档酒店/异国菜/海滨，与本次苏州经济型、历史园林选择相冲突）。样本为人工构造的测试输入，不是真实个人画像。随后真实发现30个景点并查询天气；规划仍复用LTP-2/7已选的六个真实景点及日分配，不能说本次重新手动选了30个景点或重做AI筛选。

创建草稿 `1583b14fbd6d4b63bd7f1426971fc34c` 时，历史偏好SELECT计数2→2，规划没有读取它；本次9个真实模型请求均未含历史哨兵。五个骨架完成节点齐全。两日装配、手动重排、锁定、AI重排、叙述刷新后，在页面点击定稿保存为历史 **1**，并回读只读结果。

| 日期 | 当前选择与安排 |
| --- | --- |
| 10月15日10:00 | 虎丘 → 留园（锁定第2位）→ 七里山塘；山塘河宴68元，13:46–14:46；凝翠园82元，18:56–19:56；阴24℃ |
| 10月16日08:00 | 拙政园 → 苏博本馆（锁定第2位）→ 平江路；孙盛兴奥灶面23元，11:30–12:30；平江桃花源记78元，17:30–18:30；小雨26℃，早餐缺项提示 |

酒店花筑·苏州山塘御苑精品民宿292元/晚，仅报价，没有预订。已知费用 **643元**（一晚292、餐饮251、交通估算100）；六项门票未知和第二日早餐共7缺项，不能当作完整费用或已在预算上限内。四家餐厅共20项坐标、价格、来源、营业时间和POI与真实候选匹配。

**58/58核对通过**，包含原日程/天气/预算/锁定/候选信息、无历史注入、显式记录不变、当前请求和真实骨架事件。三次并发重复定稿同历史1；创建重放同草稿，历史1/草稿1不变，出站756→756。明确偏好记录所有字段与元信息不变，兼容total_trips仍为原样本7，不是本次又学习7次。证据为real-final-verification.json、real-explicit-pref-before/after.json、real-preference-read-check.json。

| 阶段 | 秒 |
| --- | ---: |
| 冷发现30个景点及天气 | 98.525 |
| 酒店、餐饮与骨架 | 47.858 |
| 两日装配 | 16.192 / 15.432 |
| 手动重算 / 锁定重算 / AI重排 | 6.474 / 7.222 / 8.810 |
| 两日叙述刷新 | 9.986 / 9.267 |
| 页面定稿 | 1.822 |
| 三次重复定稿 | 0.017～0.019 |
| 创建重放 | 0.002 |

这不是受控性能实验；与LTP-2/7骨架63.329秒相比，本次47.858秒受到日期、缓存、服务数据和负载影响，不归因于清理提速。阶段间含人工操作，不相加作连续全流程用时。Bing、Open-Meteo、Unsplash本次主链未调用，不新增可用性结论，沿用上轮Bing拒绝的限制。兼容完整规划入口由真实图/模拟外部回归覆盖，本次真实页面链使用发现/骨架/草稿路线。

当前 [结果页面](http://127.0.0.1:5178/trip/1)，截图real-saved-overview.png、real-saved-weather.png。页面与后台进程不保证后续持续运行。

## 复验与后续

在新环境安装锁并使用隔离数据库；不要把原业务库作为测试目标：

```bash
cd backend
python3.12 -m venv /tmp/ltp8-recheck-env
/tmp/ltp8-recheck-env/bin/python -m pip install -r requirements.txt
/tmp/ltp8-recheck-env/bin/python -m pip check
/tmp/ltp8-recheck-env/bin/python -m pytest -q --disable-warnings
```

```bash
cd frontend
npm ci
npm test
npm run build
```

普通pytest提供临时SQLite；显式DATABASE_URL必须指向新的隔离库。真实复验脚本和输入在证据目录，先读live-observer.py、ltp8-real-chain.py和ltp8-verify-final.py，换新输出目录、数据库、请求ID与测试用户，避免覆盖本次或把幂等回读当作新规划。原业务库只读审计，基线只备份了实际存在的trips.db；checkpoints.db当前不存在。

本轮没有主动预填、持久禁忌/过敏模型、偏好学习质量或账号功能。每日重排后的叙述自动失效仍属LTP-10；本次已手动刷新两日。复杂营业日、预约、排队、预算缺项和建议质量继续保留限制。后续先读用户验收反馈，再按路线图处理LTP-10及LTP-9隔离评估，既有LTP-2/3/5/6/7验收不自动通过。

## Nexo 与最终回执

用户确认策略学习记录 `08d64d10-c6e1-48fe-a7e5-b8d6e9f5beaa`，不是另行伪造Nexo的CONFIRMED决策。首次客户端脚本误读start回执id导致KeyError，实际会话已成功启动，回读后继续，无重复启动；按NXUSE-008记 [台账](nexo-usage-log.md)。NXUSE-002连接入口持续，沿用用户授权文件访问原MCP，不修改Nexo。

2026-10-14 17:13关闭会话并生成交接 `cf06ee07-997b-4a4a-b196-5a3a5f1f27dd`。17:14最终USER请求 `2a1e6943-32d0-4fee-baf9-e4e18b194d42` 回读PENDING，Issue仍IN_PROGRESS v4，无活跃会话。五项标准均附来源证据，未保存用户反馈或代替用户验收。首次请求 `d2ddcc60-467e-4f75-97df-b94eb484e37a` 已被替代，仅精确化“7项直接依赖、闭包总减少59包”及“3条进度、会话1→4”的表述，范围、标准与结果不变。

执行事实3条，学习记录 `f0dc439b-bbce-40b4-87d0-0ab011693096` v2记录最终246项、依赖及真实链路；用户确认策略单独保存在前述08d64记录。项目v16下一步指向用户审查LTP-8，既有USER请求不自动通过。完整请求/回执在nexo目录。

17:15只读核对Nexo待验收页，成果/五项证据/未审查判断正确；NXUSE-006待验收指引及NXUSE-007未提交差异入口疑问持续，已追加台账。截图nexo-user-acceptance.png与完整nexo-issue-snapshot.txt保留，使用复核学习索引 `7e73dd52-74ec-4deb-8e69-13f93daec8c5`。没有修改Nexo代码、配置或直接操作其数据库。
