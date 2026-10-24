# 手动验证脚本的范围与运行前提

这些不是普通pytest测试，也不自动代表当前服务可用、完整网站覆盖或USER验收。历史日期、候选和故障属于固定素材。先读各脚本说明，不连接本机业务数据库，不为运行旧脚本重启现有服务。

## 本批保留

| 脚本 | 输入/副作用 | 本轮检查 |
| --- | --- | --- |
| ltp3_demo.py | 在新进程中先创建临时SQLite，再装配模拟路线/AI；提供本地ASGI演示 | 用隔离ASGI请求核对，真实服务全部禁止；不是完整应用路由或真实建议 |
| ltp27_recovery_demo.py | 复用同目录ltp3_demo.py；以临时目录flag注入失败/丢完成事件 | 同样为模拟故障；历史model_calls计数表示被包装的说明投影尝试，不是模型API调用次数 |
| ltp27_ticket_replay.py | 显式--source历史JSON目录、--output新文件；patched load仅返回传入快照 | 离线安排/缓冲事实回放，不查网站/模型，不连接业务库 |
| recommendation_samples.py | 显式输入P03 results.json与全新输出文件 | 离线餐厅事实比较；数量从输入计算，不再写死20/8；不是用户采纳或真人味觉评价 |

普通执行目录为backend，使用锁定环境并显式设置 `PYTHONPATH=.`。例如：

```bash
PYTHONPATH=. python tests/manual/ltp27_ticket_replay.py --source /path/to/archived-ltp27 --output /tmp/new-ticket-replay.json
PYTHONPATH=. python tests/manual/recommendation_samples.py /path/to/p03-results.json /tmp/new-dining-replay.json
```

输入素材在历史交接所列本机证据目录，不随仓库发布；不存在时先报告缺失，不能自行编造数据。不要覆盖原证据。演示服务器只有明确手动执行脚本时才监听127.0.0.1，使用新的测试进程与临时库，不能把演示模块导入已有应用进程。

## 本次排除、只保留本机的旧脚本

- journey_replay.py：固定草稿ID，默认数据库无隔离强制保护。
- phase1_baseline.py、recommendation_journey.py：固定历史在线任务，对调用者给定服务创建/编辑/定稿，无服务身份保护。
- phase1_sources.py：直接按本机配置真实批量查询供应商；本轮不执行或认证。
- phase1_verify.py：要求原专用证据树/数据库且有历史相等断言和可选真实查询，未证明对当前素材开箱可用。
- ticket_browser_demo.py：固定个人路径/端口；无context推荐请求仍受支持，但不能证明已有安排过滤或扩展实装。

历史交接中的这些命令只记录当时操作，本次未将对应脚本作为可发布复验工具纳入。保留在用户本机，不删除、不搬动、不将旧成功结果改写为新版本通过。
