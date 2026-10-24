# LTP-9 错误分类与酒店会话兼容修复交接

> 历史快照：本页的版本、测试数、端口、未提交/无Git提交与验收状态对应页内日期，不代表当前状态。当前源码和回归口径见[维护基线](../README.md#verification-baseline)；本机证据未随仓库发布。

2026-10-15，继续 LTP-9（本机内部记录，链接未公开）。用户后续授权仅在隔离环境修复前轮发现的兼容问题，补故障、真实链路与回退验证，**当前运行依赖和应用源码不切换**。前轮研究、失败与验收快照见 [初次交接](ltp9-handoff.md)，本轮不把历史失败改写为已通过。

工作根目录为 `${EVIDENCE_ROOT}/2026-10-15-ltp9-compat/`。以下证据路径相对此目录。239 个起点文件、两个原环境精确 freeze、业务 SQLite 均先备份；main / HEAD 仍为 `57bd8a46f5d4ea3c638ca23998f78bed19806f3e`，未创建 Git 提交。迁移实现及新增自动测试在 `source/backend/` 副本，仓库只同步交接、路线图、AGENTS 和 Nexo 台账。

## 本轮修复

**错误分类**：`source/backend/app/services/external_calls.py` 在保留 httpx 兼容的同时可选识别 httpx2 的超时、连接、读写及远端协议异常，空消息也不依赖字符串猜测。读取 HTTPStatusError.response.status_code，401/403 为认证、429 为限流、5xx 为不可用，其他4xx为输入/请求错误。直接状态与明确异常类型优先于偶发异常上下文；SDK 的 RuntimeError 包装则沿 cause/context 查找原类型，嵌套 ExceptionGroup 有确定优先级，循环引用与未知 data 有界处理。

错误仍在公共边界转换成脱敏 ExternalServiceError。认证/普通4xx不重试，连接、超时、限流和服务不可用最多两次；只有连接/超时触发 reset。取消直接向上传递，排队、重连、清理与回退不重置总期限。模型认证失败不能当作“不支持结构化输出”而继续调用 JSON 模式。

**酒店会话**：`mcp_adapter_trial.py` 仅对 aigohotel 使用 `HotelHTTPTransport`，明确 legacy 握手，避免对已知旧服务发送现代 server/discover 探测。高德与 Bing 仍保留各自 SSE，其他 HTTP 目标没有套用酒店策略。

`hotel_http_compat.py` 在应用副本实现一个限定版本的兼容 transport，未改 site-packages、SDK 常量或全局客户端：

- GET 405 是“不提供独立消息流”的能力响应。每个 transport 实例真实收到一次后记住该能力，不再开启后续 GET，不把405伪造成200；新客户端/reset重新核对。支持的 GET 仍读取 SDK 消息并在操作结束关闭，不增加后台重连循环。
- DELETE 200/204 正常结束，404 表示会话已不存在，405 表示服务不接受主动删除；均按实际清理状态记录。没有删除这类出站记录或禁用认证。其他清理失败仍抛出，不能通过隐藏警告让业务看起来成功。
- POST 404 只有带 session ID 时才解释为会话失效，返回 connection 让公共边界 reset 并重新握手；没有 session 的404仍为请求错误。POST 401/403、429、500/503保持失败语义。
- SDK 2.3 会把部分 POST HTTP 错误转成没有状态码的通用 MCPError；兼容层在转换前保留真实分类，以原 request ID 关联一个明确失败的 JSON-RPC 响应传给等待者。直接往流写裸 Exception 只会通知 SDK observer，不能完成该请求；本轮使用关联错误，避免无故等待至超时。错误 data 只带安全分类，不带 URL、密钥或响应正文。
- 上下文按操作持有，HTTP 客户端随上下文关闭；尝试清理会话最多1秒且仍受外层取消/期限约束，不长久跨 FastAPI 请求持有异步上下文。这个上限不证明远端一定完成了清理。

旧协议对 GET405、会话过期和清理的要求见 [MCP 2025-11-25 transport 规范](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)；实现接口与限制对照 [Python SDK transport](https://py.sdk.modelcontextprotocol.io/api/mcp/client/streamable_http/)。酒店只使用实际已验证的旧握手，不把旧服务假装成现代无会话服务。

## 固定环境与回归

本轮没有再次追最新版。候选精确沿用前轮111包：langchain1.4.6、core1.6.10、openai集成1.7.2、OpenAI SDK3.31.0、LangGraph1.2.15、FastMCP4.1.0、MCP2.3.0、httpx2/httpcore2 2.13.1。`candidate.lock.txt` / `candidate-freeze-final.txt` 逐项相同；基线和回退仍为当前75包锁。均通过 pip check。

| 验证 | 结果与证据 |
| --- | --- |
| 最终候选完整后端 | 360通过、4外部smoke跳过；`backend-tests-final.log` |
| 本轮新增 | 60项：双HTTP库真实异常/状态/SDK包装、空消息、嵌套/循环、优先级、取消、模型认证不降级；本地TCP酒店transport及API失败保留 |
| 酒店本地HTTP | 17项；JSON和POST SSE、GET405只探一次、可用GET、DELETE404/405与500、POST400/401/403/429/500/503、过期会话、真正TCP断流/HTTP读超时、初始化403、期限/取消后可继续；`transport-extra.log` |
| API保存保护 | 新httpx2超时/连接错误通过真实API和隔离SQLite验证：失败状态码及可重试提示正确，原JSON和锁定不变，重试可保存；新模型403不触发JSON能力降级 |
| 前端 | 现有58通过；类型检查/构建通过，原大包提示保留；`frontend-tests.log`、`frontend-build.log` |
| 原锁回退重建 | 新建env-rollback，安装原75锁、pip check、300通过/4跳过；`rollback-verification.json`、`rollback-3.log` |
| 分类修复对照 | 前轮五类httpx2空消息误作tool_error，本轮两HTTP库及403/500等20个同样输入分类正确；`error-probe-fixed.json` |
| SDK未修改 | 新环境SDK transport源码SHA与前轮相同，修复仅在副本应用层；`preservation-audit.json` |

本地TCP/HTTP故障由 fixture 明确注入，不是实际酒店发生401、限流或断流的证据。取消测试证明本地调用能结束并释放容量，不声称所有远端服务器都同步取消了正在执行的工作。4项 smoke 仍跳过，不冒充通过。

常规300项没有覆盖本轮缺口，新增60项测试必须随未来迁移一起带入，不能只复制 transport。完整候选补丁 `candidate-full.patch` 是相对当前应用的代码/测试增量；`compat-only.patch` 只对照前轮迁移原型，便于审查这次修复。

## 真实服务验证

`hotel-only-candidate/` 只调用真实酒店服务，与其他provider及两日流程分别观测。连续搜索两次、对真实搜索返回的ID查询详情、显式reset后再搜索，四次业务调用全部成功；工具事实/价格来自实际响应，不进行预订。`verification.json` 七项核对通过：两个客户端各真实收到一次GET405，后续无重复GET；无server/discover，业务POST无HTTP错误，DELETE404保留为清理事实，四次真实tools/call。

前轮有GET405自动重连和DELETE404告警，本轮没有相同重连循环，也没有“Session termination failed:404”错误解释。真实404响应本身仍存在；修复的是客户端对它的处理，未证明服务端改变。前轮一次POST500与自动探测有关的推断仅是因果候选，本轮明确legacy后没有出现该请求，不据此宣称上游所有500均已解决。

`probes-candidate/` 独立验证高德工具/重置后天气、酒店工具/搜索、Bing工具及DeepSeek JSON/function_calling。Bing实际搜索仍被拒绝，未改搜索策略或把HTTP协议回执当业务成功。模型支持结构化调用，本轮没有实际触发“不支持后的JSON回退”；该分支由模拟回归覆盖。

首个两日流程 `real-candidate/` 在补强分类优先级前完成34项检查，保留为过程证据；最终流程使用最终代码重新启动到18012、独立新库和新查询，位于 `real-final/`。两者都重新发现苏州2026-10-16～17的六个景点、天气、酒店及餐饮，再装配两日、手动锁定/改时间、AI重排、定稿与重复保存/历史回读。不是复用旧候选冒充本轮查询。最终源码指纹在 `final-runtime-source-manifest.json`，后续审计核对与真实运行一致；最终结果及耗时见文末补充。

网络记录按 real / probes / hotel-only 分目录；独立酒店记录还标记provider，URL仅在内存匹配，不写凭据路径。最终链路逐API耗时来自 `timings.json`，不混入独立probe做调用次数比较。不同网络/模型输入下的单次观察不能证明性能收益。

## 成本、保留与再现

新酒店transport通过FastMCP的ClientTransport接入，但为了修复当前SDK行为，依赖 MCP2.3 的 StreamableHTTPTransport、部分受保护方法和内部 context stream 工具；这是明确的版本耦合，不是稳定官方扩展承诺。未重写 JSON-RPC/POST SSE解析，而是复用SDK framing/分派；新版SDK升级须重新核对该接缝。长期可等待SDK公开支持配置或等价修复后删除此桥接，本次不替用户修改上游服务或发Issue。

当前111包/beta接口风险仍在；本次局部兼容已获得隔离证据，不代表全部平台、MCP通知、交互elicitation、所有营业日、酒店可订或建议价值通过。应用没有改变ORM。正式切换仍需用户另外决定，当前保持原环境。

复现应复制到新实验目录，使用 `candidate.lock.txt` 安装精确111包，应用 `candidate-full.patch` 到当前源码的副本，在隔离DATABASE_URL下运行 `pytest -q`。本轮完整脚本与版本、最终源码、测试、补丁均保存在证据根目录。不要在当前工作区应用补丁或把实验数据库覆盖业务库。

回退已实际重建原75环境，使用原源码运行300项。还会用该环境只读解析候选保存的历史/草稿，核对候选事实、定稿幂等和数据库未被读取改写；最终记录见文末。正式采用失败时应停止候选并恢复启动指向原源码+原环境，不在同一venv逐包降级；本轮从未切换，无须恢复业务库。

`preservation-audit.json` 核对所有239起点文件、备份、非本轮文档字节、原HEAD和业务SQLite行/结构，dotvenv/plainvenv本次独立精确快照均保留；不再依赖前轮被覆盖的起点freeze。`task-changes.patch` 和 `final-files/` 为本轮文档交付，代码与测试以隔离补丁单独审查。凭据仅进程内读取，最终扫描结果 `credential-scan.json`。

Nexo继续原LTP-9的新会话 `internal-record-043`。此前USER请求保留为历史，本轮重新提交，以最终回读记录为准；没有代用户验收。原生工具本轮可用，按 [使用台账](nexo-usage-log.md)记录复核；不捏造Nexo产品故障，也不将本地测试脚本问题归入Nexo。精确收尾/提交和最终回读见 `nexo/`。

## 最终真实与回退结果

最终运行对应 `final-runtime-source-manifest.json`，真实两日34项全部通过，草稿/历史各1条，定稿重试返回同ID/内容。读取兼容和事实核对28项通过：两轮的景点/票价、餐饮坐标/均价/来源、酒店坐标/价格/货币/ID均沿用实际候选，旧75包环境可解析全部保存JSON；只读核对前后数据库SHA不变，见 `facts-and-rollback-read.json`。

最终单次阶段：发现112.346秒、骨架57.197秒、两日装配7.706/8.049秒、手动重算7.522秒、AI重排10.625秒、定稿0.014秒；全部11次API合计203.478秒。网络/服务及模型均有波动，不把与前轮169.540/178.805秒的差异归因于兼容修复。独立酒店探测只证明无重复GET和失败语义正确，不能据此声称旅行规划变快。

另将公共分类修复单独放入原75包源码副本（未安装httpx2）运行：300通过、4跳过，`baseline-fixed-tests.log`；证明其可选依赖不会强迫当前栈新增包，也没有据此应用到当前运行目录。回退新建环境仍使用完全未修的原源码和原75锁，300通过。两个验证目的不同。

18011/18012本轮试验服务均已停止，原有服务未停止。Nexo最终会话/验收状态由收尾回读补充；正式运行依赖仍待后续单独决定。

## Nexo 收尾回读

- 会话 `internal-record-043` 已COMPLETED v5；交接 `internal-record-030`。
- 五项USER请求 `internal-record-011` 已提交并回读PENDING，Issue v4、无活跃会话；未代用户接受。
- 学习记录 `internal-record-061` v1，关联本轮修复和台账。
- 精确输入/回执及最终读取为 `nexo/close-input.json`、`acceptance-input.json`、`issue-final.json`、`session-final.json`。本次仅验收隔离成果，不改变当前运行依赖。
