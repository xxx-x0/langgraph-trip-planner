# LangSmith P0：兼容验证与历史样本盘点

日期：2026-10-24（Asia/Shanghai）。依据用户确认的[首期方案](eval-observability-phase1-plan.md)，本轮只推进 P0。

**结论：现锁版本可支持首期主要 API，16 项本地探针与 LangSmith 云端合成样本实测通过。用户后续授权补采后，T18/R10 两个材料缺口已闭合，替代素材与独立计算参考已冻结为 v2；人工质量标注、正式旅行 eval 和 P1～P5 实现尚未完成，不代用户验收。**

本轮没有改运行代码、原虚拟环境、依赖锁、业务数据库、原始历史证据或现有服务进程；没有 Git 提交。只更新交接/方案与仓库外探针、材料。最初兼容验证没有请求模型、地图、票务；后续按用户授权读取一次真实 12306 列表，并完成 24 次高德路线工具调用（含一次限流重试），见第 8 节。没有调用真实 LLM。LangSmith 只上传过合成算术样本及探针结果；本次旅行补采材料未上传。

## 1. 隔离范围与证据

仓库外目录：`${EVIDENCE_ROOT}/eval-p0-20261024/`。

从当前 Python 3.12.13 环境中按 `backend/requirements.lock.txt` 离线复制 75 个已安装分发包，建立新的 venv；75 个版本全部与锁一致，依赖约束检查无缺失。不安装、不升级原环境。隔离环境导入路径已核对，`langsmith==0.8.9`、`langchain-core==1.4.0`、`langgraph==1.2.4`。

原环境实际共有 135 个分发包；隔离环境只有锁定的 75 个。原环境包版本清单、原 `pyvenv.cfg`、前后端锁文件、`backend/data/trips.db` 前后核对一致。数据库仅以文件字节读取 SHA256，没有 SQLite 连接，也未导入业务 app。

| 证据 | 内容 |
| --- | --- |
| `evidence/environment.json` | 离线复制方法、锁版本核对、文件数 |
| `evidence/dependency-check.json` | 75 个分发包的活动依赖约束检查，issues 为空 |
| `evidence/sdk-signatures.json` | 实际安装 SDK 的方法签名和模块位置 |
| `evidence/sdk-local-pytest.log`、`sdk-local-junit.xml` | 最终 16 个本地探针通过，2 个 SDK 警告 |
| `evidence/sdk-first-attempt.log`、`sdk-first-attempt-junit.xml` | 首轮失败保留，未改写成一次通过 |
| `evidence/upload-false-limitation.json` | `upload_results=False` 仍产生 PATCH 的最小复现摘要 |
| `evidence/offline-evaluation-rows.json` | 人工算术目标 3 例×2 次，共 6 条结果，包含错误 |
| `evidence/candidate-search.json`、`historical-inventory.json` | 搜索范围、文件数、历史来源 SHA、缺失项及路线覆盖 |
| `evidence/preservation-before.json`、`preservation-after.json` | 原锁/环境/业务库保持不变的核对 |
| `evidence/cloud-smoke.json` | PASS，最终实测 54 次 HTTP 请求，dataset/trace/feedback/两组实验创建及回读通过 |
| `evidence/cloud-smoke-first-attempt.json` | 配置填写完成前首次 auth_read 失败，1 次请求；未创建云端成果 |

隔离 Python 首次采用复制解释器时遇到 macOS dylib 路径问题；仅在新 venv 内改用标准解释器符号链接解决。未修补原 Python 或原虚拟环境。

## 2. 实际验证内容与边界

探针使用真实锁定 SDK，HTTP 由内存 `requests.Session` 模拟传输，真实 socket 连接被禁止；LangGraph 节点与 LangChain 假模型也在隔离环境执行。它们验证 SDK 调用/序列化/运行语义，**不是 LangSmith 云端可用性、真实 DeepSeek 或旅行业务质量的证明**。

| 能力 | 本地结果 | 证据及限定 |
| --- | --- | --- |
| traceable 父子关系 | PASS | 并发两条操作 trace 不串，父子 ID 与各自输入匹配 |
| async generator | PASS | 第一个事件发出时未结束，遍历完成后根 span 才结束；正式 SSE 仍需 P1 接口验证 |
| 取消传播 | PASS | CancelledError 向上传播，trace 以错误状态结束，不转成功 |
| LangGraph/模型调用 | PASS | 节点可见、共用 trace；假模型 usage 字段保留且只有一个 LLM run |
| 输入/输出脱敏 | 有限制 | I/O 脱敏不自动覆盖异常 error 文本，见第 3 节 |
| 全 run 脱敏钩子 | PASS（本地人工探针） | `process_buffered_run_ops` 覆盖本例输入、metadata、tags 和异常；不代表已完成所有真实字段白名单 |
| feedback | PASS（模拟响应） | 可创建/解析；comment 必须额外脱敏，不能指望 I/O 脱敏设置 |
| dataset/report API | PASS（模拟响应） | 数据集创建/列表、run 详情/列表和 URL 生成可用；另有第 6 节云端小样本验证，大规模分页一致性尚未验证 |
| aevaluate 重复和失败 | PASS（显式离线适配） | 6 条记录完整保留：2 个正确、2 个错误答案、2 个目标异常；并发/重复有效 |
| evaluator 抛异常 | PASS | 保留结果行，score 为 null、error 标记为真，不能算 0 分或丢弃 |
| 禁止导出 | 有限制且有替代办法 | 原 `upload_results=False` 仍发 PATCH；显式 LocalOnlyClient 后捕获请求为 0 |
| 队列和关闭 | PASS（局部机制测试） | SDK 支持队列上限；设 2 后不阻塞地丢弃；close(timeout=.05) 在 .25 秒内返回。使用 SDK 内部队列方法测试，不等于完成应用 A03/A04 性能验收 |
| 传输失败/禁用追踪 | PASS | 模拟连接失败不改变业务函数返回；显式关闭 tracing 时不导出 |

官方 API 能力与当前安装签名均已核对。参考：[异步评估](https://docs.langchain.com/langsmith/evaluate-llm-application)、[LangChain 追踪](https://docs.langchain.com/langsmith/trace-with-langchain)。

首轮 3 个失败中，2 个暴露同一离线导出问题，1 个是探针模拟响应错误地返回 attachments 字段；后续模拟 project 响应补齐 SDK 要求的 reference_dataset_id。模拟响应错误属于探针实现问题，不计为 SDK 不兼容。最终 16 项包含“限制可复现”检查，不能解释成“SDK 无限制”。

## 3. P1/P2 必须采用的兼容处理

### 3.1 离线模式需要显式禁止导出

在锁定 0.8.9 中，`aevaluate(..., upload_results=False)` 的目标执行路径仍会产生 run PATCH；通过模拟 session 捕获，没有真实发出请求。源码 `_arunner._aforward` 中的 tracing context 与 run 结束路径可解释该现象。

P0 已用隔离 `LocalOnlyClient` 原型验证：create_run/update_run 保持本地，feedback/network API 显式禁止；结果行及 evaluator 分数仍完整。原型不修改 SDK，不进入运行应用。

后续离线 runner 应强制使用无导出 client，同时保持网络边界断言；业务 LLM 的出站与观测上传应独立控制。不能仅依赖 `upload_results=False`、环境变量或未配置密钥作为隐私边界。不要直接替换全局 SDK client 影响其他会话。

### 3.2 脱敏覆盖范围需包含 error、dataset、feedback

`hide_inputs / hide_outputs / hide_metadata` 只处理对应字段；异常 error、其他 run 字段、数据集和反馈不是自动安全的。

后续采用上传前全 run 处理钩子＋数据集/反馈显式转换；run 名称与 tags 使用固定词，不拼原始用户输入；本地日志也需要独立脱敏。所有 child runs 都使用同一受控 client。禁止附件/原始网页原文进入首期导出。

`process_buffered_run_ops` 批处理要求保持 run 数量和 ID 次序，不可用返回更少 run 的方式实现采样。钩子失败时 SDK 记录错误并可能丢失该批，应用需要可见的导出失败状态。P0 的 redactor 只是替换人工 marker 的机制验证，不是可用于真实数据的完整脱敏实现。参考：[官方脱敏范围](https://docs.langchain.com/langsmith/mask-inputs-outputs)。

### 3.3 队列、关闭及序列化

锁版支持 `LANGSMITH_TRACING_QUEUE_MAX_SIZE`（源码默认 10000）和 `Client.flush(timeout=...) / close(timeout=...)`；首期可将队列明确设 1000、关闭等待 2 秒，无需为此先升级依赖。应用层仍须记录丢弃/导出失败，不能把 SDK 警告当完整运行监测。

buffered run ops 与普通 tracing queue 是不同的缓冲；批处理线程池、失败可见性和完整进程退出时间仍需 P1 压力/中断验证，不能从本例 .05 秒 close 推导所有组合都满足 2 秒退出。

报告读取使用 SDK 的 schema 和分页接口，应用只暴露脱敏后的稳定 DTO；不依赖 LangSmith UI HTML 或手拼租户 URL。

## 4. 历史样本盘点

### T18：原 80 条铁路候选

找到并记录 SHA 的原始文件包括：

- `2026-10-20-ltp27/train-initial.json`、`train-before-confirm.json`、`train-saved.json`。
- 同目录 `train-default-recommendations.txt` 和 `live-verification.json`。
- `2026-10-20-ltp26-ltp27-followup/` 的 0.2.1 初始/保存快照、推荐与排除说明可作后续参考。

原日程快照有 **7 景点、13 正餐、27 路段**；原文本可提取 **48 条排除记录**，与历史交接一致。但文本不是完整候选输入：缺少全部 80 条候选各自的到达时间、票价、余票等结构化字段，也没有独立的可行参考集合。

在相关 ticket/LTP-27/meal-recovery 历史目录及仓库 `output`、`.playwright-cli` 的限定文本文件中扫描 1127 个文件（具体目录/排除项/5MB 上限见搜索清单）。仅找到另一份 **3 条人工转录候选**的完整 request，日期为 2026-10-27，不能替代原 80 条浏览器采集。

**首次盘点状态：BLOCKED_MISSING_CANDIDATE_BATCH；后续已用新批次闭合材料缺口，见第 8 节。** 原批次仍未恢复。搜索结论仅限已记录范围，不宣称其他位置绝不存在原文件。不能从交接数字倒造 80 条输入，或将排除文字复制成独立 gold。

首次盘点提出恢复原抓取或授权新采集；用户随后已授权后者。新版本保留完整候选字段、来源 DOM 行、采集时间及旧快照哈希，不能冒充找回旧批次。

### R10：更少绕路的每日重排

找到 `2026-10-14-meal-recovery/` 中 `real-initial.json`、前后 AI/最终草稿、实际 AI 输出及出站观测。它们能证明原日程与当时执行路线，不证明所有替代顺序。

以原第一天虎丘→留园→七里山塘为候选素材，留园锁在第 2 位。在同日历史结果中共找到 **9 对有向地点组合**。保持正餐间隙、交换首尾景点后，最低限度的候选“七里山塘→留园→虎丘”仍缺 **4 条有向路线**；原顺序路线齐全。

独立核对只读现有 JSON，不调用生产 route/schedule 生成答案，不将反向路线视为同一条，不混用不同方式时长或推算缺失分钟。更广泛餐厅选择所需路线只会更多，当前没有证据证明一个完整、可行且更短的替代方案。

**首次盘点状态：BLOCKED_INCOMPLETE_ALTERNATE_ROUTES；后续路线缺口已补齐，见第 8 节。** 原始留样本身仍只证明已执行路线；新版本另有完整限定范围的路线矩阵与独立可行参考，人工质量复核保留到 P2。

用户已授权有界补查。v2 明确标为历史日程＋新采集路线的混合来源，没有人工编造路线，也不再称为纯历史路线回放。

## 5. P0 数据契约结论

现 SDK 可承载方案要求的匿名关联、metadata、评分 key/score/extra 与 reference example；建议保持以下应用契约，P1/P2 实现时按版本固化：

- run：operation_id、匿名 session、target、source/replay/live/injected、业务版本、技术状态、业务结果、export_status。
- check：rule_id、layer=model/system/observability、status、score（缺失 null）、expected/actual、evidence_path、evaluator_version。
- experiment：dataset ID/version/hash、source hash、prompt/model/evaluator 版本、计划/完成/错误/未评估计数、重复编号。
- report：本地缓存时间、云端读取状态、缺失原因、来源限制；前端永远拿不到凭据。

P0 的 6 条离线算术结果与 4 条云端目标结果只是 SDK 兼容材料，不属于首期 30 个旅行案例。T18/R10 已有仓库外来源夹具及参考计算；其余案例、正式评分器业务实现、70 条运行及工作台页面均未开始。

## 6. 已完成的 LangSmith 配置与云端实测

已经创建权限为 `0600` 的仓库外文件：

`${USER_CONFIG_DIR}/langsmith-p0.env`

只在该文件填写，不改 `backend/.env`，不把密钥发送到聊天或提交仓库：

```dotenv
LANGSMITH_API_KEY=你的密钥
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_WORKSPACE_ID=
LANGSMITH_PROJECT=trip-planner-p0-20261024
```

1. 登录 [LangSmith](https://smith.langchain.com)，在 Settings → API Keys 创建 PAT 或具有对应 workspace 权限的 service key。需要 trace 写入/读取、dataset 与 experiment 操作；仅能上传 trace 的 tracing key 不够。[官方密钥说明](https://docs.langchain.com/langsmith/create-account-api-key)
2. Endpoint 必须对应实际账号区域。文件预填 GCP US；EU 为 `https://eu.api.smith.langchain.com`，其他区域按账号界面/官方文档填写。涉及多个 workspace 时填写目标 workspace ID；单 workspace 如权限要求也应显式指定。[区域与 workspace 配置](https://docs.langchain.com/langsmith/trace-with-langchain)
3. 用户已填写并确认；本次 endpoint 与权限实测可用，workspace 未显式填写也可完成上述操作。当前无需追加配置，不需要在业务后端打开 tracing 或重启现有服务。

仓库外 `scripts/cloud_smoke.py` 默认只检查配置是否存在，传 `--run` 才会实际执行。首次在配置填写完成前读取时，auth_read 返回 LangSmithAuthError，未创建成果；用户确认“填好了”后重新读取配置，最终实测 **PASS**。首次失败证据单独保留。

最终使用 2 条人工算术样本完成 dataset 创建/回读、根子 trace、脱敏回读、feedback 写入/回读、两组小实验和报告查询。基线两例得分为 1/0，对照为 1/1；两组均回读到 2 个根 run，与预期一致。未调用模型、地图、票务，不上传历史业务素材；按 P0 前缀保留成果，不删除已有云端数据。脚本设置同域请求限制、单请求超时和最多 80 次请求，实际 54 次，不启用无限重试。

云端数据集名称：`trip-planner-p0-20261024-70ffa116-synthetic-two-examples`。

实验名称：

- `trip-planner-p0-20261024-70ffa116-baseline-e517f5f5`
- `trip-planner-p0-20261024-70ffa116-comparison-c9153639`

[本次父子 trace（SDK 返回的实际链接）](https://smith.langchain.com/o/cd4706cf-1ded-47da-ac8c-f69796e819a1/projects/p/d6c8a8a5-b026-4a33-b428-6b47a99ac23c/r/a8b8ef03-5458-4aac-b419-c3361cbd18fc?poll=true)。访问需要对应 workspace 权限。

这里的算术“错误版/正确版”仅检验比较接口，绝不作为旅行 AI 改善证据。人工敏感 marker 的云端回读未检出，不代表首期全部真实字段脱敏验收完成；云端小样本也不能替代 P1 并发、断网、压力和退出验证。

## 7. 下一步与验收状态

| 项目 | 当前状态 | 剩余工作 |
| --- | --- | --- |
| 原环境/业务库保留 | PASS（本轮核对） | 后续继续保持隔离 |
| 75 锁版 SDK 本地可用性 | PASS_WITH_LIMITATIONS | 采用离线 client、全 run/反馈/数据集脱敏；应用接入另验 |
| 云端权限/写读/实验 | PASS（合成样本） | 当前无需用户追加配置；业务接入及压力另验 |
| T18 来源材料完整性 | READY_V2（新批次替代） | 旧日程＋新 80 候选；35/45 可行性参考；P2 人工排序标注 |
| R10 备选路线与参考答案 | READY_V2（混合来源） | 23 条有向路线覆盖 20 排列，2 个改善参考；P2 人工质量复核 |
| 本次 P0 两个材料缺口 | CLOSED | 来源/哈希/独立核算已留证；不等于正式 eval 或用户体验验收 |

云端配置当前无需追加；两个材料缺口已经按后续授权闭合。应用契约仍须随实现固化，后续进入 P1/P2 时再接入运行代码和正式评分器，本次没有自动扩大到该阶段。

## 8. 2026-10-24 授权补采与 v2 冻结材料

用户明确授权：“找不到原始材料就重新采集候选、补查缺失路线，明确标记新旧数据来源，仍保持现有运行环境和业务库不变。”

隔离产物目录：`${EVIDENCE_ROOT}/eval-p0-20261024/supplement/`。总清单为 `manifest.json`，逐文件记录 SHA256、字节数、版本及来源。保留首次盘点和云端验证证据，不覆盖成“首次就齐全”。

### 8.1 T18：新采候选＋旧完整日程

- **旧数据**：`2026-10-20-ltp27/train-initial.json`，完整苏杭 7 天日程、酒店/餐厅、市内路线及缓冲；旅行日期仍为 10 月 26 日至 11 月 1 日，没有平移日期。旧市内供应商事实未重新核价或验证。
- **新数据**：北京时间 **2026-10-24 19:28:27**，12306 普通单程、11 月 1 日杭州→南京，全天、不预筛出发时段。页面共 156 个车次；只保存班次、站点、时刻、历时、席别参考价和余票等限定字段，无账号、订单、购票 token 或整页 HTML。
- **提取**：其中 128 行有支持的可用席别，按既有席别优先顺序和全天均匀采样规则取 80 条；每条候选保留对应 DOM 行与席别标签，28 条在采样前跳过的原因另存。通过浏览器只读 DOM 采集并离线归一化，**不是扩展重新实装测试**。
- **独立可行性参考**：已保存安排结束 13:15，保留接驳 60＋候车 60＋酒店办理 30＝150 分钟，因此最早可行出发为 **15:45**。新批次 **35 条保留、45 条排除**，逐条保存窗口、余量和原因。旧 48/32 只保留为旧证据，不挪用为新答案。
- **边界核对**：G7376 15:37 出发余量 −8 分钟，应排除；G3106 15:48 出发余量 3 分钟，可行但紧张；G3342 16:16 出发余量 31 分钟。没有要求模型必须首选 G3106，也没有生成模型排名。
- **价格口径**：保留这次列表参考价与采集时间，同行确认总价仍未知；余票不保证持续可售。未购票，未调用推荐模型，未采用到任何业务行程。

文件：`raw/T18-rail-dom.json`、`raw/T18-historical-snapshot.json`、`fixtures/T18-input.json`、`fixtures/T18-reference.json`、`evidence/T18-extraction-audit.json`。类型为 `mixed_historical_itinerary_and_new_capture`，版本 `T18-v2-20261024`。可行集合由独立区间算术核定；T-RANK 的人工可接受集合留 P2 标注，不能将程序计算声称为真人复核。

### 8.2 R10：完整限定路线矩阵与改善参考

**旧数据**沿用 10 月 14 日留样中的 10 月 15 日苏州日程：虎丘 150 分钟、留园 90 分钟、七里山塘 90 分钟，留园锁定在第 2 个景点，原午晚餐与酒店事实保留。原 POI/营业资料来自历史快照，不能把归档时间当成每个字段的原始查询时间。

明确本例范围为当前三景点、两家已存正餐、原酒店，不更换餐厅；提示词写明保留游览时长、锁定位置及正餐，仅调整景点顺序与正餐插入位置。两种合法景点顺序与午餐先于晚餐的全部插入方式共有 **20 个排列**，需要 **23 条有向边**。首次的“缺 4 条”只是固定原用餐间隙的最小交换；完整范围实际缺 15 条，另 8 条已有边用于同批复核。没有用反向边、不同交通方式或距离估算补时长。

北京时间 **19:30—19:31** 从高德官方 MCP 实际采集：补 15 条缺边＋复核 8 条已有边；近距离按原策略步行，其余公共交通，固定采用供应商首个返回方案。一次步行查询返回 `CUQPS_HAS_EXCEEDED_THE_LIMIT`，保留失败文件后只重试一次，成功；共 **24 次路线工具调用、23 条完整路线**，没有伪造成功降级或人工路线。采集边界未导入业务应用或连接数据库。

比较统一使用这一批新路线：原顺序 **180 分钟**；独立枚举后 3 个排列符合已知营业、最晚入园、餐次、锁定和日长约束，其中 2 个分别减少 **18 / 42 分钟**。最佳参考为：

`酒店 → 七里山塘 → 原午餐 → 留园 → 虎丘 → 原晚餐 → 酒店`

交通分钟逐段为 `4＋16＋27＋36＋33＋22＝138`。留园 13:17—14:47，虎丘 15:23—17:53，两顿正餐各 60 分钟，酒店办理结束 20:18。营业窗口按旧资料中 10 月季节区间独立解析；餐厅重复时段取保守交集。原始秒数保留，即使逐边向上取整，该参考仍能满足本例已知窗口，结束 20:24。

**旧保存路线总计 168 分钟，不能拿它与新备选作改善比较。** 新查询原顺序已变为 180 分钟，特别是酒店→虎丘由旧 32 分钟变为新 48 分钟，差异逐边保留在 `evidence/R10-old-new-comparison.json`。输入中的固定基线时间轴由独立算术按新矩阵重建，旧原始 JSON 单独原样留存；没有将旧叙述/预算当成刷新后质量结论。

高德 MCP 工具没有出发日期/时刻参数，因此新结果是**10 月 24 日查询所得的冻结路线事实**，不能声称还原了 10 月 15 日实时交通，也不能保证实际出发时交通或营业仍相同。该案例整体标 `mixed_historical_day_and_new_route_capture`，版本 `R10-v2-20261024`；23 条边各自标新采集，人工路线数为 0。模型执行和真人质量验收均未进行。

文件：`raw/R10-historical-snapshot.json`、`raw/R10-route-*.json`（含原限流与 retry 文件）、`fixtures/R10-input.json`、`fixtures/R10-reference.json`、`evidence/R10-coverage-plan.json`。参考与输入分开保存；后续模型不得收到可行集合或参考答案。扩大餐厅池、交通策略或允许的编辑范围时必须生成新版本与补齐相应路线。

### 8.3 核对与保持不变

`scripts/verify_fixtures.py` 的 **15 项材料核对通过**：80 条候选逐字段对来源、独立时间阈值与边界、23 边/20 排列完整覆盖、缺边检出、坐标方向、锁定/时长/营业与无重叠、改善算术和向上取整敏感性。它不导入生产 `ScheduleCheck.evaluate`、`multicity.projection` 或 `schedule_day`，也不调用网络。这些是材料核验，**不是正式模型 eval 的 15 个成功案例**。

补采前后 **196 个受保护文件哈希一致**，包括业务源码、前端源码、扩展源码、后端配置、依赖锁、原 venv 配置及业务库；没有 SQLite 连接、应用导入、服务重启、依赖安装或 Git 提交。原环境包版本另行复核。产物经本机实际凭据匹配扫描无命中，输入不含本机绝对路径；该检查也不替代 P1 正式全字段脱敏验收。

本次没有把材料上传 LangSmith，也没有运行模型排序/重排、业务保存或工作台页面。下一阶段可使用这些冻结素材完成 P2 独立人工质量标注与正式数据集构建；用户无需为本次补采增加 LangSmith 配置。
