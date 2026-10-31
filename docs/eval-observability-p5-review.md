# P5 分层复核清单

日期：2026-10-25，方案修订v2。**产品行为、客观约束、个人偏好分别复核。** 原30份参考仍为pending_human、确认0份；本轮只改方案，不改数据、评分器、代码、运行输出或成绩。

先阅读 [已确认的3项产品规则](eval-observability-p5-product-decisions.md)，完整方法见 [分层评估方案](eval-observability-p5-evaluation-design.md)。配套：[验收矩阵](eval-observability-p5-acceptance.md)、[演示流程](eval-observability-p5-demo.md)、[待填复核记录](eval-observability-p5-review-record.json)。三项产品选择已由用户在本会话确认并单独记录；案例复核、人审标签、分数和整体验收仍待完成。

## 按职责复核，不要求本人挑选30个标准答案

| 复核轨道 | 负责内容 | 本人的参与边界 |
| --- | --- | --- |
| 产品规则 | PR01调整日程的权限；PR02偏好缺失/冲突时的响应；PR03模糊偏好的表达 | PR01=B、PR02=A、PR03=A为主并按需追问已确认；工程落实可检验契约，不批量确认案例 |
| 客观约束/明确指令 | 工程独立核算时间轴、候选、事实和保存状态，核对明确意图；取证不足留空 | 可以审阅依据和做独立复核，但不需亲自替工程计算；工程证据不冒充真人验收 |
| 条件化偏好 | 先声明本次目标/约束，再审查可接受集合、优先关系与并列；个人体验另记 | 判断“按给定需求是否合理”，不是“我会选哪一个”。可引入不同旅行习惯的人，保留分歧；单人参与只标单人复核 |

原D01～D08不再作为8项必须由本人选择的清单。迁移对应：D01→PR01＋客观窗口；D02→PR03＋时段场景；D03→工程取证契约；D04→T18条件化偏好；D05→R02明确指令；D06→R10客观可行性＋优化目标；D07→工程分组；D08→可选judge。具体事实与处理见分层方案末尾的案例表。

## 复核顺序与记录规则

1. 三项PR规则已确认，工程按所定边界准备客观证据与条件化偏好规格。产品决定不代替逐案核对，也不要求本人逐案投票。
2. 工程先给出输入、来源、独立推导与未知项，再复核参考；偏好案例先写明确意图和允许多个答案的依据，最后看模型输出。当前输出已看过，不能称盲测。
3. 客观事实、明确指令遵循、条件化偏好和真人采纳分别留证。参考的`confirm_current / request_revision / insufficient_evidence`用于绑定版本的审阅结论，不表示对所有人都最优。单个产品决定或喜欢某个车次都不能批量确认案例。
4. 旧JSON中的`human_review`保留为未签署的历史参考复核栏；新增`review_tracks`只组织待办，不自动写入annotation或打分。产品选择单列`product_decisions`；个人采纳/满意度不混入gold。
5. 签署前核对输入、路线和参考版本。`canonical_sha256`用于既有confirmed_reference_sha256契约，`file_sha256`用于文件字节核验，不可混用。版本变化需重新审阅。
6. 新增偏好变体须另建数据/参考/规则版本，先冻结意图、可接受集合及偏序再运行。旧输出不按新增偏好倒判，原实验不覆盖；仅重评分也须单列为旧输出重评。

## 客观核验与偏好规格的当前进度

已补 [重点客观核验材料](eval-observability-p5-objective-evidence.md)：T10/T11/T17给出有条件调整见证与固定性缺口，T12/T18核对提前日期拒绝、T18独立复算35/45，R02/R10枚举冻结路线下的完整排列。计算状态为工程核对、待独立复核，不替代人审或新gold；旧FAIL/ERROR仍保留。

已准备 [12份偏好规格](eval-observability-p5-preference-specs.md)，覆盖价格、时间、席别、多答案、未说明偏好和硬条件无匹配等情况。不是新增已执行案例，不对原输出按新意图倒判。复核表仅补工程证据与规格入口，人审/整体验收栏仍待完成。

## 30 例逐项检查

下表是分层待办，不是给本人的逐案选票；每个勾选框均未勾选。“无 F/E”只表示这次诊断没有 FAIL/ERROR，可能仍有未评项，不代表参考已正确或业务合格。真实模型案例须看全部 3 次，运行链接默认第 1 次；完整三次 Observation、哈希和待填字段在 [复核记录](eval-observability-p5-review-record.json)。T03 尤其要看第 2、3 次。来源“代理构造”不等于真人手工标注。

| 案例 / 待完成 | 分组 / 来源 / 本次执行 | 复核轨道与检查重点 | 当前 F/E 诊断规则（跨重复去重） | 材料 |
| --- | --- | --- | --- | --- |
| [ ] T01 低价优先 | dev / 代理构造 / 真实模型 ×3 | 客观＋偏好：按本次明确价格目标比较，同价可并列；未知总价/附加费不补齐。 | 无 F/E（仍待人审） | [输入](../backend/evals/datasets/inputs/T01.json) · [参考](../backend/evals/datasets/references/T01.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-T01-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] T02 车程优先 | dev / 代理构造 / 真实模型 ×3 | 客观＋偏好：按本次车程目标核算，允许并列；不混用门到门时间。 | 无 F/E（仍待人审） | [输入](../backend/evals/datasets/inputs/T02.json) · [参考](../backend/evals/datasets/references/T02.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-T02-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] T03 日间优先 | dev / 代理构造 / 真实模型 ×3 | 偏好＋PR03：明确本次时段后定义首选/备选；旧B参考不扩展为通用日间标准。 | T-RANK:FAIL | [输入](../backend/evals/datasets/inputs/T03.json) · [参考](../backend/evals/datasets/references/T03.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-T03-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] T04 均衡并列首选 | holdout / 代理构造 / 真实模型 ×3 | 偏好：明确目标关系，再核定多答案/偏序；不把均衡等同固定加权总分。 | 无 F/E（仍待人审） | [输入](../backend/evals/datasets/inputs/T04.json) · [参考](../backend/evals/datasets/references/T04.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-T04-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] T05 未知价不当免费 | dev / 代理构造 / 真实模型 ×3 | 客观＋偏好：未知价不为0；只按可比事实评价本次价格目标。 | 无 F/E（仍待人审） | [输入](../backend/evals/datasets/inputs/T05.json) · [参考](../backend/evals/datasets/references/T05.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-T05-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] T06 无票与未知余票 | dev / 代理构造 / 真实模型 ×3 | 客观＋偏好：独立核对无票/未知与可行集合；首选依本次明确目标。 | 无 F/E（仍待人审） | [输入](../backend/evals/datasets/inputs/T06.json) · [参考](../backend/evals/datasets/references/T06.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-T06-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] T07 全部无票 | dev / 代理构造 / 无模型 ×1 | 全部无票应空结果且不调用模型，不能将无推荐算模型失败。 | 无 F/E（仍待人审） | [输入](../backend/evals/datasets/inputs/T07.json) · [参考](../backend/evals/datasets/references/T07.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-T07-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] T08 无上下文兼容 | holdout / 代理构造 / 真实模型 ×3 | 无日程上下文只作票务排序，不声称已验证可容纳。 | 无 F/E（仍待人审） | [输入](../backend/evals/datasets/inputs/T08.json) · [参考](../backend/evals/datasets/references/T08.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-T08-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] T09 离城余量边界 | dev / 代理构造 / 真实模型 ×3 | 逐项核算离城缓冲与 18:00 等号边界，余量不重复扣减。 | 无 F/E（仍待人审） | [输入](../backend/evals/datasets/inputs/T09.json) · [参考](../backend/evals/datasets/references/T09.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-T09-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] T10 抵达缓冲边界 | holdout / 代理构造 / 真实模型 ×3 | 产品＋客观：PR01后工程复算B是否可行，不按个人车次偏好决定。 | T-ELIG:FAIL；T-MARGIN:FAIL | [输入](../backend/evals/datasets/inputs/T10.json) · [参考](../backend/evals/datasets/references/T10.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-T10-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] T11 双城窗口 | dev / 代理构造 / 真实模型 ×3 | 产品＋客观：依PR01复核两侧窗口；排序另按明确意图判定。 | T-ELIG:FAIL；T-MARGIN:FAIL；T-RANK:FAIL | [输入](../backend/evals/datasets/inputs/T11.json) · [参考](../backend/evals/datasets/references/T11.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-T11-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] T12 跨出旅行日期 | holdout / 代理构造 / 真实模型 ×3 | 客观：工程按拒绝阶段核定余量适用性，null不填0；旧ERROR保留。 | T-MARGIN:ERROR | [输入](../backend/evals/datasets/inputs/T12.json) · [参考](../backend/evals/datasets/references/T12.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-T12-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] T13 非法候选回退 | dev / 代理构造 / 注入 ×1 | 预设非法 ID 应被检出且规则回退；模型 FAIL 不计真实模型错误率。 | T-VALID:FAIL | [输入](../backend/evals/datasets/inputs/T13.json) · [参考](../backend/evals/datasets/references/T13.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-T13-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] T14 全部日程冲突 | dev / 代理构造 / 无模型 ×1 | 全部日程冲突应空结果、不调模型、不写日程。 | 无 F/E（仍待人审） | [输入](../backend/evals/datasets/inputs/T14.json) · [参考](../backend/evals/datasets/references/T14.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-T14-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] T15 模型超时回退 | dev / 代理构造 / 注入 ×1 | 预设模型超时后有界回退，原安排不受影响；不是实际供应商事故。 | 无 F/E（仍待人审） | [输入](../backend/evals/datasets/inputs/T15.json) · [参考](../backend/evals/datasets/references/T15.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-T15-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] T16 取消传播 | dev / 代理构造 / 注入 ×1 | 取消应向下传播，取消后无新外部调用及业务写入。 | 无 F/E（仍待人审） | [输入](../backend/evals/datasets/inputs/T16.json) · [参考](../backend/evals/datasets/references/T16.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-T16-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] T17 双检查点过期拒绝 | holdout / 代理构造 / 注入 ×1 | 客观＋PR01：独立核对两处409/最新快照；窗口争议不抵销并发保护。 | T-ELIG:FAIL | [输入](../backend/evals/datasets/inputs/T17.json) · [参考](../backend/evals/datasets/references/T17.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-T17-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] T18 旧日程与补采铁路候选 | holdout / 历史日程＋补采票务 / 真实模型 ×3 | 客观核验35/45与来源；偏好未来分场景定义多答案，原排名继续未评。 | T-MARGIN:ERROR | [输入](../backend/evals/datasets/inputs/T18.json) · [参考](../backend/evals/datasets/references/T18.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-T18-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] R01 明确交换顺序 | dev / 代理构造 / 真实模型 ×3 | 核定交换 A/B 意图与最终 B→A→C；硬约束、餐次及事实同时成立。 | 无 F/E（仍待人审） | [输入](../backend/evals/datasets/inputs/R01.json) · [参考](../backend/evals/datasets/references/R01.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-R01-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] R02 锁定第二景点 | dev / 代理构造 / 真实模型 ×3 | 明确指令＋客观：核对B锁第二且C提前的所有可行排列，不按个人喜好选景点。 | R-INTENT:FAIL | [输入](../backend/evals/datasets/inputs/R02.json) · [参考](../backend/evals/datasets/references/R02.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-R02-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] R03 删除与手动午餐 | holdout / 代理构造 / 真实模型 ×3 | 删除项不恢复、手动午餐及位置保护，核定移动后的时间轴。 | 无 F/E（仍待人审） | [输入](../backend/evals/datasets/inputs/R03.json) · [参考](../backend/evals/datasets/references/R03.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-R03-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] R04 保留两顿正餐 | dev / 代理构造 / 真实模型 ×3 | 原两顿正餐均保留，时段与插入位置有效，不靠数量掩盖漏餐。 | 无 F/E（仍待人审） | [输入](../backend/evals/datasets/inputs/R04.json) · [参考](../backend/evals/datasets/references/R04.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-R04-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] R05 不恢复已删晚餐 | dev / 代理构造 / 真实模型 ×3 | 已删晚餐不补回，不能将无晚餐自动计为模型漏餐。 | 无 F/E（仍待人审） | [输入](../backend/evals/datasets/inputs/R05.json) · [参考](../backend/evals/datasets/references/R05.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-R05-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] R06 餐厅事实来源 | dev / 代理构造 / 真实模型 ×3 | 餐厅名称、坐标、价格沿候选事实，禁止由模型编造或替换。 | 无 F/E（仍待人审） | [输入](../backend/evals/datasets/inputs/R06.json) · [参考](../backend/evals/datasets/references/R06.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-R06-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] R07 关闭餐厅修正 | holdout / 代理构造 / 注入 ×1 | 关闭餐厅注入后有限恢复并保留旧安排，不能标为优化成功。 | 无 F/E（仍待人审） | [输入](../backend/evals/datasets/inputs/R07.json) · [参考](../backend/evals/datasets/references/R07.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-R07-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] R08 无法保留正餐拒绝 | dev / 代理构造 / 注入 ×1 | 正餐无法保留时拒绝且无部分写入，确认拒绝为预期结果。 | 无 F/E（仍待人审） | [输入](../backend/evals/datasets/inputs/R08.json) · [参考](../backend/evals/datasets/references/R08.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-R08-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] R09 固定休息与抵离窗口 | dev / 代理构造 / 真实模型 ×3 | 固定休息、19:00 离开窗口、游览时长与餐次同时满足。 | 无 F/E（仍待人审） | [输入](../backend/evals/datasets/inputs/R09.json) · [参考](../backend/evals/datasets/references/R09.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-R09-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] R10 旧日程与补采路线改善 | holdout / 历史单日＋补采路线 / 真实模型 ×3 | 客观＋目标：核验180/162/138及营业餐次，只按明确优化目标评价，不把短路线等同舒适。 | R-INTENT:FAIL；R-ROUTE:FAIL | [输入](../backend/evals/datasets/inputs/R10.json) · [参考](../backend/evals/datasets/references/R10.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-R10-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] R11 路线共享期限 | dev / 代理构造 / 注入 ×1 | 注入路线超时服从共享期限，失败保留已存状态。 | 无 F/E（仍待人审） | [输入](../backend/evals/datasets/inputs/R11.json) · [参考](../backend/evals/datasets/references/R11.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-R11-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |
| [ ] R12 并发删除晚餐 | holdout / 代理构造 / 注入 ×1 | 并发删除晚餐后拒绝迟到结果，保存的是最新状态而非旧 before。 | 无 F/E（仍待人审） | [输入](../backend/evals/datasets/inputs/R12.json) · [参考](../backend/evals/datasets/references/R12.json) · [运行](http://127.0.0.1:15175/quality/runs/current_live-R12-1?experiment_id=eval_38609cdd0f754738b89760d783aa31e8) |

每例完成时需同时核对来源/约束、参考/适用性、原始模型/系统结果及失败保存语义。产品决定、客观复核、偏好审阅与代码修复分别记录；出现争议时保留原参考并列出拟改内容，不为凑满 30 份签署。

## 可选 judge：只备材料，不执行

沿用 [judge 契约](../backend/evals/judge.py) 的两个量表，评分对象是最终系统说明 `system_explanation`，不是模型原始 JSON 或真人满意度。J-INTENT：0 未回应/相反，1 部分回应，2 明确回应且符合事实；J-TRADEOFF：0 编造优势/忽略冲突，1 基本正确但遗漏代价，2 有证据支持收益、代价和不确定性。证据不足应 abstain；没有可评说明时不能拿“操作成功”替它得分。

旧诊断面板如下，均取已发布的最终输出，不新调模型。**这12份不再视为可直接执行的校准集**：其中包含现有holdout案例，只能诊断审阅，不能用于judge调优。正式校准需从开发材料另选并冻结12份，同时覆盖已明确意图、多答案和证据不足。T03 的两次输出用于检验边界一致性，所以是 **12 份输出、11 个案例**，不是 12 个独立场景。选择是有目的的诊断抽样，不是随机质量估计；人审可以先调整并冻结面板，不能看完 judge 成绩后换样本凑阈值。

| 样本 | 运行 | 入选理由（非预置分数） |
| --- | --- | --- |
| J01 | current_live-T01-1 | 已知价格下的偏好解释 |
| J02 | current_live-T03-1 | 日间偏好第一次输出 |
| J03 | current_live-T03-2 | 同一输入的另一种首选 |
| J04 | current_live-T04-1 | 均衡、并列与取舍 |
| J05 | current_live-T05-1 | 未知价格披露 |
| J06 | current_live-T10-1 | 抵达窗口口径分歧 |
| J07 | current_live-T11-1 | 双城窗口与解释 |
| J08 | current_live-T18-1 | 混合真实来源与首选未定 |
| J09 | current_live-R01-1 | 明确交换后的说明 |
| J10 | current_live-R02-1 | 技术完成与意图不符 |
| J11 | current_live-R09-1 | 固定休息/抵离限制 |
| J12 | current_live-R10-1 | 未实现路线改善 |

后续拟冻结的计算方法（工程准备，不要求本轮产品拍板）：每量表单独计数，12 为固定分母；两轮分别与经独立复核的同一份条件化人审标签比较，均至少 10/12，且两轮之间至少 10/12 才称该量表“初步校准”。比较必须精确同分；缺失、无效或 abstain 单列且不作为数值一致通过，不能缩小分母。未达到即保留未校准，修改 prompt 后必须新版本/新校准记录，不能只保留更好一轮。当前实现的校准对象只存摘要；真正接入前还要核查每量表证据与摘要绑定，不能仅填一个合格数字绕过逐条结果。

偏好审阅应核对给定意图，而非标注者自己的选择。不同旅行习惯者的分歧需留存；仅一人时标“单人复核，偏好覆盖未验证”。正式校准材料确定后，人工先填 score（0/1/2 或 null）、reason、证据路径和 abstain_reason；系统评分引用路径须能解析到 `final_output.*`。面板按发布 JSON 的最终输出规范化哈希冻结。之后再给 judge 同一输入/输出，隐藏人审分数、gold、基线/当前标签、诊断侧注和预期赢家，报告中仍保留内部关联。已有“current_live”运行名不能原样放入 judge 提示。

若以后沿用每次请求一个量表的现有 payload，两量表 × 12 份 × 两轮 = **48 次 judge 请求（未计重试）**；这是未来仍采用12份/两量表/两轮时的算术示例，不是批准调用计划；旧诊断面板不能直接用于执行。这是可选后续范围，**本轮请求数为 0**。调用前须先选模型、冻结脱敏 payload、估 token、输出上限和重试预留，并披露具体费用；当前没有为未来费用作估价或启动调用。judge 即使校准，也不能代替 30 份参考确认、来源家族审查或 USER 验收。
