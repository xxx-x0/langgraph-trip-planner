# LTP-9 MCP 迁移与分步升级评估交接

> 历史快照：本页的版本、测试数、端口、未提交/无Git提交与验收状态对应页内日期，不代表当前状态。当前源码和回归口径见[维护基线](../README.md#verification-baseline)；本机证据未随仓库发布。

2026-10-15，[LTP-9](http://127.0.0.1:3000/issues/85b44ef6-521c-4a52-aa21-42957bd9bb88)，USER 验收。此次完成隔离研究，**建议暂缓切换当前运行依赖**。新接口可完成真实两日流程，但尚不能作为完整兼容升级发布：新增 httpx2 异常类型没有被现有外部边界正确识别，酒店服务还有会话兼容噪声，迁移依赖面扩大且接口仍为 beta。当前应用源码、requirements、package-lock、原环境和业务库均未升级；所有迁移实现仅在仓库外副本。没有 Git 提交。

证据根目录：`/Users/finn/.local/share/nexo-codex/handoffs/2026-10-15-ltp9/`，以下文件名相对此目录。原 main / HEAD `57bd8a46f5d4ea3c638ca23998f78bed19806f3e` 仅是基线，不包含既有或本轮未提交成果。238 个现有文件已保存带 SHA 的起点副本；本轮仓库只增加本交接并更新 AGENTS、路线图和 Nexo 台账。

## 评估范围与依据

范围为后端 LangChain / LangGraph / MCP / OpenAI SDK 的依赖闭包；Python、FastAPI、前端框架不做主动升级。前端验证使用现有 node_modules 和 package-lock，在副本输出构建产物。仅验证 macOS、Python 3.12.13；没有验证 Windows、Linux 或全部声明支持的 Python 版本。

2026-10-15 重新读取官方文档、实际 PyPI 元数据和候选 wheel 源码，没有沿用 10 月 13 日“最新版”作为已验证目标。来源与事实如下：

- [官方迁移说明](https://docs.langchain.com/oss/python/migrate/langchain-mcp-adapters)：新入口要求 `langchain[mcp]>=1.4.0`，仍为 beta；配置改为 MCPConfig / 单目标，错误和会话行为变化。
- [旧适配器仓库](https://github.com/langchain-ai/langchain-mcp-adapters)：已归档、停止积极维护；升级到 0.3.2 也不能解决未来维护归属问题。
- [FastMCP transport 文档](https://gofastmcp.com/clients/transports)：SSE 为兼容传输；应按服务真实能力显式构造 SSE 或 HTTP，不能要求用户控制不了的远端立即迁移。
- [LangGraph v1 迁移说明](https://docs.langchain.com/oss/python/migrate/langgraph-v1)：当前自定义 StateGraph 无需改成 create_agent。此次保留现有图与草稿 API。
- 当日 [PyPI](https://pypi.org/project/langchain/) 元数据快照 `pypi-metadata.json`；候选 `langchain/mcp` 源码在 `upstream/`。声明的 Python 下限为 3.10，不等于全部平台已实测。

| 包 / 约束 | 当前锁 | 隔离候选及约束 |
| --- | --- | --- |
| langchain-core | 1.4.0 | 1.6.10，需要 protocol ≥0.0.17；实际 0.0.19 |
| langchain-openai | 1.1.9 | 1.7.2，需要 core ≥1.6.10、OpenAI ≥2.45,<4；实际 SDK 3.31.0 |
| langgraph | 1.2.4 | 1.2.15，需要 core ≥1.4.7、checkpoint ≥4.3.0、SDK ≥0.4.6 |
| checkpoint-sqlite | 3.1.0 | 3.1.2，需要 checkpoint ≥4.3.0；应用仍不启用检查点执行 |
| langchain-mcp-adapters | 0.2.2 | 0.3.2，仍要求 MCP SDK <2；不能与 MCP 2 一起保留 |
| 新入口 | 未安装 langchain 主包 | langchain 1.4.6，需要 core ≥1.6.10、graph ≥1.2.12；mcp extra 要求 FastMCP ≥4.0.11,<5 |
| FastMCP / MCP SDK | 当前锁只含 MCP 1.27.2 | FastMCP 4.1.0 / MCP 2.3.0；引入 httpx2/httpcore2 2.13.1 |

## 分步结果

| 隔离环境 | 安装与变化 | 回归 / 结论 |
| --- | --- | --- |
| env-baseline | 当前精确锁，75 包 | pip check；300 通过、4 smoke 跳过；作为对照和回退 |
| env-adapter | 75 包，仅 adapters 0.2.2→0.3.2，其余锁不变可解析 | 同为 300/4；两种本地 transport 契约通过；没有维护或性能收益依据，不切换 |
| env-ecosystem | 78 包，10 项版本变化、增加 httpx2/httpcore2/truststore | 同为 300/4；本地契约和真实服务探测完成；未单独跑完整两日流程，不作为独立发布认证 |
| env-migration | 从 75 包重建，删旧 adapter，新增37项、变更10项，最终111包 | 试验副本 300/4；本地契约及真实两日完成；存在下述错误分类兼容失败，暂缓采用 |
| env-rollback | 再从原75包锁全新安装 | pip check 与 300/4；基线代码可只读解析候选保存的数据 |

`*-freeze.txt` 为实际环境精确版本；`*-dependency-diff.json` 给出完整闭包。ecosystem 严格只改顶层版本时，原 protocol 0.0.16 与新 core 冲突，解析失败证据 `ecosystem-strict-resolve.log`。随后仅对目标框架解除必要闭包约束，未整体更新无关包。111 是保留基线其他依赖的试验环境总数，不是最小可安装闭包。

前端现有版本 58 项通过，类型检查/生产构建通过；已有大包警告保留，见 `frontend-tests.log`、`frontend-build.log`。四组后端日志 `tests-{环境}.log`，新副本最终完整复验发生在标量包装修正后。模拟服务回归、真实外部调用与下述故障注入分开解释；4 项 smoke 的跳过不算服务验证成功。

## 配置、错误与生命周期

迁移试验位于 `migration-source/backend/app/services/`，增量为 `migration-trial.patch`，不能直接应用到当前运行目录。

1. 三个服务分别持有一个 MCPAdapter，避免多服务配置自动加前缀破坏现有工具名称。高德、Bing 显式 SSETransport，酒店显式 StreamableHttpTransport；URL 和凭据沿用配置，仅在进程内读取原 .env，不复制它。
2. 工具发现和每次调用各自进入、退出客户端上下文；不在 FastAPI 请求任务里长久持有异步上下文。reset 丢弃工具/客户端引用，下次重新发现；关闭入口不跨任务退出一个早已关闭的 context。
3. 实际验证新工具 `.ainvoke(arguments)` 在 `isError=True` 时可只返回正文列表；必须以 ToolCall 形式调用，检查 ToolMessage.status。直接换 import 会把失败当作正文成功。`contract-migration-*.json` 保留两种调用对照。
4. 结构化结果来自 ToolMessage.artifact.structured_content；原文本字段也保留解析。SDK 自动把标量返回包装为单个字符串 result 时，试验副本解包该传输包装。第一次两种 transport 的相等断言失败已保留在 `*-initial.json`，修正后通过；未隐藏失败记录。
5. 本地真实 TCP 断开后重启 fixture，基线/迁移均为首次失败→一次 reset→重新发现→第二次成功，未重复追加图/SDK工具重试。`reconnect-*.json`；这是本地注入故障，不是外部服务真实中断。
6. 本地 SSE、Streamable HTTP 均验证 0.3 秒总期限、显式取消向上传递、随后重新调用成功；server-cancellation 文件确认服务端任务收到取消。应用 SSE 的 EOF/终止语义沿用现有前端回归，真实发现/骨架/定稿均核对完整终止事件。

**尚未解决的兼容失败**：`error-probe-initial.json` 用实际库异常类构造空消息的 ReadTimeout / ConnectTimeout / ConnectError / ReadError / RemoteProtocolError。httpx 五类识别正确，httpx2 五类均落为 tool_error，不能得到预期 timeout/connection 的重试及提示。另 HTTPStatusError 的 response.status_code 未被通用分类读取，403/500 在两套 HTTP 库中均可误分类；后者是原边界已有缺口，不归因于新接口。新环境成功回归不能掩盖这些失败。本次不修当前运行代码，也不将该原型称为可直接合入版本。

正式迁移前须补充两套 HTTP 库与 SDK 包装异常的契约，读取真实 response 状态，覆盖失败→有限恢复→最后失败提示，并将这些断言纳入常规回归。SDK 的 HTTP GET 后台流重连与一次工具重发须分别计数，所有等待仍受外层总期限限制。没有评估无限期保持会话、服务端 elicitation/interrupt、人机恢复或所有多模态返回；现有业务只消费工具，不使用 MCP prompts/resources。

## 真实服务与两日流程

三种环境独立 probe 结果位于 `probes-baseline/`、`probes-ecosystem/`、`probes-migration/`。高德15工具、酒店3工具、Bing2工具均发现成功；高德显式 reset 后天气和酒店真实查询成功。DeepSeek V4 Pro 的 json_prompt 和 function_calling 均实际成功；真正“不支持能力后回退”只由模拟回归验证，本次服务支持工具调用，不能称实际触发了回退。

Bing 实际搜索失败，迁移 SDK 抛 MCPError，服务返回“当前输出可能包含不当内容”。`probes-migration/bing-raw-diagnostic.json` 保留脱敏原始诊断；工具发现成功不等于搜索业务可用，两套适配路径都没有得到有效搜索结果。

酒店新客户端日志出现 GET 405、DELETE 404 的会话兼容提示，以及一次规划期间 POST 500；独立查询和最终流程成功，但不能消除这些协议异常或证明酒店可订。保留原日志和出站记录，正式采用前需要核对服务端支持及 SDK 会话终止/重连策略，避免增加不必要请求。

两组均在新 SQLite 中重新发现景点、查询天气、酒店和餐饮，使用这次发现的六个景点分为两天：苏州 2026-10-16～17。没有复用旧旅行的候选/天气响应。每组完成发现→骨架→两日装配→手动锁定/开始时刻→AI重排→定稿→重复定稿→历史回读，各34项检查通过；每库仅1条历史。结果与模型建议保存在 `real-{环境}/`，候选位置/价格/来源及旧环境兼容读取另24项通过，见 `facts-and-rollback-read.json`。

| 单次阶段，秒 | 当前锁基线 | 新 MCP 试验 |
| --- | ---: | ---: |
| 新发现 | 92.093 | 94.748 |
| 骨架 / 候选 | 48.242 | 52.731 |
| 第一天装配 | 6.487 | 6.667 |
| 第二天装配 | 6.620 | 6.769 |
| 手动编辑 / 重算 | 6.505 | 8.612 |
| AI重排 | 9.565 | 9.246 |
| 定稿 | 0.010 | 0.013 |
| 全部11次API合计，含回读/重试 | 169.540 | 178.805 |

这是一组网络/模型条件下的观察，两个流程部分重叠执行并有独立探测；没有统计显著性，也不是受控性能基准。每次发现使用空的新库，进程内允许当前缓存；未进行冷/热缓存多轮比较。没有证据证明迁移提升性能。各环境 `outbound.jsonl` 同时包含链路和独立探测，不从混合日志推算单条旅程的调用次数；API阶段耗时来自独立客户端 `timings.json`。

真实成功仅说明此次功能可走通。复杂营业日、预约、门票未知、餐饮/酒店实时可用性和建议最优性仍保留限制；没有用户实际旅行或独立价值验收。

## 回退与再现

本次从未切换运行环境，因此无需对当前应用执行降级或恢复业务库。实验服务18009/18010已在验证后关闭，仅停止本轮创建的两个进程；既有服务保持原状。离线审查 JSON/日志不需要重启服务。

后续若用户决定正式升级，应把旧源码和旧75包环境完整保留，候选用独立端口/独立库验证后再切换启动指向。失败时停止候选进程，使用原源码+原环境启动；不要在同一 venv 逐包降级，也不要把实验库覆盖业务库。此次没有ORM变更；若后续加入结构变更，须另外准备迁移/备份/恢复验证，本次只证明当前JSON可被基线读取。

复现可在新目录中执行（不要覆盖现有证据）：

```bash
# 先阅读证据目录中的 setup.py / install_migration.py；配置只从原.env进程内读取。
# 基线/回退重新安装：将目标路径设为一个新的实验venv。
uv venv --python 3.12 /tmp/ltp9-new-baseline
uv pip install --python /tmp/ltp9-new-baseline/bin/python -r backend/requirements.lock.txt
uv pip check --python /tmp/ltp9-new-baseline/bin/python
PYTHONPATH=backend DATABASE_URL=sqlite+aiosqlite:////tmp/ltp9-new-tests.db /tmp/ltp9-new-baseline/bin/python -m pytest -q backend/tests
```

完整实验脚本为 `setup.py`、`install.py`、`install_migration.py`、`prepare_migration.py`、`regressions.py`、`run_contracts.py`、`contract_probe.py`、`reconnect_probe.py`、`error_probe.py`、`observer.py`、`real_chain.py`、`live_probes.py`、`rollback.py`、`facts_audit.py`、`preservation_audit.py`。它们使用本机证据路径；复制复现前改为新根目录及空闲端口，不覆盖已保存实验。最终候选版本以 freeze 文件为准，重新解析可能产生新版本，需对照差异。

## 保留、审查与后续

`preservation-audit.json` 核对238起点文件均在、备份匹配、非本轮文档字节未改、HEAD及业务SQLite表/行未改、plain venv原freeze未改。原 .venv 为134包，与此前LTP-8保存的134锁逐项一致；起点采集脚本误把 `.venv` 和 `venv` 使用同一输出文件名，覆盖了 .venv 的本次精确freeze快照，不能宣称仍持有该快照。已修正复现脚本，使用此前已验证锁及本次75包约束复核；安装命令全部指向仓库外。该证据局限、第一次安装重建和原型首轮失败均在 `verification-notes.json`，不归为Nexo故障。

`task-changes.patch` 只含本轮文档增量；`final-manifest.json` / `final-files/` 提供审查快照，既有未提交代码和 CV 保留。`credential-scan.json` 检查配置凭据值未进入本轮新日志/交接；不复制.env或连接令牌。

建议下一阶段：先在独立兼容修复中处理 httpx2/HTTP 状态分类、补故障契约，再核实酒店生命周期噪声；保留单provider无前缀和ToolMessage/artifact边界。随后用同一明确版本锁重新跑两日全链路、失败恢复与冷/缓存对比，才提议运行环境切换。旧adapter0.3.2只是低改动候选，不能作为长期维护方案。暂不同时升级前端、Python或改图架构。

Nexo会话 `2b65c7e9-1a69-43d4-8390-ca1cfc6b962f`。执行/回归/真实链路与失败事实已记录；[Nexo台账](nexo-usage-log.md)追加原生连接本次可用及请求UUID校验代理问题。未修改Nexo产品；本轮未复验旧页面引导问题，不推断它们已经修复。会话关闭、五项USER验收请求及最终回读记录在 `nexo/`；验收属于本次研究交接，不是授权运行升级或宣告兼容失败已修复。最终状态见文末补充。

## Nexo 最终状态

- 执行会话已关闭为 COMPLETED v5，交接 `b9caac6f-a067-4415-aeea-3fd137a04af4`；本轮创建的实验服务已停止。
- 五项 USER 请求 `4668354e-21f7-422a-b07a-9b4b9443eb61` 已提交并回读 PENDING，Issue v4、无活跃会话；未代用户验收。
- 学习记录 `f5c60561-96f9-4a76-880a-f7358f928db6` v1，关联本次研究与台账入口。
- `nexo/close-input.json`、`acceptance-input.json` 保存精确输入；`issue-final.json`、`session-final.json` 为最终原生工具回读。研究标准的PASSED表示完成核对/留证，不表示候选兼容失败已修复或运行升级已获接受。

用户后续授权继续隔离修复（2026-10-15）：双HTTP库分类及酒店会话兼容原型、60项新故障回归、最终真实两日与回退已完成，详见 [后续修复交接](ltp9-compat-handoff.md)。本文件保留初次研究与失败的历史快照；运行依赖仍未切换，新的USER请求见后续交接。
