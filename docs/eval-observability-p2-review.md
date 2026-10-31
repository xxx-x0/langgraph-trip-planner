# P2 人工参考复核清单

日期：2026-10-24；2026-10-25补充P3/P5状态链接。**30/30 为待人工确认，0 份已确认。** 本文是待办，不能作为真人验收记录。构造样本由代理编写；独立算术/区间核对不等于独立人工标注。

2026-10-25后续：当前复核职责按 [P5分层方案](eval-observability-p5-evaluation-design.md) 执行，产品选择仅见 [PR01～PR03](eval-observability-p5-product-decisions.md)。以下来源和草稿参考保留；不再要求本人逐案选择统一gold。

## 复核方式

逐案打开输入及参考，核对场景是否成立、必要事实是否完整、适用规则和预期成功/拒绝是否准确。记录复核者、日期、分歧及理由；不认同的参考标记 disputed。确认时在案例 annotation 中填写 reviewer、reviewed_at、confirmed_reference_sha256，清空已处理 pending_items，再改 status=confirmed。摘要须对应当前 reference_sha256。不能只批量改状态绕过核对。

修改输入、参考、分组或评分适用性后应增加版本、重算资产与 manifest 哈希，运行 validate 和专项测试。先完成下述来源家族审查，再将 manifest.split_review 标记 confirmed；人审参考通过不能自动代替分组验收。实际核定以案例 JSON 为准，本文表格仅导航。

## 30 例逐项队列

全部状态：pending_human / agent_draft。M=计划真实模型＋固定回放，F=计划故障注入，Z=计划不调用模型；这是P2准备时的执行模式；P3已完成对应真实批次（M每例3次，F/Z每例1次），见 [真实交接](eval-observability-p3-live-handoff.md)。最新逐案复核、口径分歧与待填记录见 [P5人工清单](eval-observability-p5-review.md)；人工状态未变。

| 案例 | 场景 | 分组 | 模式 | 素材来源 | 输入 / 待审参考 |
| --- | --- | --- | --- | --- | --- |
| T01 | 低价优先 | dev | M | 代理构造 | [输入](../backend/evals/datasets/inputs/T01.json) / [参考](../backend/evals/datasets/references/T01.json) |
| T02 | 车程优先 | dev | M | 代理构造 | [输入](../backend/evals/datasets/inputs/T02.json) / [参考](../backend/evals/datasets/references/T02.json) |
| T03 | 日间优先 | dev | M | 代理构造 | [输入](../backend/evals/datasets/inputs/T03.json) / [参考](../backend/evals/datasets/references/T03.json) |
| T04 | 均衡并列首选 | holdout | M | 代理构造 | [输入](../backend/evals/datasets/inputs/T04.json) / [参考](../backend/evals/datasets/references/T04.json) |
| T05 | 未知价不当免费 | dev | M | 代理构造 | [输入](../backend/evals/datasets/inputs/T05.json) / [参考](../backend/evals/datasets/references/T05.json) |
| T06 | 无票与未知余票 | dev | M | 代理构造 | [输入](../backend/evals/datasets/inputs/T06.json) / [参考](../backend/evals/datasets/references/T06.json) |
| T07 | 全部无票 | dev | Z | 代理构造 | [输入](../backend/evals/datasets/inputs/T07.json) / [参考](../backend/evals/datasets/references/T07.json) |
| T08 | 无上下文兼容 | holdout | M | 代理构造 | [输入](../backend/evals/datasets/inputs/T08.json) / [参考](../backend/evals/datasets/references/T08.json) |
| T09 | 离城余量边界 | dev | M | 代理构造 | [输入](../backend/evals/datasets/inputs/T09.json) / [参考](../backend/evals/datasets/references/T09.json) |
| T10 | 抵达缓冲边界 | holdout | M | 代理构造 | [输入](../backend/evals/datasets/inputs/T10.json) / [参考](../backend/evals/datasets/references/T10.json) |
| T11 | 双城窗口 | dev | M | 代理构造 | [输入](../backend/evals/datasets/inputs/T11.json) / [参考](../backend/evals/datasets/references/T11.json) |
| T12 | 跨出旅行日期 | holdout | M | 代理构造 | [输入](../backend/evals/datasets/inputs/T12.json) / [参考](../backend/evals/datasets/references/T12.json) |
| T13 | 非法候选回退 | dev | F | 代理构造 | [输入](../backend/evals/datasets/inputs/T13.json) / [参考](../backend/evals/datasets/references/T13.json) |
| T14 | 全部日程冲突 | dev | Z | 代理构造 | [输入](../backend/evals/datasets/inputs/T14.json) / [参考](../backend/evals/datasets/references/T14.json) |
| T15 | 模型超时回退 | dev | F | 代理构造 | [输入](../backend/evals/datasets/inputs/T15.json) / [参考](../backend/evals/datasets/references/T15.json) |
| T16 | 取消传播 | dev | F | 代理构造 | [输入](../backend/evals/datasets/inputs/T16.json) / [参考](../backend/evals/datasets/references/T16.json) |
| T17 | 双检查点过期拒绝 | holdout | F | 代理构造 | [输入](../backend/evals/datasets/inputs/T17.json) / [参考](../backend/evals/datasets/references/T17.json) |
| T18 | 旧日程与补采铁路候选 | holdout | M | 旧日程＋补采铁路 | [输入](../backend/evals/datasets/inputs/T18.json) / [参考](../backend/evals/datasets/references/T18.json) |
| R01 | 明确交换顺序 | dev | M | 代理构造 | [输入](../backend/evals/datasets/inputs/R01.json) / [参考](../backend/evals/datasets/references/R01.json) |
| R02 | 锁定第二景点 | dev | M | 代理构造 | [输入](../backend/evals/datasets/inputs/R02.json) / [参考](../backend/evals/datasets/references/R02.json) |
| R03 | 删除与手动午餐 | holdout | M | 代理构造 | [输入](../backend/evals/datasets/inputs/R03.json) / [参考](../backend/evals/datasets/references/R03.json) |
| R04 | 保留两顿正餐 | dev | M | 代理构造 | [输入](../backend/evals/datasets/inputs/R04.json) / [参考](../backend/evals/datasets/references/R04.json) |
| R05 | 不恢复已删晚餐 | dev | M | 代理构造 | [输入](../backend/evals/datasets/inputs/R05.json) / [参考](../backend/evals/datasets/references/R05.json) |
| R06 | 餐厅事实来源 | dev | M | 代理构造 | [输入](../backend/evals/datasets/inputs/R06.json) / [参考](../backend/evals/datasets/references/R06.json) |
| R07 | 关闭餐厅修正 | holdout | F | 代理构造 | [输入](../backend/evals/datasets/inputs/R07.json) / [参考](../backend/evals/datasets/references/R07.json) |
| R08 | 无法保留正餐拒绝 | dev | F | 代理构造 | [输入](../backend/evals/datasets/inputs/R08.json) / [参考](../backend/evals/datasets/references/R08.json) |
| R09 | 固定休息与抵离窗口 | dev | M | 代理构造 | [输入](../backend/evals/datasets/inputs/R09.json) / [参考](../backend/evals/datasets/references/R09.json) |
| R10 | 旧日程与补采路线改善 | holdout | M | 旧单日＋补采路线 | [输入](../backend/evals/datasets/inputs/R10.json) / [参考](../backend/evals/datasets/references/R10.json) |
| R11 | 路线共享期限 | dev | F | 代理构造 | [输入](../backend/evals/datasets/inputs/R11.json) / [参考](../backend/evals/datasets/references/R11.json) |
| R12 | 并发删除晚餐 | holdout | F | 代理构造 | [输入](../backend/evals/datasets/inputs/R12.json) / [参考](../backend/evals/datasets/references/R12.json) |

## 先复核的三项

### 来源家族与保留集

当前按方案保留 dev20 / holdout10，但 17 个票务构造案例共享 synthetic-ticket-template-v1，11 个每日构造案例共享 synthetic-day-template-v1，均跨组。验证器显式报告 cross_split_source_families，formal_ready=false。现阶段只能称场景保留集，不能称未见数据上的独立验证。

正式比较前需人工审查近重复关系，按来源家族重新分组或重新设计独立保留集；如坚持 20/10，需补充独立来源/结构后重新版本化。当前针对所有案例做评分器单元测试也已经接触保留案例，不能以后隐去这点。不能仅改 family 名称消除警告。

### T18：历史日程 + 补采候选

历史苏杭行程快照归档于 2026-10-20；12306 候选由 P0 在 2026-10-24 11:28:27.916 UTC 采集，查询 2026-11-01 杭州→南京。页面 156 行中 128 行可识别且有票，均匀抽取 80 行，非全站最优集合；原历史候选批次没有找回。P2 未重新查票，当前余票及价格不保证仍有效。

独立算术草稿：最后保护活动 13:15 + 已存离开缓冲 150 分钟 = 最早 15:45；80 条中 35 可容纳、45 排除。人工须核对日期/地点、活动、缓冲计入方式和可行集合，客观集合由工程独立核验；后续按明确本次偏好分别核定可接受首选/偏序，不要求本人按自己的旅行习惯选出通用答案。现在 acceptable_first=null，T-RANK 仍 NOT_EVALUATED，不能拿旧模型选中项当 gold。列表单人参考价不能变为同行含税总价。

以下为 35 个可行候选的待审摘录；分钟余量来自参考算术草稿，价格仍为采集时列表参考价。

| 班次 / 候选 ID | 出发→到达 | 单人参考价 | 窗口余量（分钟） |
| --- | --- | --- | --- |
| G3106 / rail_69_G3106 | 2026-11-01T15:48 → 2026-11-01T17:17 | 198.0 | [3] |
| G7690 / rail_70_G7690 | 2026-11-01T15:53 → 2026-11-01T17:22 | 141.0 | [8] |
| G3342 / rail_72_G3342 | 2026-11-01T16:16 → 2026-11-01T17:57 | 132.0 | [31] |
| G1482 / rail_73_G1482 | 2026-11-01T16:18 → 2026-11-01T17:33 | 127.0 | [33] |
| G7696 / rail_75_G7696 | 2026-11-01T16:34 → 2026-11-01T18:13 | 137.0 | [49] |
| G7696 / rail_76_G7696 | 2026-11-01T16:48 → 2026-11-01T18:13 | 127.0 | [63] |
| G48 / rail_78_G48 | 2026-11-01T16:54 → 2026-11-01T18:03 | 141.0 | [69] |
| D3296 / rail_81_D3296 | 2026-11-01T16:59 → 2026-11-01T18:18 | 114.0 | [74] |
| G7652 / rail_82_G7652 | 2026-11-01T17:04 → 2026-11-01T18:26 | 127.0 | [79] |
| D18 / rail_83_D18 | 2026-11-01T17:10 → 2026-11-01T21:32 | 164.0 | [85] |
| G1666 / rail_85_G1666 | 2026-11-01T17:23 → 2026-11-01T18:46 | 127.0 | [98] |
| G230 / rail_86_G230 | 2026-11-01T17:34 → 2026-11-01T18:34 | 141.0 | [109] |
| Z282 / rail_88_Z282 | 2026-11-01T17:40 → 2026-11-01T22:44 | 186.0 | [115] |
| G7310 / rail_90_G7310 | 2026-11-01T17:47 → 2026-11-01T21:09 | 373.0 | [122] |
| G1098 / rail_91_G1098 | 2026-11-01T17:52 → 2026-11-01T19:34 | 150.0 | [127] |
| G46 / rail_95_G46 | 2026-11-01T18:00 → 2026-11-01T19:01 | 141.0 | [135] |
| G1510 / rail_96_G1510 | 2026-11-01T18:01 → 2026-11-01T20:51 | 223.0 | [136] |
| G1098 / rail_92_G1098 | 2026-11-01T18:05 → 2026-11-01T19:34 | 141.0 | [140] |
| G7626 / rail_98_G7626 | 2026-11-01T18:15 → 2026-11-01T19:48 | 120.0 | [150] |
| G1380 / rail_99_G1380 | 2026-11-01T18:27 → 2026-11-01T19:53 | 120.0 | [162] |
| G3380 / rail_101_G3380 | 2026-11-01T18:38 → 2026-11-01T22:15 | 265.0 | [173] |
| G1662 / rail_102_G1662 | 2026-11-01T18:53 → 2026-11-01T20:37 | 120.0 | [188] |
| G7588 / rail_104_G7588 | 2026-11-01T19:05 → 2026-11-01T22:04 | 228.0 | [200] |
| G7566 / rail_106_G7566 | 2026-11-01T19:09 → 2026-11-01T21:42 | 223.0 | [204] |
| G7642 / rail_107_G7642 | 2026-11-01T19:20 → 2026-11-01T20:44 | 120.0 | [215] |
| G7582 / rail_110_G7582 | 2026-11-01T19:46 → 2026-11-01T21:12 | 111.0 | [241] |
| G7666 / rail_112_G7666 | 2026-11-01T19:57 → 2026-11-01T21:20 | 127.0 | [252] |
| D2282 / rail_114_D2282 | 2026-11-01T20:02 → 2026-11-01T23:19 | 279.0 | [257] |
| G3024 / rail_115_G3024 | 2026-11-01T20:05 → 2026-11-01T21:35 | 122.0 | [260] |
| G3060 / rail_117_G3060 | 2026-11-01T20:10 → 2026-11-01T22:20 | 228.0 | [265] |
| G3072 / rail_120_G3072 | 2026-11-01T20:29 → 2026-11-01T21:46 | 122.0 | [284] |
| G1656 / rail_122_G1656 | 2026-11-01T20:53 → 2026-11-01T22:36 | 117.0 | [308] |
| D3240 / rail_124_D3240 | 2026-11-01T21:01 → 2026-11-01T22:44 | 106.0 | [316] |
| G206 / rail_126_G206 | 2026-11-01T21:16 → 2026-11-01T23:12 | 223.0 | [331] |
| G236 / rail_127_G236 | 2026-11-01T22:25 → 2026-11-01T23:32 | 92.0 | [400] |

### R10：历史单日 + 补采路线

旧苏州日程为 2026-10-15：虎丘 150 分钟、留园 90 分钟且锁在第二位、七里山塘 90 分钟，两家原正餐及同一酒店。营业/最晚入场信息沿旧记录，尚未重新核实。P0 在 2026-10-24 11:30～11:31 UTC 完成 23 条有向路线（15 条补缺、8 条刷新；24 次请求含一次限流后重试）。高德工具没有出发日期参数，不能把它称作 10-15 历史实时路况。

同批路线矩阵覆盖 20 个保持锁位的活动/餐次排列。基线为 180 分钟；旧档案的 168 分钟仅归档，绝不能用于计算本批改善。

| 可行排列 | 路程分钟 | 相对同批基线减少 | 顺序（含首尾酒店） |
| --- | --- | --- | --- |
| R10-p03 | 180 | 0 | 花筑·苏州山塘御苑精品民宿 → 虎丘山风景区 → 山塘河宴·周公蟹·松鼠桂鱼(山塘街店) → 留园 → 七里山塘景区 → 凝翠园饭店 → 花筑·苏州山塘御苑精品民宿 |
| R10-p04 | 162 | 18 | 花筑·苏州山塘御苑精品民宿 → 虎丘山风景区 → 山塘河宴·周公蟹·松鼠桂鱼(山塘街店) → 留园 → 凝翠园饭店 → 七里山塘景区 → 花筑·苏州山塘御苑精品民宿 |
| R10-p09 | 138 | 42 | 花筑·苏州山塘御苑精品民宿 → 七里山塘景区 → 山塘河宴·周公蟹·松鼠桂鱼(山塘街店) → 留园 → 虎丘山风景区 → 凝翠园饭店 → 花筑·苏州山塘御苑精品民宿 |

工程应提供独立核算与来源证据，必要时由相应领域人员复核营业/最晚入场、餐次窗口、交通方式、酒店返回及等待时间是否与任务相符，162/138 分钟两个参考是否真正满足需求。只减少路线但违反营业或餐次的排列不能得分。餐厅池固定为当前两家；新餐厅、新地点或新交通方式必须另补路线并增加版本。P2准备时尚未执行模型；后续P3三次真实输出均保留原排列、交通180分钟，未实现路线改善。162/138分钟仍是待审参考，不是模型成果；用户满意度未验证。

## 其余参考与 judge

其余 28 例也必须复核，并非因 synthetic 就默认答案正确。尤其核对 T09 的 18:00 边界、T10 抵达缓冲、T17 两个过期检查点，R07/R08 的有限恢复及失败保留、R09 固定休息/19:00 离开窗口、R12 并发后的最新状态。

辅助 judge 暂未调用，也没有校准成绩。未来须另选开发材料冻结12份条件化人审输出再执行两次judge；P5旧面板含holdout，只作诊断审阅，不用于调优。校准时人工一致与重复一致均至少 10/12，记录版本和证据哈希。测试代码中构造的校准记录只测试门禁，不能移用为真人校准证据。P2 可以交付代码评分器，未完成人审和正式实验的部分继续明示。
