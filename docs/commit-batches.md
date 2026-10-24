# 提交整理执行记录与收尾范围

2026-10-24，核对至已提交 `3b3a93c`。最初基准为 `57bd8a4`；原大批未提交成果已经按用户逐次授权提交，下面不是“尚未执行”的新拆分计划。没有推送。

## 已执行提交

| 提交 | 范围 |
| --- | --- |
| `7bf4582` | refactor: centralize bounded external service calls (batch 1) |
| `a9f8bb8` | refactor: unify graph state and recover discovery streams (batch 2A) |
| `3b7667f` | fix: finalize drafts atomically and reject stale writes (batch 2B-1) |
| `5339374` | fix: preserve draft attraction edits during rebuilds and AI reorder (batch 2B-2) |
| `97de7c0` | fix: preserve AI meal slots and validate saved dining facts (batch 2B-3) |
| `d64f682` | fix: project saved itinerary facts and protect read-only results (batch 2B-4) |
| `6dc897c` | fix: preserve hotel quote conditions and budget completeness (batch 3A) |
| `42942b6` | feat: preserve dining intent and protect restaurant replacement (batch 3B) |
| `bdc5ac0` | feat: rank hotels by area distance and explain saved recommendations (batch 3C) |
| `81902ef` | feat: protect later departure with travel windows and fixed rests (batch 4A) |
| `8900933` | feat: compare transport alternatives and synchronize saved days (batch 4B) |
| `026500d` | feat: add multicity snapshots and explicit boundary-day adjustment (batch 4C) |
| `c0f5b4b` | feat: rank browser ticket candidates against saved schedules (batch 5) |
| `53f4671` | feat: refine trip workspace and saved itinerary reading (batch 6) |
| `bf849eb` | fix: preserve current trip facts and routing boundaries (batch 7A) |
| `46c30e0` | refactor: organize timeline helpers and API declarations (batch 7B) |
| `92ef495` | test: guard legacy reads and finalize failures (batch 8) |
| `3b3a93c` | refactor: finish source and regression test cleanup |

历史交接中的测试数对应当时版本；最新源码收尾隔离结果为后端623通过、4 smoke跳过，前端239通过、构建通过。模拟验证、离线回放、真实服务和真人验收分列，不互相代替。

## 两批收尾

1. 源码与测试：`3b3a93c` 已提交11文件。明确排除的未使用常量/导出、未接入字段和模型元数据片段仍留本地，不再拆新功能批。其后新出现的观测实现属于独立进行中的工作，本记录不替它完成或提交。
2. 文档、手动脚本和忽略规则：本轮仅审查与准备候选，尚未暂存/提交。保留当前入口说明、带日期的交接/限制、通过隔离核对的脚本与运行说明；依赖固定本机记录、旧接口或无隔离保护的一次性在线脚本，以及两份独立观测评估文档列为本地排除。

精确清单及验证见本机 `output/docs-scripts-closeout-review-2026-10-24/`；output未随仓库发布，克隆者不自动取得。

## 版本管理边界

- 运行时 `frontend/src/data/railStations.json` 必须保留，不能当缓存忽略；站名表不代表实时票价。
- 扩展源码版本0.2.2已入库；ZIP由 `scripts/package_ticket_extension.py` 经前端predev/prebuild自动生成，已忽略，不纳入提交。当前本机旧ZIP保留，不因文档检查覆盖；源码测试通过不等于新版扩展重新实装。
- `.playwright-cli/`、`output/`、`docs/cv/`根目录忽略；原证据、设计产物、简历保留本地，不删除或移动。
- requirements和package-lock随前面源码批次保留，不在收尾升级依赖。
- 本机localhost链接、仓库外路径和忽略的截图/JSON是历史证据位置，不作为克隆后可自动获得的发布材料。
- 不使用git clean、git rm或git add -f来“清空”工作区；明确排除的片段保持未提交，业务库不变。
