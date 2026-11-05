# 旅行记录第一版

2026-11-03。用户授权在当前项目实现独立的旅行记录、相册、足迹、从已有行程补记、备份恢复。入口为导航「旅行记录」和 `/travel-records`。本阶段仍为本机单用户，无公开部署、账号、云同步或Git提交。

## 已实现的使用流程

1. **记录旅行**：选择实际到过的城市，填写可选名字、文字、日期。支持一次旅行多城、同城多次到访，年/月/日或未知日期；不能将未来日期保存成已发生经历。城市可以先手动记录，经纬度留空时明确标记“位置待补”，不伪造地球点位。
2. **整理相册**：原件按上传字节保存，预览处理EXIF方向和透明背景；查看器显示原图、键盘前后切换、下载原图。支持照片说明、顺序、封面、封面取景位置和片段关联。照片与片段可软删除/恢复，片段恢复保留关联照片。
3. **回看足迹**：城市去重、旅行次数、到访次数分开计算；城市、年份、文字搜索联动相册。回收站不计足迹。COBE 2.0.1的参数与镜头数学沿用 `finn-digital/src/components/travel/travel-globe.tsx` 和 `src/lib/travel/globe-view.ts`，适配Vue；支持拖拽、键盘、自动转动、选城聚焦、减少动态效果、页面不可见时暂停。无WebGL时保留城市列表与相册。
4. **从行程补记**：可以在记录页选择来源，也可从我的行程、已保存结果、多城只读版本进入。默认不勾选到访，不自动沿用计划日期；需要用户确认。服务端核对来源快照及实际勾选范围。原计划、城市工作副本和偏好均不写入。恢复备份后即使原计划不在本机，仍能完整阅读回忆。
5. **继续未完成编辑**：IndexedDB保存文字和待上传File，页面刷新或返回列表后可继续。上传逐张进行，失败保留剩余队列和已保存内容；失败后暂停队列以保留原顺序。保存成功才清除草稿。草稿写入失败明确提示保留页面；未编辑的页面不生成无意义草稿。
6. **完整备份/恢复**：页面底部下载ZIP，包含正式记录、原件、顺序/说明/封面/关联和回收站。选择ZIP后展示新增、相同、冲突、已恢复过及原件修复数量，确认后恢复。冲突可另存副本或跳过；现有回忆不覆盖。预览后有其他修改会拒绝旧预览。重复导入不重复新增，缺失/损坏原件可按备份哈希修复；原件缺失时拒绝导出不完整备份。

## 文件与运行

- 页面：`frontend/src/views/TravelRecordsView.vue`、`TravelMemoryView.vue`、`TravelMemoryEditorView.vue`；组件位于 `frontend/src/components/memory/`，共享类型、请求与草稿仓库分别在 `types/travelMemory.ts`、`services/travelMemory.ts`、`services/memoryDrafts.ts`。
- 后端：`api/routes/travel_memories.py`、`models/travel_memory.py`、`services/travel_memories.py`、`memory_media.py`、`memory_backup.py`。已有启动 `init_db()` 创建新表 `travel_memories`；没有修改旧ORM表结构或业务记录。
- SQLite仍遵循 `DATABASE_URL`；原件目录默认 `backend/data/travel-memory-media`，可用 `TRAVEL_MEMORY_STORAGE_DIR` 指定绝对路径。整个应用的数据目录备份应同时保存SQLite和原件目录；页面ZIP只备份旅行记录模块，不包含计划和浏览器未提交草稿。
- 新依赖仅为精确锁定 `cobe@2.0.1` 与 `Pillow==13.0.0`，既有依赖版本未升级。安装用 `npm ci`、`python -m pip install -r requirements.txt`，之后重启后端。
- 隔离演示页面：`http://127.0.0.1:15183/travel-records` → 后端18033，使用 `output/travel-memories/ui.db` 和 `ui-media/`。示例标题标注“演示”，图片是生成的测试图形；不要将其视为用户真实旅行。第二个空库恢复实例15184/18034仅用于恢复验证，已停止，数据与证据保留。

## 数据来源与边界

离线城市索引共7940条，基于 [GeoNames城市数据](https://download.geonames.org/export/dump/) 的cities15000、countryInfo、admin1Codes以及语言标记的中国城市别名；保留原参考库14座城市。坐标为城市参考中心，不是照片拍摄点或到访轨迹。中文标签使用非历史中文别名，国际城市保留原来源名称，并支持中文别名搜索；同名城市显示省州与国家供用户确认。可手动补充未覆盖地点。

GeoNames数据依据 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) 使用，搜索界面提供署名链接；快照SHA-256、筛选范围在 `backend/app/data/memory_cities_source.json`，重建脚本为 `scripts/build_memory_cities.py`。索引约1.15 MB，仅在后端加载，不需要在线地图密钥或调用LLM。

第一版照片支持静态JPEG/PNG/WebP，每张20 MiB以内、4000万像素以内，每次旅行最多500张（含照片回收站）。HEIC需先导出JPEG。单份ZIP最多512 MiB、清单8 MiB、2000条记录；超限明确失败，不生成部分备份。恢复预览有效一小时。回收站保留原件，不提供永久删除或自动压缩。IndexedDB受当前浏览器/站点存储空间和清理行为影响，不能代替正式保存和外部备份。原件及ZIP保留照片元数据，仅在本机使用。

## 验证与证据

自动回归最终数字见下方运行记录。新增后端用例覆盖日期精度、重复到访、创建/更新/上传幂等、并发CAS、原件与EXIF预览、排序/软删除、磁盘失败、体积限制、原件修复、完整备份、冲突复制/跳过/重复确认、过期/陈旧预览、路径穿越/缺件/坏哈希/重复文件/链接及来源计划/明确偏好原样保留。新增前端用例覆盖城市/日期统计、编辑副本隔离、来源确认、恢复错误、并发核对、本机失败保留、撤销删除与照片关联。

浏览器使用Chromium和两套隔离SQLite/媒体目录，实走直接记录、月份日期、两张照片与片段、刷新续写、上传失败后刷新重试、说明/封面取景/顺序、照片和片段回收站、旅行回收站、单城与多城补记、完整下载、相同备份跳过、冲突副本、重复恢复以及空库恢复。并发修改与503上传失败、WebGL缺失是明确注入的故障场景。390px亮暗色、桌面、原图1600px回看和减少动态效果分别检查；库页和编辑页无横向溢出。

空库恢复包含3条记录、2个原件；原件与上传文件逐字节相同，恢复文档与ZIP清单相同。原实例保留新文字，旧备份仅产生1个副本，再次恢复不新增。字段/原件复核脚本与22项结果在 `output/travel-memories/verify_evidence.py`、`verification.json`；浏览器截图与下载文件在 `output/playwright/travel-memories/`。记录与照片均为隔离演示数据，没有用用户业务库、没有新地图/酒店/票务外调，不能代表真实旅行数据或真人满意度验收。

运行记录：后端1049通过、4项外部smoke跳过；前端44个测试文件、284项通过，`vue-tsc`与Vite生产构建通过。新增模块32项后端、17项前端验证。构建仍有既有主包体积/高德混合导入提示，未据此升级或拆分无关依赖。原业务 `backend/data/trips.db` 修改时间仍为2026-10-19；没有向该库执行验证或迁移。

复验命令（从backend/frontend各自目录运行；后端必须指定隔离库及媒体目录）：

```bash
memory_test_dir=$(mktemp -d /tmp/ltp-memories-test.XXXXXX)
DATABASE_URL="sqlite+aiosqlite:///$memory_test_dir/trips.db" \
TRAVEL_MEMORY_STORAGE_DIR="$memory_test_dir/media" \
python -m pytest -q

# frontend目录
npm test
npm run build
```
