# P1：票务推荐与每日 AI 重排 Trace

日期：2026-10-24。状态：**本轮授权的两条链路已接入并完成隔离验证，默认关闭；未提交本轮改动。**

这次交付观测能力，不是 30 案例 eval、建议质量结论或质量工作台。发现/创建草稿、采用预览、SSE 和其他编辑尚未接入；P2～P5 不由本次授权自动推进。原方案见 [实施方案](eval-observability-phase1-plan.md)，材料来源见 [P0 交接](eval-observability-p0-handoff.md)。

## 1. 实现范围

| 入口 | 根操作与子步骤 | 结果区分 |
| --- | --- | --- |
| `ticket_assistant.rank_tickets` | `ticket_recommendation` → snapshot_read / eligibility / model_selection / output_validation / rule_fallback / snapshot_recheck | 正常推荐、规则回退、空结果、过期冲突、取消/超时；只读，不修改行程 |
| `POST /api/trip/draft/{id}/day/{index}/ai-rearrange` | `day_rearrangement` → snapshot_read / model_suggestion / output_validation / constraint_repair / route_calculation / schedule_validation / saved_schedule_recovery / fact_projection / cas_save | 模型建议、锁定/餐次修正、保留原安排、成功保存、422 拒绝、409 冲突、取消/超时 |
| 上述操作内的公共外部调用 | external_queue / external_attempt / external_reconnect / external_backoff / external_result；实际模型调用另有 model_call | 排队、每次尝试、有限重连、退避、缓存命中及固定失败分类；保留原期限/重试所有权 |

`fact_projection` 当前计预算计算；保存前的交通/休息约束及事实说明刷新仍在 `cas_save` 内。子步骤是否存在取决于实际执行分支，例如无候选不会产生模型 span。未进入业务函数的 FastAPI 参数校验错误不创建操作 Trace。

新增 `backend/app/services/observability.py`。现有业务文件只增加观测调用与等价上下文包装，没有修改筛选、排序、锁定、用餐保护、路线、CAS 或原错误返回规则。新增测试为 `tests/services/test_observability.py` 和 `tests/api/test_trace_operations.py`。

## 2. 脱敏与数据契约

- 每次操作生成独立 UUID；父子关系由 ContextVar 传递，并发操作不共用树。草稿 ID、候选 ID、景点/餐厅名、快照以及模型/提示词指纹使用 HMAC 别名；不上传业务 user_id。
- 字段白名单只保留固定枚举、有界数值、布尔值及不透明别名。例如匿名候选的出发/到达分钟、列表价或 null、余票状态，重排前后的顺序、锁定/删除集合、餐次与修正数量。
- **不保留原始提示词、模型响应全文、自由文本 hint、地址/坐标、站名、认证头、Cookie、密钥、异常正文/堆栈。** hint 仅记录“是否提供”和“已省略”。SDK inputs 固定为空；outputs 仅为白名单 facts。无效模型响应也不上传原文。
- 两条操作作用域内显式关闭 LangSmith/LangChain 自动 tracing，包含自身观测关闭的情况，避免自动子调用绕过白名单。没有全局改变其他链路的 tracing 行为；不要为本功能设置全局 `LANGSMITH_TRACING=true`。
- 同一套脱敏文档先入队，再写本地索引/上传；本地索引不保存原文。`schema_version=trace-v1`、`privacy_version=allowlist-v1`。
- 仅 `model_call` 提交实际可得的 token 用量；其他阶段不复制用量。结构化模式无法取得 usage 时为 `usage_known=false`，不是 0。模型只保存别名，本期没有计价表，**不据 LangSmith 空白或默认金额宣称费用为零**。
- 普通操作标记 `execution_mode=live`、`data_origin=unclassified`；本轮人工材料 smoke 单独标记 `environment=demo`、`execution_mode=live_model_with_synthetic_tools`、`data_origin=synthetic`。

未配置 HASH_KEY 时别名只在当前进程内稳定，重启后改变，文档标记 `identity_scope=process`。准备好的 P1 私有配置含独立随机 HASH_KEY，可跨重启关联，标记 `configured`；更换该键会断开此前的匿名关联，不更改历史记录。

这份最小 Trace 有意省略文本语义，不能直接拿来评估自由文本需求满足程度，也不能当成 P2 的完整 eval 输入。P2 仍需独立构建、审查、冻结案例输入与参考答案。

## 3. 导出及失效边界

- 默认总开关和云导出开关均关闭。总开关关闭时不启动工作线程、不写观测索引、不构造云客户端。
- 开启后业务线程只构造有界内存数据；文件和网络由后台 daemon 执行。队列按未处理 span 总数限制为 1000，单操作最多 128 span。队列满丢弃整个新操作；树超限保留已记录部分并标记 `truncated`，不得当作完整追踪。
- 云客户端复用锁定的 `langsmith==0.8.9`，关闭 SDK 自动批处理及额外重试；每个完成的 span 单次 POST，连接/读取超时 250/750ms。不追踪 exporter 自身，不递归导出。
- 当前只接受内置的 LangSmith HTTPS 官方主机，拒绝跨源及重定向。自托管/自定义域名不在本版范围。
- 网络、认证、磁盘、入队失败不改变业务结果。失败不新增业务重试，不回滚已成功的业务保存，也不延长原 35 秒票务模型期限/110 秒重排总期限。
- 本地记录 `disabled / pending / exported / partial / export_failed` 及已发送 span 数。失败树不自动重发；部分上传可能只在云端存在部分节点，必须结合本地状态看，不能称完整。
- shutdown 最多等 2 秒，未完成数量计 `shutdown_pending`。不承诺强杀/崩溃时交付全部内存队列，也不承诺 exactly-once。
- 索引保存到独立 `OBSERVABILITY_DIR/operations`，原子替换、文件权限 0600；按 30 天/200 MiB 清理旧操作索引。不会清理其他目录里的固定实验文件。本地保留策略不是云端保留保证；云端仍按账号配置。
- `/health` 增加 `observability` 状态：开关、队列、成功/失败、部分上传、丢弃、磁盘失败、shutdown 未完成数。没有密钥、配置路径或业务数据；观测失败仍保持业务 health 正常。

## 4. 已准备的配置与启停

独立文件已创建：`${USER_CONFIG_DIR}/langsmith-p1.env`，权限 0600，复用用户已填的 P0 API key，项目名 `trip-planner-dev`，含新随机 HASH_KEY。**文件默认两开关均为 false，当前服务未由本轮重启或切换。无需再次申请或填写密钥。** `backend/.env` 与 P0 配置未改。

启动时按需加入环境变量；沿用原 Python 环境和原有启动方式，不需要 pip install：

```bash
# 在 backend 目录，接到你原有的启动命令前：
OBSERVABILITY_CONFIG_FILE="$HOME/.config/langgraph-trip-planner/langsmith-p1.env" \
OBSERVABILITY_ENABLED=true \
OBSERVABILITY_EXPORT_ENABLED=true \
python run.py
```

只写脱敏本地索引时，将 `OBSERVABILITY_EXPORT_ENABLED=false`；完全关闭时将 `OBSERVABILITY_ENABLED=false`。配置启动时读取，修改后需重启目标服务；不会通过更改文件热切换已运行的线程。环境变量优先于独立配置文件。

现有 P0 文件也能作为凭据来源，但应显式覆盖 `LANGSMITH_PROJECT`，避免把开发流量写入 P0 兼容验证项目。本轮云验证写到独立项目 `trip-planner-p1-isolated-20261024`，没有创建公开分享链接。

## 5. 验证结果及证据

证据根目录：`${EVIDENCE_ROOT}/trace-p1-20261024/`。所有 pytest/API 保存均显式指定该目录下的隔离 SQLite；使用 P0 的 75 包锁定 venv。没有启动业务库应用生命周期或修改原库。

| 验证 | 结果及证据 |
| --- | --- |
| 后端最终全量普通回归 | **653 passed / 4 skipped**，`evidence/backend-final.log`、`backend-final.xml`；4 项为外部 smoke 默认跳过 |
| 新增观测专项 | 共 **30 项**：24 项服务测试＋6 项 API 测试；包含在最终全量结果中，不额外加总 |
| 前端 | **239 tests / 38 files 通过**，`evidence/frontend-tests.log`；vue-tsc＋Vite 构建通过，`frontend-build.log`，仅既有大 chunk 警告；产物在隔离目录，未替换当前 dist/扩展包 |
| 无扰动 | 真实 ASGI API＋临时 SQLite 下，观测关/开/云故障三组重排响应及保存 JSON 精确一致；票务开关对照与只读不写检查通过 |
| 故障关联 | 非法模型 JSON、取消、超时、规则回退、旧安排恢复、快照迟到 409、并发树隔离、队列满、磁盘失败、不可达、部分上传、重定向拒绝、关闭上限通过；故障为明确注入 |
| 脱敏 | SDK 实际序列化 payload 检查＋隔离云端回读通过；测试密钥/手机号/邮箱/hint/原始 ID/POI 名探针未出现；异常正文由固定分类替代 |
| 云端最终复验 | 两个实际模型请求，票务 **10 span / 303 tokens**、重排 **16 span / 1157 tokens**；根/子闭合、归属、空 inputs、真实 token 字段逐项核对，**19 项通过**，`evidence/cloud-smoke-v2.json` 及 `cloud-readback-*.json` |

云端验证使用人工票务候选/人工日程、地图替身，模型是真实配置的模型；不是新 12306/高德查询，也不是建议质量验收。没有运行 T18/R10、保留集或 30 例正式 eval。

首轮云验证发现“普通顶层 usage_metadata 被接受但云端 token 仍为 0”；按现锁 SDK 的 RunTree 契约改为 `extra.metadata.usage_metadata`，加序列化断言后重新执行两条链路，并核对云端 prompt/completion/total token。首轮原始证据保留在 `cloud-smoke.json`，不作为最终用量验收；两轮共 4 次真实模型调用。用量字段依据也见 [LangSmith 官方说明](https://docs.langchain.com/langsmith/cost-tracking)。

最终可直接打开（需要用户自己的 LangSmith 权限）：

- [票务推荐 Trace](https://smith.langchain.com/o/cd4706cf-1ded-47da-ac8c-f69796e819a1/projects/p/672a5a89-7053-46a2-9346-f3cb9179a0df/r/006d2d33-513b-42f9-8007-62a6da9bab48?poll=true)
- [每日重排 Trace](https://smith.langchain.com/o/cd4706cf-1ded-47da-ac8c-f69796e819a1/projects/p/672a5a89-7053-46a2-9346-f3cb9179a0df/r/857e1487-71c7-4acb-aed5-4dc8cb45e4b1?poll=true)

### 开销

每条链路预热 10 组，随后交错运行开/关各 100 次，交替顺序；人工模型/地图、真实隔离 SQLite、无外网。入队之后的 drain 在计时外，避免把 exporter 完成时间误计成业务请求等待；队列丢弃为 0。原始 200 组数据和方法见 `evidence/benchmark.json`。

| 链路 | 关闭 p95 | 开启 p95 | p95 差值 | 配对额外耗时 p95 |
| --- | ---: | ---: | ---: | ---: |
| 票务推荐 | 0.352 ms | 0.913 ms | 0.560 ms | 0.592 ms |
| 每日 AI 重排 | 3.340 ms | 3.687 ms | 0.348 ms | 0.658 ms |

两种计算均低于预设 20ms。这个结果不代表真实模型/地图网络延迟或持续高吞吐保证；后台积压和慢导出另由注入测试验证。

## 6. 保留核对与范围验收

`evidence/preservation-after.json`：业务 `trips.db`、`backend/.env`、配置源码、后端锁、前端锁、原 venv 配置 SHA-256 均与本轮开始一致；原环境 135 包逐项等于 P0 清单，锁定 75 项在原环境和隔离环境均匹配。未安装/升级依赖、未做 ORM 迁移、未切换运行环境。本轮修改的运行源码以 `evidence/implementation-vs-start.patch` 单独记录，避免把用户已有改动归为本轮成果。

Git 有一项独立观察：开始时的 62,104 字节暂存补丁，在工作期间被其他操作提交为 `3b3a93c`（19:43:34）；提交 diff 与起始暂存补丁逐字节相同。因而“index 不变”检查如实为 false，而“起始暂存内容完整保留”通过。本轮没有执行 add/reset/commit，也没有撤回该提交；P1 源码与测试仍未提交。不可笼统写“仓库 HEAD/index 完全没变”。

按本次缩小范围：A01/A02 的两条非 SSE 主链路部分、A03/A04、A05 的 Trace 部分、A10 的隔离部分和 A13 已取得证据。A01/A02 的发现/草稿/SSE、A05 的 dataset/feedback、P2 的人工标注与评分、实验比较及工作台尚未完成。工具调用树完整可见不代表用户偏好最优、路线更好或真人验收通过。

下一步如继续授权 P2：先冻结 30 例数据契约/人工参考与评分器正反例，沿用本轮 Trace 的 operation/session 关联；不把当前匿名 Trace 自动转成完整 eval 输入，不改写 P0 留样来源。
