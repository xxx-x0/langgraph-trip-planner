# P4：只读质量工作台交接

日期：2026-10-25（工作目录沿用启动日期 `eval-p4-20261024`）。已接入 P3 的真实实验，完成运行记录、实验比较、案例详情与本地 Trace。**30 份参考仍待人工确认，所有指标只用于诊断，正式成绩为 null / NOT_EVALUATED。**本轮没有新增模型请求、judge 或云上传，没有修改依赖、运行 `.env`、业务库或提交 Git。

## 直接查看

- [运行记录](http://127.0.0.1:15175/quality/runs)
- [评估实验](http://127.0.0.1:15175/quality/experiments)
- [R02 意图未完成与 Trace](http://127.0.0.1:15175/quality/runs/current_live-R02-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8)

15175 为本次独立前端预览，代理到 18027 的 quality-only 后端。该后端只挂载质量接口，没有主应用启动事件、业务数据库初始化、草稿清理或模型客户端。现有其他端口和业务运行配置未替换；预览进程退出后可按下文重启。

本批次仅有本地 Trace，**没有上传 LangSmith，也没有可验证的云端运行链接**。页面明确展示此状态，不拼接 workspace/run URL，不把“未查询云端”显示为“云端正常”。本次不需要配置 LangSmith。

## 页面与口径

运行记录默认显示 `current_live` 的 70 个槽位；基线需切换方案或选全部。摘要与分页共用筛选结果，支持案例搜索、链路、来源、执行性质、诊断分类、dev/holdout、技术状态、业务结果、日期和仅失败/缺证据。筛选、实验选择、详情及比较对象写入 URL，刷新保留。高级筛选折叠，真实用量和诊断摘要优先展示。

| 默认当前方案统计 | 数值 / 意义 |
| --- | --- |
| 完成 / 计划 | 70/70；30 个独立案例 |
| 真实请求与用量 | 60 次；65,660 tokens；用量覆盖 60/60 个真实模型运行 |
| 计算费用 | US$0.02273084；按实际 usage、缓存与运行时周末费率计算，未核账单 |
| 峰时全缓存未命中保守值 | US$0.09609336；不同于费用计算值，也不是预算花费 |
| 原批准预算 | US$3.23895924；全实验上下文，不随筛选误称实际花费 |
| 有 FAIL/ERROR 的诊断 | 22 次运行、9 个案例；不能视为模型失败率 |
| 诊断检查 | P=690、F=39、E=6、U=15、NA=197；适用分母 750 |
| 正式质量 | 未评估；30 份参考待人工确认 |

费用、token 仅聚合真实模型请求；无模型和注入不按模拟 usage 计费。未知用量/费用保留未知与覆盖数。操作 p50/p95 使用技术成功的操作墙钟，失败/超时仍保留原记录；少于 20 次标小样本。技术完成和返回 `adjusted` 不代表完成用户意图。

分类来自绑定本次 plan hash 的 [诊断侧注](../backend/evals/workbench_findings.json)，是代理初步归因，不改参考、不改评分结果：

| 分类 | 默认当前方案运行数 | 案例与说明 |
| --- | --- | --- |
| 模型问题（待人审） | 8 | T03 两次；R02/R10 各三次。意图/偏好或路线改善未完成 |
| 参考口径分歧 | 7 | T10/T11 各三次、T17 一次。平移日程与固定旧时刻的窗口定义不同 |
| 证据缺项 | 6 | T12/T18 各三次。早期拒绝未生成余量，保留 ERROR |
| 故障注入 | 8 | 全部预设故障运行。T13 非法模型 ID 为预设检出；T17 同时有参考分歧 |

分类可重叠，不可相加当唯一失败数。其他未分类诊断保留“待分类”，不会默认归为模型问题。真实模型原始遵循与注入模型检查分开统计；模型/系统层结果不互相抵销。

实验页展示模型、案例、评分器、源码/数据/计划哈希、输入/输出/缓存用量及预算，四组诊断指标之外单列故障注入模型检查和运行成本。不提供综合质量大分数。配对要求数据集、夹具、评分器版本一致，按 case_id + repetition + input_sha256；当前可比较 22 对，40 对缺一侧，另 8 对基线故障不适用。基线一次不复制为三次。版本不同、未完成、NA 或 E/U 保留“无法判断”；正式差值一直为空。

案例详情展示脱敏输入、原时间轴/缓冲/锁定删除、模型建议、最终结果/时间轴、逐项 actual/expected/原因、来源、前/最新/后状态，以及完整候选可行性表。T18 保留两城快照、80 候选与 35 个可行结果；原业务文档/休息标识匿名化。点击检查中的证据字段定位事实面板；候选可按 ID/理由搜索。比较页右侧运行链接可进入同例证据对照，刷新保留。

Trace 展示真实根子关联、步骤状态、耗时及白名单事实；模型调用步骤保留用量。父步骤含子步骤，不将嵌套耗时相加。注入案例明确提示步骤不等于真实供应商请求。缺 Trace、云端未上传与技术失败分开呈现。

## 只读接入与配置

新增实现：

- [导入器](../backend/evals/workbench.py)：验证 plan/report/ledger、冻结 source、Observation/engineering 哈希、逐请求 usage；提取脱敏事实后发布独立展示快照。不会重新执行案例或模型。
- [读取与统计](../backend/app/services/quality_reports.py)、[API 路由](../backend/app/api/routes/quality.py)：仅读发布目录；无 SQLAlchemy、业务 service 或模型调用。拒绝任意路径读取，损坏/不完整报告单列，分页游标绑定筛选和快照。
- [独立预览入口](../backend/evals/serve_workbench.py)：不启动主应用数据库/外部服务。
- [前端页面](../frontend/src/views/quality/QualityView.vue)、[详情](../frontend/src/views/quality/QualityDetail.vue)、[Trace](../frontend/src/views/quality/QualityTrace.vue)、[只读 client](../frontend/src/services/quality.ts)。

API 均为 GET：status、runs、runs/{id}、experiments、experiments/compare、experiments/{id}/export。详情 `download=true` 导出同一份脱敏记录；不存在写入、重跑、改分或上传接口。导出文件没有本机路径、原业务 ID、提示词正文、认证字段或密钥。

`QUALITY_WORKBENCH_ENABLED` 默认关闭，设为 `1` 才读目录；关闭时 API 返回 403，status 只返回关闭状态，不扫描报告。主导航只在开发模式或显式 `VITE_QUALITY_WORKBENCH=1` 的演示构建中，且后端启用时显示。该模式限本机，未增加公开部署/认证能力。

`QUALITY_REPORT_DIR` 默认为 `~/.local/share/langgraph-trip-planner/quality-workbench`。本轮发布文件：

`${EVIDENCE_ROOT}/quality-workbench/eval_38609cdd0f754738b89760d783aa31e8.json`

重启当前预览（已有进程运行时无需重复）：

```bash
cd backend
QUALITY_WORKBENCH_ENABLED=1 ${EVIDENCE_ROOT}/eval-p0-20261024/venv/bin/python -m uvicorn evals.serve_workbench:app --host 127.0.0.1 --port 18027
```

另一终端：

```bash
cd frontend
VITE_BACKEND_URL=http://127.0.0.1:18027 npm run dev -- --host 127.0.0.1 --port 15175
```

若以后在现有主后端启用，使用同一进程环境变量和发布目录即可；本轮没有写入用户 `.env` 或重启原业务服务器。新实验导入命令见 [eval 操作说明](../backend/evals/README.md#p4-只读质量工作台)。已发布同 ID 不覆盖；新评估用新实验 ID，禁止通过改分覆盖原证据。

前端只在内存缓存最多 40 个成功读取结果。断网时显示缓存时间；不同筛选不复用错误缓存，403/404/422 不回退旧成功结果，关闭状态清除缓存。不写 localStorage、业务库或主应用状态，不将未知数据补为零或成功。

## 验证与验收边界

- 后端 **845 passed、4 smoke skipped**；新增 P4 14 项覆盖只读/关闭、过滤分页、精确配对、分母、来源/注入隔离、缺失/损坏/路径拒绝、隐私探针、证据篡改、待审降为诊断和多城事实投影。全部显式使用仓库外 SQLite。
- 前端 **247 passed**（新增 P4 8 项），生产构建通过；修正 App 测试的状态请求 mock，测试不访问真实服务。原大 chunk 提示仍存在，未新增依赖。
- [API 对账](${EVIDENCE_ROOT}/eval-p4-20261024/evidence/api-audit.json)：315 项字段/关联核对，逐个检查 100 槽位的规则状态、诊断资格和已执行槽位的 Trace 根子 ID。不是 315 个新业务案例。
- Playwright 实页：1440 桌面、390 手机亮/暗色，筛选模型问题到 R02、展开模型 Trace、比较到同例证据、刷新定位、候选与脱敏导出；下载内容与发布快照相同。实际网络 offline 验证内存缓存；关闭/空报告使用明确的浏览器响应模拟，不冒充修改了运行配置。
- 键盘 Tab 有可见焦点；减少动态效果时 panel animation=none；详情、实验比较在 390px 的 document/body scrollWidth 均为 390。截图和步骤保存在 [本轮证据目录](${EVIDENCE_ROOT}/eval-p4-20261024/evidence)。

本轮已交付本地报告驱动的 P4；没有接在线业务运行索引、同步 LangSmith、提供真实云端链接或完成 P5 真人校准。A11 的本地筛选/比较/导出/状态已验证，云端链接部分不适用于这份未导出批次；不能写成云端验收通过。真人体验与审美、参考口径、正式质量及账单核销仍由后续确认。

无扰动与最终哈希见 [保护核对](${EVIDENCE_ROOT}/eval-p4-20261024/evidence/preservation-after.json) 和 [产物清单](${EVIDENCE_ROOT}/eval-p4-20261024/evidence/artifact-manifest.json)。474 个原有文件中，469 个哈希相同；5 个授权入口/测试/说明文件发生变更，无意外变化。原环境 135 包、隔离环境 75 包版本相同，业务库、P3 的 194 份源码与原报告/账本哈希相同；HEAD 与暂存区相同。本次新增只读模块与入口，不更改业务算法、ORM、依赖版本或业务数据，既有未提交工作保留。
