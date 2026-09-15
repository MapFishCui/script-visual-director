# 导演组、视频段任务与镜头（v0.7）

导演组是一次合并输出的完整剧情段落，可以53秒、48秒或更长。一个导演组包含多个视频段任务；一任务对应一次生成，可含多个镜头。先按情绪与信息设计导演组，再把镜头分配到任务；不按15秒切断段落叙事。

内部 JSON 的 `groups` 为兼容旧项目保留，实际表示短视频段任务；新增 `director_groups` 表示导演组。不要根据旧字段英文名称继续把两者混为一谈。推荐任务编号 T01、T02，导演组编号 D01、D02；旧任务 G01 等无需改名。每个任务的镜头连续、全片覆盖一次；每个导演组的任务也连续、全片覆盖一次，不能漏项、重复或重排。

## 创作与规划

1. 按 [二次创作](creative-development.md) 写完整改编场景与导演组意图，确认后编写中文电影分镜。
2. 划分视频段任务并检查目标输入限制。当前 AIMixer H3 参考流程每任务计划≤15秒，绑定参考视频每段2–15秒、单任务合计≤15秒；最多9图、3视频、共12项参考。导演组和全片审核串联片没有这个15秒上限。其他系统先核对模式限制，不继承H3预算。
3. 任务从0计时并编译完整目标提示词及中文对照；导演组保留总体时间轴、每段起点、叙事意图与前后衔接。不能给每段都安排一个假结局或为了凑满15秒加戏。
4. 在项目页同时审核导演组、内部任务、逐镜中英稿，再确认布局和可选预演，随后生产基准与扩展资产。
5. 每导演组导出一个独立导演包：包内多个任务依次生成，在目标导演台合并为本组输出。多个导演组分别导入和合并，不把全片全部任务塞入同一个合并输出。

53秒示例可以由13+14+14+12秒四个任务组成；48秒示例可由12+12+12+12秒组成。这是计时结构示例，不是推荐的电影剪辑节奏。真实任务时长来自台词、动作和反应估时。模型帧对齐可能使最终合并时长略增，导出报告列出原计划与对齐后时长，需在目标端检查尾帧。

## 方案数据

`groups-apply` 输入字段：revision、project_revision、adapter、shared_references、groups、director_groups。

- adapter 为 generic 或 aimixer-h3；其他目标先使用通用包，不伪造原生格式。
- groups 每项仍含 id、title、shots、intent_zh、continuity_in、continuity_out、references。
- director_groups 每项含 id、title、tasks、intent_zh、continuity_in、continuity_out。例如：

```json
{"id":"D01","title":"来客与第一次预警","tasks":["T01","T02","T03","T04"],"intent_zh":"从夜班日常进入不安，以她决定核实危险结束。","continuity_in":"她独自复习，尚无异常信息。","continuity_out":"她开始核实男人的警告；不提前表现对循环的理解。"}
```

图片引用 `{key,kind:"image",asset,version}`；视频引用 `{key,kind:"video",index,item}`，指向工具已验证的逐镜／任务预演索引。只选择纯摄影机候选，不把整个53秒导演组预演当作单次输入。公共素材仅支持图片，实际素材按版本和SHA-256核验，缺失保持待绑定。

`groups/state.json` 保存两层结构、版本及批准，旧版状态只读时不重写。旧短组解释为任务，页面提示补充导演组；不得自动把所有任务归到一个剧情段落或沿用旧批准。保存新版方案保留历史并撤销组批准，要求重新核对中英稿及衔接；原逐镜内容和图片不覆盖。

## 命令与审阅

```sh
.venv/bin/python scripts/svd.py groups-apply PROJECT PLAN_JSON
.venv/bin/python scripts/svd.py groups-request PROJECT work/request.json
.venv/bin/python scripts/svd.py groups-sync PROJECT work/sync.json
.venv/bin/python scripts/svd.py groups-confirm PROJECT --evidence '用户实际确认当前两层方案及中英稿'
.venv/bin/python scripts/svd.py groups-check PROJECT
.venv/bin/python scripts/svd.py groups-previs PROJECT previs/runs/RUN/exports/EXPORT/index.json
.venv/bin/python scripts/svd.py groups-package PROJECT delivery/D01.mmxpack.zip --director-group D01
.venv/bin/python scripts/svd.py groups-bundle PROJECT delivery/all-director-groups.zip
```

单个导演组可省略 --director-group；有多个时必须明确选择或用 groups-bundle。总ZIP是运输包，先解压再分别导入其中的 D01.mmxpack.zip、D02.mmxpack.zip，不能把总ZIP直接当成原生导演包。通用模式每组输出通用ZIP，提供中英稿、任务次序和素材绑定，可手动逐段生成后剪辑。所有任务正式导出需真实资产检查、用户确认和项目校验通过；--draft只放宽未完成项，不放宽输入尺寸／时长限制。

同步包仍为 revision、project_revision、storyboard_fingerprint、groups（逐任务 id/text/translation_zh/check_note）。request同时给出导演组完整意图与任务预算；每段目标文本必须结合所属导演组写。任务镜头编号从1开始，切点为段内时间，中英文一起确认。网页可编辑两层名称、意图、进入／退出状态及成员列表；跨组移项须一次提交完整覆盖方案，保存后回Codex同步。不能替用户点击生产项目的批准。

## 预演和输出边界

groups-previs 为内部任务生成短预演，并为导演组生成整体节奏审核预演。索引以 level=task/director 区分；导演组级视频不允许作为任务参考绑定。缺少成员镜头则该任务／导演组显示待完成，不拼出假完整视频。重组会使关联预演证据过期，按最新版本复核。

本skill不采样最终AI视频，也不自动操控目标导演台的合并按钮。它交付每组独立任务包及合并顺序，供目标端执行。不能把53秒预演说成已生成53秒最终影片。

## 当前 AIMixer 原生映射与验证

对照本地检出的 [AIMixer 导入源码](https://github.com/AIMixer/ComfyUI_MiniMaxH3_Director/blob/52f8fb7b8d8eb6bebf33ebb534827efa8f95484c/director/pack.py)，适配版本固定为该提交。

一个原生 `.mmxpack.zip` = 一个导演组；包内 `asset_groups/0001/group.json` 等分别是短任务，导入器映射为 segments。提示词按任务保留完整六部分，共用图片占先前槽位，本地图片接续。每个包重新从0开始时间轴，exportMode=all；目标端实际合并效果仍需测试。不要把源码里的 asset_groups 误认为本skill的导演组。

frameCount依上游24fps、17k+5对齐；durationSec保存创作秒数。默认画布864×480，连续性引导关闭，使用者按实际工作流调整。extra/director_group.json、shot_map.json、delivery.json 保存导演组意图、原片／任务切点、中文对照、目标输出名称、原计划与对齐后时长。所有结果保留 target_h3_validated=false。

可选契约测试通过 SVD_AIMIXER_SOURCE 指向该源码，验证真实导入、时间轴组装、媒体复制与路径重写；不启动ComfyUI或H3推理。适配器升级后重新验证，不能将源码导入成功等同于最终视频效果验证。
