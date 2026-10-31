# P5 产品规则与条件化评估：实施交接

日期：2026-10-25。按用户后续代码授权实施PR01=B、PR02=A、PR03以A为主并按需追问。保留原30例、真实P3实验及P4发布快照；参考仍待人工确认。本轮没有真实模型、judge、地图或票务网站调用，没有依赖升级、ORM迁移、业务库写入或Git提交。

## 已实现的行为

- **时间约束**：`DayDetail/DayPlan.time_constraints`只增加JSON字段，分别记录可移动开始时间、最早开始下界、固定开始时刻和景点/用餐固定时刻。锁定顺序独立保留。新装配的日程允许交通预览延后非固定开始；旧记录缺字段时保留原时间，不推断其预约可移动。
- **日程编辑与保护**：每日编辑的“时间约束（可选）”支持上述条件，固定活动可沿当前时刻设置。重算、强制装配、AI重排、交通同步、定稿和历史结果共用约束检查；失败保留已存状态、原CAS和时间约束。模型返回的时间约束不被直接采用。
- **推荐与预览**：候选带`direct/requires_adjustment/conflict`和逐项前后时刻。卡片区分原安排可用与需调整后可用，采用继续走原预览/确认，无新增普通路径确认弹窗。取消项目仍走既有用户主动调整入口。
- **偏好缺省**：默认“先看不同选择”。按已知价格、车上时长、到达时刻和已有衔接余量展示有实际区别的候选，不设唯一赢家，不为凑3条添加重复选项；该默认路径不调用模型。用户明确选价格/时间/日间/均衡后才进入已有模型筛选与规则回退。
- **明确条件**：“更多要求（可选）”设置接受席别、每人列表参考价上限及出发/到达时段。必须满足的条件在模型前过滤；无匹配明确说明当前列表范围和可修改条件，未知价无法确认满足上限，不静默放宽、降级或编造体验。票价仍不升格为同行含税总价。
- **脱敏Trace**：保留既有开关/失败隔离；新增偏好事实只记录匿名席别标识、数值和布尔条件，补充意图原文不上传Trace。本轮未上传云端。

关键实现：[时间约束](../backend/app/services/schedule_constraints.py)、[同步预览](../backend/app/services/journey_comparison.py)、[推荐可行性](../backend/app/services/ticket_schedule.py)、[本次偏好](../backend/app/services/ticket_preferences.py)、[推荐服务](../backend/app/services/ticket_assistant.py)、[候选界面](../frontend/src/components/BrowserTicketAssistant.vue)、[每日编辑](../frontend/src/components/draft/DayCard.vue)。

## 评估v2与旧实验兼容

[conditional-v2.0](../backend/evals/conditional.py)及[12份版本化草稿](../backend/evals/conditional_cases.json)单独存在，未改旧`datasets/`和rules-v1.1。12份变体来自5份已见基础材料，不代表12个新增独立样本或新的未见holdout。

支持：条件化接受集合、并列、成对优先关系、未说明偏好不评排名，以及日期提前拒绝时余量null的分阶段语义。引用原日内约束评分时仍使用独立评估代码，不借生产规划器生成gold。输入哈希与`2.0-draft-PSxx`版本绑定，拒绝把旧真实输出套到新偏好；人审未完成时仅诊断，回放正式成绩始终null。

运行命令（现有隔离Python，无需安装依赖）：

```bash
cd backend
${EVIDENCE_ROOT}/eval-p0-20261024/venv/bin/python -m evals.conditional validate
${EVIDENCE_ROOT}/eval-p0-20261024/venv/bin/python -m evals.conditional replay --directory /tmp/p5-conditional-new-run
```

输出必须是仓库外的新目录。运行器冻结app/evals源码、数据与版本/依赖清单，每场景独立子进程和SQLite，复用P3断网/禁止凭据和原库访问的guard。只允许离线模型替身/固定事实；无实时模式或judge入口。保留所有计划槽位、逐槽证据、失败和部分进度，不覆盖已有目录。

本次最终报告：[回放报告](${EVIDENCE_ROOT}/eval-p5-implementation-20261025/replay-handoff/report.json)、[冻结manifest](${EVIDENCE_ROOT}/eval-p5-implementation-20261025/replay-handoff/manifest.json)。R10的中性模型替身仍保留原顺序，路线改善诊断FAIL；不会为变绿而使用参考答案生成模型输出。本次诊断检查33 PASS、1 FAIL、2 NOT_EVALUATED，是检查计数而非案例通过率；所有结果仅证明回放/评分工程能力，不是新模型质量成绩。

P4仍展示原真实实验，未将本轮替身报告混进真实运行统计。v2报告当前单独导出JSON，尚未接入P4发布格式；后续如做真实v2实验需先适配用量估算并披露费用，不能复用原P3预算授权。

## 验证与证据

最终测试日志见 [后端](${EVIDENCE_ROOT}/eval-p5-implementation-20261025/evidence/backend-handoff.log)、[前端](${EVIDENCE_ROOT}/eval-p5-implementation-20261025/evidence/frontend-release.log)、[构建](${EVIDENCE_ROOT}/eval-p5-implementation-20261025/evidence/build-release.log)。后端870项通过、4项外部smoke跳过；前端250项通过，构建通过。构建沿用既有chunk等提示，不把它们称为新故障或供应商验证。

浏览器用独立15176前端/18028合成服务，未替换原业务服务器。服务仅挂本轮所需路由、使用独立SQLite、地图替身并禁用真实模型：

- [采用闭环](${EVIDENCE_ROOT}/eval-p5-implementation-20261025/evidence/browser-flow-final.log)：模拟扩展回传，B卡片披露11:00→11:10；预览无写入，确认后草稿和刷新保持11:10、锁位及未知同行总价。
- [边界检查](${EVIDENCE_ROOT}/eval-p5-implementation-20261025/evidence/browser-boundaries.log)：固定活动11:10后尝试11:30被拒绝；保存状态不变；商务舱无匹配时不降级、不出现采用按钮。390px暗色无横向溢出，见 [截图](${EVIDENCE_ROOT}/eval-p5-implementation-20261025/evidence/mobile-dark.png)。这是合成UI验证，不是扩展实装、真实查票或真人体验验收。

原库、依赖/锁、`.env`、旧数据及P3/P4证据的前后保护核对见 [保护记录](${EVIDENCE_ROOT}/eval-p5-implementation-20261025/evidence/preservation-after.json)。

## 当前边界与待人工事项

普通同步仅延后可移动的开始，不自动提前出发侧既存安排、跨日搬移或全局优化。固定时刻不明的旧记录需要在可选时间约束中核对；不通过默默改变旧字段消除冲突。席别仅按当前读取到的产品名称核对，不保证覆盖网站全部席别/报价；门到门和接驳仍沿已存估计。

原30份参考和新12份参考草稿都未由本次代码授权确认为gold。独立人工核算、偏好覆盖/分歧、judge校准和USER验收继续待完成。原方案发现/创建草稿/SSE等Trace缺口亦未由本轮补齐，不宣称P0～P5全量验收或业务质量提升。
