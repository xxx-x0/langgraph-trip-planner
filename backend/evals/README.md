# 首期离线评测数据与评分器（P2）

本目录包含 18 个票务推荐、12 个每日 AI 重排案例和 22 条评分规则。当前为 `trip-eval-v1` / `1.0.1-draft` / `rules-v1.1`，不是已经完成的模型质量实验。全部 30 份参考答案仍为 `pending_human`，judge 未校准；20/10 目前仅为场景分组，同源人工模板跨组，不能声称独立泛化评估。

P3 已加入隔离运行器和报告，见下文；P2 的 validate/review/score/selftest 仍保持纯离线。

## 数据及来源

- `datasets/cases/`：案例元数据、适用性矩阵、来源组件、SHA256、人工复核状态。
- `datasets/inputs/`：完整冻结输入；`references/`：独立参考草稿；`routes/`：12 份有方向的路线夹具。
- `datasets/manifest.json`：102 个资产文件的字节哈希、内容摘要、分组复核状态。
- T01～T17、R01～R09、R11～R12：28 个代理编写的人工构造样本，`synthetic`，不是人工已标注数据或真实供应商报价。
- T18：历史苏杭日程 + P0 于 2026-10-24 补采的 80 个铁路候选；R10：历史苏州单日事实 + P0 同日补采的 23 条有向路线。新旧来源分组件记录，P2 没有再次采集。原始材料只在仓库外归档，仓库保存脱敏投影和来源哈希。

公共 POI 名称、地址、坐标及必要时刻保留；用户 ID、联系方式、密钥、Cookie、原始自由文本、图片/网页 URL 和本机路径不进入数据集。`clock` 是固定实验时钟，不能当成采集时间，来源时间以 `sources` 为准。

## 本地命令

在 `backend/` 下使用现有兼容 Python 环境，不需要安装依赖、启动服务、设置 LangSmith 或连接数据库：

```bash
python -m evals validate
python -m evals review --output /tmp/trip-eval-review.json
python -m evals selftest --output /tmp/trip-eval-selftest.json
python -m evals score --input /tmp/captured-observation.json --output /tmp/trip-eval-score.json
```

本机验证使用 `${EVIDENCE_ROOT}/eval-p0-20261024/venv/bin/python`。命令不导入业务应用、数据库或 LangSmith SDK，也不读取 `.env`；环境里误设 tracing 开关不会上传这些离线材料。

`selftest` 只用人为构造的已知输出测试评分器，标记 `SCORER_SELFTEST_ONLY`，真实模型调用数为 0。T13 的非法模型 ID 应得到模型层 FAIL、系统回退通过，这是预设正确行为。不能将该命令的通过率用作模型或产品成绩。

`score` 默认不评分尚待人工确认的参考依赖项，返回 NOT_EVALUATED；`--allow-provisional` 仅用于诊断，并保留 provisional 标签，不代表人工确认。T18 首选参考仍为空，即使诊断也不虚构排名分数。

如需从 P0 原件重建，使用 `python -m evals.build_dataset --p0 <supplement目录> --output <新的空目录>`。不得用重建覆盖人工复核后的版本；修改参考或分组需递增版本、重新生成资产/manifest 哈希并重新复核。原件路径见交接文档。

## 评分与证据契约

`contracts.Observation` 接收独立采集的执行证据：原始模型结构化建议、最终原生响应、系统过滤集合、逐候选判断、保存前/并发最新/保存后 JSON、HTTP/业务状态、模型调用次数、trace 树、恢复次数和取消后的调用次数等。缺证据保持 null，不填成功默认值。案例 ID、版本及输入摘要必须匹配冻结案例。

P3 运行器从真实业务函数/路由及隔离 SQLite 采集这些字段。`before_state` / `latest_state` / `after_state` 使用保存 JSON：票务沿用输入的 `saved_state`，每日为 `request` + `days_detail`。种子 ID 固定为 eval ID，保存 JSON 原样回读；不能拿参考答案、期待值或自行补齐的列表冒充执行证据。

`dataset.model_inputs()` 只提供模型可见的业务字段；票务必须传入**实际系统观测的** eligible IDs，不能用参考集合代替待测过滤器。参考答案、故障脚本、人工状态不能放入被测模型 prompt。评分逻辑不调用生产的 ScheduleCheck、projection 或 schedule_day 来反推正确答案。

| 规则 | 主要检查 |
| --- | --- |
| T-VALID / T-ELIG | 选择属于原候选及实际可行集、唯一且数量正确；过滤集合逐项比较并报告 FP/FN |
| T-FACT / T-MARGIN | 班次、站点、价格来源、未知同行总价及保存缓冲不编造；所有候选的余量和 <=30 分钟提醒 |
| T-RANK / T-DISCLOSE / T-OUTCOME | 可接受首选及偏好顺序；未知/紧张/回退说明；成功、全冲突、取消、两处旧版本拒绝等预期结果 |
| R-LOCK / R-REMOVED / R-MANUAL / R-MEAL | 锁位、删除集合、手动餐厅位置、正餐数量及餐次；原始模型和系统修正分开评 |
| R-FACT / R-DURATION / R-REST | 候选事实、游览时长、固定休息区间及重叠 |
| R-WINDOW / R-INTENT / R-ROUTE | 独立区间核对营业/最晚入场/餐次/交通窗口；明确编辑意图；同批有向路线矩阵的真实减少 |
| R-DISCLOSE | 修正或保留旧安排是否明确说明，不把回退说成需求完整达成 |
| S-PERSIST / S-TRACE | 成功仅变目标日、失败/过期保留最新保存状态、恢复次数与期限；trace 父子关系、闭合、步骤、实际调用及用量不重复 |
| J-INTENT / J-TRADEOFF | 系统说明的 0/1/2 语义评分契约；当前没有调用 judge、没有真人校准成绩 |

确定规则为 0/1；judge 为 0/0.5/1（原始 0/1/2），保留证据路径。Judge 必须有单独的操作者校准记录 `JudgeCalibration`（12 份、人工一致和重复一致均至少 10 份）并匹配版本；模型返回的“已校准”字段无效。当前 CLI 不启用 judge，Python API 可接收经核实的校准记录。单元测试的校准记录完全是测试替身。

缺少必需证据、缺路线、评分异常为 ERROR；不适用为 NOT_APPLICABLE；待参考/未校准为 NOT_EVALUATED。R10 不反向借边、不填估算路线、不访问地图兜底。披露规则目前校验当前中文模板的结构标记及关键词，不代表通用语义理解。

汇总分开 target / split / source / execution_mode / provenance / layer / rule。P/F/E/U/NA 保留全部分母：已评分通过率=P/(P+F)，覆盖率=(P+F)/(P+F+E+U)，完成率=P/(P+F+E+U)；空分母为 null。故障注入、自检、真实模型执行不混算，重复 case/run 不得重复计数。每案的 `formal_acceptance` 只表达已确认参考下的系统硬约束，不是整个实验或独立保留集已验收；还须检查数据集 `formal_ready`、分组、人审和实验协议。

人工待办见 [复核清单](../../docs/eval-observability-p2-review.md)，验证证据与边界见 [P2 交接](../../docs/eval-observability-p2-handoff.md)。

## P3 隔离运行器与报告

在 `backend/` 使用同一 Python，输出必须是仓库外的新目录：

```bash
python -m evals.experiment prepare --directory /tmp/trip-eval-demo --repeats 3
python -m evals.experiment run --directory /tmp/trip-eval-demo
python -m evals.experiment report --directory /tmp/trip-eval-demo
python -m evals.estimate --directory /tmp/trip-eval-demo --repeats 3 --output /tmp/trip-eval-quote.json
```

默认 baseline + current_replay：前者使用同一生产可行性检查和规则排序 / 每日 no-op；后者走真实推荐/每日路由、修正、事务、CAS 和 Trace，模型边界用固定替身，地图按冻结矩阵回放。替身不读取参考，也不根据 hint 求解最优答案；每日默认保留当前顺序，因此意图评分失败正常。故障脚本使用输入中的 fault，经确定屏障注入。8 个故障案例在基线为 N/A。3 次重复时为 30 基线槽位 + 70 当前槽位，仍只有 30 个独立案例。

每个槽位是新进程、新 SQLite；输入原样入库，源代码与数据复制到实验目录。只复制明确的 py/json 源文件，不复制 .env、业务库、历史日志或个人资料。manifest 冻结源码内容（含未提交/未跟踪源码）、锁、实际 Python 包版本、数据、模型参数、预算和分组状态。环境采用白名单，默认拒绝网络、外部 SQLite、参考答案与 .env 文件访问；本地 Trace 不导出。

`--cases T01,R01` 可选子集，`--max-slots 1` 可分批推进；重复运行会跳过已经有结论的槽位，失败也不自动重试。单进程锁防重复调度。实验目录创建 `CANCEL` 文件或向运行器发送 SIGINT/SIGTERM 可停止，删除 CANCEL 后可继续尚未调度部分；不重新执行已取消/失败/中断的槽位。需要重试应新建实验。上次进程不明的 RUNNING 槽位标 INTERRUPTED，不重发模型请求。

默认并发 1、总墙钟 1200 秒、单槽 120 秒，可在 prepare 时设 `--wall-seconds` / `--slot-seconds`；不能中途放宽。预算停止、未运行和 worker 失败均留在计划分母。实际 110 秒重排期限的 R11 故障验证使用缩短时钟并记录这一点，不能称等待了真实 110 秒。

产物为 `manifest.json`、`ledger.json`、每槽 observation/engineering/SQLite/Trace，以及 `report.json`、`report.md`、`checks.csv`。报告把整份 pending_human 案例列为诊断，正式分数为空；不是只排除部分主观规则。按规则/模型系统层/来源/分组分开统计，重复先汇总到案例，不能冒充更多独立样本。操作墙钟与进程启动时间分开，p50/p95 仅统计成功操作；超时/取消仍保留自身状态和耗时。

### 真实模型的调用前门禁

`evals.estimate` 从离线运行实际捕获的生产 prompt 计算粗略 token 区间与预算预留，标明假设、费率来源和日期。v1入口固定直接 DeepSeek V4 Pro、json_prompt、非思考模式；本机当前Flash默认模型由下文v2入口验证。按峰时缓存未命中保守估算；不是服务账单，未知 usage/费用不填 0。

真实调用须先向用户展示估算，再明确使用该 estimate 哈希。CLI 不会从默认离线模式自动升级为在线：

```bash
# 仅在已披露费用、用户明确要求开始之后操作；这里不包含凭据内容。
python -m evals.experiment prepare --directory /tmp/trip-eval-live --variants baseline,current_live --repeats 3 --estimate-file /tmp/trip-eval-quote.json
python -m evals.experiment run --directory /tmp/trip-eval-live --approve-estimate <estimate_sha256> --credentials-file <本机现有配置文件>
```

估算必须匹配源码、数据、模型、案例与重复数。密钥仅从显式配置读入子进程环境，不进入 manifest/job/报告；仅允许 api.deepseek.com:443，票务、地图和 LangSmith 仍不联网。每次模型请求前预留输入字节估计＋8192 输出 token，按最大尝试数预留请求/token/费用；整个实验与每个槽位同时受限。实际 usage 仅取服务响应，缺失、超额、账单不明会停止继续调度并保留预留，不自动退款或用 0 掩盖。正式联网批量尚未执行；传输实测需后续授权。

P3 修复了 P2 输入时间轴缺少 start_time/end_time 的可执行性问题：只从已有分钟数派生显示文本，案例版本升为 1.0.1-draft，参考/路线未改。评分器 rules-v1.1 接受生产的 wait 区间（仍检查重叠和时长）；生产在日期校验提前返回、未计算余量的候选保留缺证据 ERROR，不补造余量。实际取证显示的其余诊断分歧见 [P3 交接](../../docs/eval-observability-p3-handoff.md)。

## P4 只读质量工作台

P4 从已冻结 P3 报告发布脱敏展示快照，不执行模型、数据库迁移或云上传。当前参考全部待人工确认，页面正式成绩为空；失败归因侧注只作诊断，不改原评分或答案。页面 `/quality/runs`、`/quality/experiments`、`/quality/runs/:runId`。

从 `backend` 运行（使用现有隔离 Python，不安装依赖）：

```bash
python -m evals.workbench \
  --experiment /path/to/frozen-experiment \
  --usage-audit /path/to/live-results.json \
  --annotations evals/workbench_findings.json \
  --output "$HOME/.local/share/langgraph-trip-planner/quality-workbench"
```

本次侧注绑定 `02329411…` 计划，其他实验不可沿用；可省略侧注，未归因失败显示待分类。`--usage-audit` 可省略，无法核定的真实费用显示未知。导入器验证冻结源码和证据哈希，拒绝覆盖已发布同一实验 ID。原始报告、SQLite、prompt 和配置文件不由网页直接提供。

```bash
QUALITY_WORKBENCH_ENABLED=1 python -m uvicorn evals.serve_workbench:app --host 127.0.0.1 --port 18027
```

独立预览入口只挂载质量 API，不执行业务主应用 startup。`QUALITY_REPORT_DIR` 可指定只读快照目录；默认关闭，关闭时不读取目录。开发模式显示入口，生产演示构建另需 `VITE_QUALITY_WORKBENCH=1`；这不构成公开部署授权或认证。前端代理可通过 `VITE_BACKEND_URL=http://127.0.0.1:18027` 设置，现有 `.env` 无需改写。更多实际用量、限制与验证见 [P4 交接](../../docs/eval-observability-p4-handoff.md)。

## P5 条件化偏好 v2（离线）

`python -m evals.conditional validate` 校验12份独立版本的场景草稿；`python -m evals.conditional replay --directory /tmp/p5-conditional-new-run` 在仓库外新目录生成冻结源码/依赖manifest、逐场景隔离SQLite/Observation与JSON报告。它只有离线入口，禁止网络/凭据/业务库访问，没有真实模型或judge模式。

数据在 `conditional_cases.json`，原30例、rules-v1.1及旧实验不变。新意图必须与输入哈希/场景版本匹配，旧真实输出不能直接按新偏好打分。多答案、并列、偏序和分阶段缺证据分别处理；未说明偏好不评分排名，待人审参考只作诊断，正式成绩始终null。12变体来自5个已见基础材料，不增加独立holdout。

本轮替身报告单独保存，不导入P4真实实验统计。运行范围、实际回放与限制见 [实施交接](../../docs/eval-observability-p5-implementation-handoff.md)。上文P3首次制定时“正式联网尚未执行”仅为历史状态；后来60次真实请求及费用见 [P3真实交接](../../docs/eval-observability-p3-live-handoff.md)，不代表本模块已获真实调用授权。

## v2 真实批次的独立入口

`evals.conditional`继续只做离线；`evals.conditional_live`按单独披露并批准的Flash预算执行。prepare/report不调用模型、不读取凭据，prepare只接受仓库外新目录。用户确认后才能使用run：

```bash
python -m evals.conditional_live prepare --directory /tmp/v2-authorized-run --estimate-file /path/to/budget-proposal.json
python -m evals.conditional_live run --directory /tmp/v2-authorized-run --approve-estimate <approved_estimate_sha256> --budget-usd 0.36 --credentials-file <existing_local_configuration>
python -m evals.conditional_live report --directory /tmp/v2-authorized-run
```

执行清单单独冻结适配后的源码/依赖，并核对产品代码、参考、输入及提示词仍匹配已批准估算。每槽独立进程/SQLite；只向模型槽传入凭据，只允许直连DeepSeek 443。运行器和每次请求均预留请求/token/费用，提示词哈希不符在派发前拒绝。用量未决、预算停止、取消或上次RUNNING中断不会自动重发；并发锁和`CANCEL`文件继续适用。`--max-slots 1`可先核对计划内首槽回执，再续跑剩余槽，不增加重复请求。

报告区分原始模型与系统修正/回退，保留全部计划槽位、来源、Trace及费用回执；全部待审参考只出诊断，正式成绩为空。费用优先按响应缓存和可确定的非峰时请求区间核算；遇跨费率时段或节假日口径未定则保持未知，并另列峰时全未命中上界，不能冒充供应商账单。范围与已批准预算见 [v2验证计划](../../docs/eval-observability-v2-live-validation-plan.md)。

## v2.1 离线修复验证

`conditional_cases_v21.json`与`conditional_v21.py`单独升版，原v2.0数据、评分语义及27次真实批次保留。新Observation须绑定`2.1-draft-PSxx`，旧真实输出不能直接套用v2.1评分。PS06只比较已知价格的子序列，未知项摆放位置不评分，未知也不能当最低价；PS10检查`empty_preferences`，与日程冲突、混合约束和可用性空结果分开。

```bash
python -m evals.conditional_v21 validate
python -m evals.conditional_v21 replay --directory /tmp/v21-new-offline-run
```

此入口只有离线模式，冻结源码/数据/版本，每槽新进程和SQLite，不能读取凭据、业务库或联网。当前价格/车程指标直接对全部可行候选排序，因此12场景中9个路径不调用模型，PS03/PS05/PS12使用中性替身；不把替身计为真实请求或质量改善。PS12从同一冻结路线提供器获得有向事实，未知边保留未知，默认替身仍可能不改善路线。

首期T13原为price目标下的非法模型ID注入；当前数值路径不经模型，新增证据明确标记`injection_exercised=false`，不能把它当新故障检出。兼顾路径的非法ID回退继续由独立测试覆盖。v1估算器只适用于实际捕获到模型提示词的场景；新行为若要真实重验，须另建匹配新源码、路径和提示词的估算与授权，不复用旧US$0.36预算。

本轮实现、离线结果与旧证据保护见 [v2.1交接](../../docs/eval-observability-v21-offline-handoff.md)。

## v2.1 真实模型对照入口

`evals.conditional_live_v21`执行单独批准的v2.1报价，旧v2入口和历史报告保留。`prepare`/`report`不读凭据、不调用模型；`run`须绑定用户批准的报价哈希与US$0.30上限：

```bash
python -m evals.conditional_live_v21 prepare --directory /tmp/v21-authorized-run --estimate-file /path/to/v21-budget-proposal.json
python -m evals.conditional_live_v21 run --directory /tmp/v21-authorized-run --approve-estimate <approved_estimate_sha256> --budget-usd 0.30 --credentials-file <existing_local_configuration>
python -m evals.conditional_live_v21 report --directory /tmp/v21-authorized-run
```

本协议固定21槽：9个确定性票务路径不调用模型，PS03/PS05各1次，PS12有/无新增路线输入各5次。PS12奇数组先有输入、偶数组先对照；两组使用相同冻结日程、路线提供器及后处理，对照只在实际模型边界删除整个新增路线输入段。变换后再捕获提示词、记录Trace别名、校验批准哈希与预留预算，不能让较小的对照预算发送较大的完整提示词。

执行前冻结源码和75包隔离环境，核对产品源码、输入、参考、报价资产及依赖锁；逐槽预留最坏22次、385862 token、US$0.2779602，每次请求另受提示词/输入/输出/费用限额约束。授权不符、输入漂移、用量未决、取消、预算停止或上次执行中断不会自动追加请求。可用`--max-slots 13`核对计划内首组，再续跑剩余槽；已完成槽不重发，账本预留不可中途缩小。

JSON/Markdown/CSV保留全部槽位、模型原始输出、系统结果、Trace、回执及来源。PS12按冻结有向矩阵独立计算交通分钟、原始秒数、等待、结束时间和硬约束，未改善、拒绝、执行失败、证据不足均保留在各组5次分母内。待审参考只用于诊断，正式成绩为null；同一已见日程重复5次不等于5个独立保留样本。费用按响应缓存及核实的请求时段计算，跨时段/节假日依据不足时保持未知，另列峰时全未命中上界，不当作供应商账单。

2026-10-26已授权批次完成12次真实请求，PS12两组均0/5改善，具体失败与费用见 [真实对照交接](../../docs/eval-observability-v21-live-handoff.md)。此结果不修改旧实验或代表人工验收，也未自动发布到P4工作台。

## v2.2 业务修复后的离线验证

```bash
python -m evals.conditional_v22 validate
python -m evals.conditional_v22 replay --directory /tmp/v22-new-offline-run
```

独立的`conditional_cases_v22.json`与新Observation版本保留旧数据、参考和真实报告。此入口仅离线：逐槽新进程/SQLite、冻结源码和依赖、拒绝网络/凭据/外部库，没有live或judge选项。9条票务路径不使用模型，PS03/PS05/PS12使用中性替身；PS12的系统改善来自业务的有界路线比较，原始替身仍可被判为未改善，两层结果分开报告。

PS12的新评估契约使用已声明窗口或本地日期结束边界，不继续使用未输入的22:00截止；晚餐最迟开始随本日60分钟用餐和日期边界推导，不暗加个人的晚间偏好。原营业/最晚入场参考仍待人审，新版和首期参考均不自动确认，正式成绩始终null。旧版本真实输出不能换标签重评为v2.2。

Trace将详细混合来源映射到有限枚举`mixed`，报告保留完整来源类型；输入补查缺边与最终路线失败分开记录。新增路线比较span只记录状态、次数及用时差，不上传原始提示词或自由文本。旧US$0.30授权绑定的源码/提示词已变化，不能用于本次新实现的真实调用；需要另行披露范围、调用量和费用。

结果、保护范围与限制见 [v2.2离线修复交接](../../docs/eval-observability-v22-offline-handoff.md)。
