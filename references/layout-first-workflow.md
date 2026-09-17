# 中文导演稿 → 平面图 → 整场调度白模 → 正式分镜

这是保留的布局优先流程，已有项目或用户明确选择时采用；新完整项目默认参见 keyframe-grid-workflow.md。对话里的情节分镜仍按轻量入口。已有项目保留原阶段与记录，不自动重建、批准或迁移；review-init 对已有项目仍拒绝覆盖。

## 中文导演稿与平面图

首个确认对象就是页面中的逐镜“中文导演稿”：场景、镜头运动、人物运动，连同时长、台词语气及必要创作依据。这是包含拍法的中文方案，不是必须另写的一篇散文。保留原情节和分析；creative-treatment.md 可作为辅助改编资料，不是确认门槛。

review-init PROJECT --workflow layout-first-v1 初始化后，review-serve 打开同一页；可直接带完整中文稿初始化，也可先保持空镜表展示进度，再用 review-storyboard 导入。不要用占位镜头。程序的 analysis 阶段对应“中文导演稿确认”，指纹同时绑定分析文件和当前中文逐镜正文；不要求系统原文先生成。用户确认之后即可 render-layout、review-layout 和 review-confirm --stage layout。

平面图用米制比例确定结构、物件、通道及人物初始位置，结合中文稿中的拍法检验空间。独立观察机位或场面路线可用 shot=null；已有明确对应关系则用真实镜号。正式机位细化仍可在后续预演适配输入中完成。

## 整场白模先确认行动

blocking 阶段与 previs 阶段独立。前者使用能看清行动的观察机位，可辅以俯视与局部诊断视角，展示事件先后、并行动作、接触和遮挡；这些视角不是最终剪辑。用户看到的是整个场面的调度，动作段编号不是镜号。

白模精度以能判断行动为准：

- 场地与关键物件有正确比例和可用结构；门洞、门扇轴心、通行净空、台阶或坡面应实际建出。复杂轮廓会影响行动或遮挡时，不用粗方块代替。
- 人物身高、体积、朝向和可辨认姿态应符合设定；转身、俯身、跨越、坐起等必要动作实际动画化，不能仅匀速滑动模型冒充表演。
- 关键交互要表现触及、抓握、开合、持物跟随和释放的先后；检查手与目标接触、穿插、脚底高度与遮挡。达不到的细部明确标为未验证，不伪称精确物理模拟。
- 服装轮廓仅在妨碍行动或影响剪影时体现；皮肤、织物纹理、精细面部、真实风雪与口型不作为调度通过依据。灰模可用简单区分色，但不混同最终资产美术。
- 同一世界时间轴维护人物、门与物件状态。观察播放时长只是行动参考；正式分镜可省略、停留或交叉剪辑，不被它锁死。

先对最容易出错的接触与遮挡渲染诊断帧，修正后完整输出；不能因为由 AI 写脚本就免除检查。大场景分场独立运行，当前绑定器一次只绑定一个布局，不宣称自动跨场景拼接。

## 命令与数据

```sh
.venv/bin/python scripts/svd.py blocking-choice PROJECT generate --evidence '用户要求先看整场调度白模'
.venv/bin/python scripts/svd.py blocking-bind PROJECT blocking/adapter/build.py --coverage COVERAGE_JSON
.venv/bin/python scripts/svd.py blocking-run PROJECT --mode smoke
.venv/bin/python scripts/svd.py blocking-run PROJECT --mode render
.venv/bin/python scripts/svd.py blocking-check PROJECT blocking/runs/RUN --note '实际观看后的检查与未验证范围'
.venv/bin/python scripts/svd.py review-confirm PROJECT --stage blocking --evidence '用户确认本版整场白模的原话'
```

用户选择跳过时用 blocking-choice PROJECT skip --evidence 原话，页面显示已跳过（未验证），然后继续分镜。不能把跳过写成检查通过。后续逐镜预演另外选择。

适配脚本、运行参数、输出目录和编码协议复用 local-previs.md：--smoke／--render／--out；必须实际用 Blender 后台执行，保留日志、PNG、可编辑 output/critical-previs.blend 与 MP4。运行结果与输入全部在 blocking/ 下，不覆盖 previs/。

脚本同目录 job.json：

```json
{
  "fps": 12,
  "beats": [{"id":"B1","duration":6,"action":"本动作段实际行动","start_state":"位置、姿态和物件起始状态","end_state":"实际结束状态"}],
  "clips": [{"beat":"B1","duration":6,"original_start":0}],
  "source_layout":"spatial/LOC/layout-v001.json",
  "layout_fingerprint":"当前布局指纹",
  "input_sha256":{"layout.json":"实际布局副本 SHA256","build.py":"实际脚本 SHA256"}
}
```

这是数据结构示意，须替换真实内容和指纹。覆盖文件为 {"required_beats":["B1"],"reason":"整场行动范围"}，必须列出所有动作段。每段对应连续世界时间，段内可以多人并行动作。clips 的时间与 beats 对应；不设置 per_shot_v1。frame-map 使用 frame、beat、original_time；render-report 和 comparison PNG 按 local-previs 协议。完整检查验证覆盖、实际解码帧数／尺寸／帧率、视频及 .blend 指纹；smoke、局部视频或文字说明不能确认为整场完成。

## 中文稿导入与最终分镜

review-storyboard PROJECT PACKET_JSON 在空镜表的现有项目首次导入中文导演稿，发生在首个确认之前，不覆盖已有镜头。包结构为 {"revision":1,"shots":[],"storyboard":{}}：revision 取最新项目版本，shots 填 schema.py 的完整非空 SHOT 列表，storyboard 为同镜号完整中文字段映射（director-review.md）；空包不可运行。已有镜头使用 review-edit。

用户在页面确认中文导演稿，程序记作 analysis；确认布局，再确认 blocking 或记录跳过。之后才能 review-export／review-sync 编译最终系统分镜，完成导演审核并逐镜确认。白模后的正式分镜是经验证和适配的执行版本，不是重新从零生成一套镜头。

中文正文修订会使中文稿确认及依赖它的布局、调度确认过期；只改系统翻译不会撤销上游确认。若修订影响空间与行动，更新适配输入再检查；不受影响的结果可经实际复核保留，不能自动当作已确认。修改布局文件、调度脚本／输入、视频或 .blend 时对应检查过期。程序检查版本，语义影响仍需助手核对。

最终分镜确认后 previs-* 负责逐镜摄影机预演；整场调度录像不直接作为逐镜参考包。H3 文本在真实素材绑定后重编译，明确采用的参考内容。整场白模、导演组长度不受单次 H3 生成时长约束。
