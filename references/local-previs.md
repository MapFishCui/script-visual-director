# 本地 Blender 预演与用户选择

布局确认后先询问“生成预演／跳过预演”。说明本剧有哪些走位、遮挡或运镜值得检查；这是建议，不是强制条件。用户已明确选择时直接沿用，不重复问。即使复杂场景，用户也可以跳过；记录原话、当前布局版本及“动态空间未验证”，继续资产流程，不写成检查通过。以后修改分镜或布局，旧选择失效，重新询问。

## 用户选择与后台执行

```sh
.venv/bin/python scripts/svd.py previs-choice PROJECT generate --evidence '用户原话：需要预演'
.venv/bin/python scripts/svd.py previs-choice PROJECT skip --evidence '用户原话：这次跳过预演'
```

审核页也提供两个选择按钮。点击只保存决定，不在浏览器启动进程；用户回当前对话说“继续预演”后由 Codex 执行。Blender 使用 `--background --factory-startup` 独立进程，不弹工作窗口，不改用户正在编辑的 .blend，不安装常驻服务。审核页仅显示状态与结果链接，不自动嵌入或播放视频；需要查看时按需打开。

skip 会保留旧资料及 pending 检查记录，并解除本轮白模生产依赖；跳过不是“已验证”。选择重新生成会恢复此前建议的白模要求，并撤销跳过状态。布局与分镜确认仍是前置条件。

## 本机检测

```sh
.venv/bin/python scripts/svd.py previs-doctor
.venv/bin/python scripts/svd.py previs-doctor --blender /Applications/Blender.app/Contents/MacOS/Blender
```

自动查找 PATH、macOS 应用目录或 Windows 标准安装目录；也可指定可执行文件。不要猜测安装完成，不替用户安装软件。检测不到时保存准备材料；用户说“装好了，继续”后再次检测并接着执行。辅助命令用技能 .venv；bpy 由 Blender 自带 Python 执行，无须把 bpy 安装进系统 Python。

## 编写本剧的动画适配脚本

Codex 根据已确认分镜、布局、路线和时长，在 PROJECT/previs 下编写并检查 `build_previs.py` 和配套输入。本地工具负责检测、运行、校验和登记；不会仅凭布局 JSON 自动理解人物心理、产生正确走位。禁止将某一剧的人名、坐标、镜号写死进通用 skill。

适配脚本应使用实际可编辑几何和动画，支持：

- 无模式参数时只建立 `.blend`；`--smoke` 生成有代表性的少量诊断帧；`--render` 生成本任务完整帧序列。
- `--out ABSOLUTE_NEW_DIRECTORY` 指定新目录；拒绝覆盖旧结果。
- 同一时间采样渲染俯视与摄影机视角；输出组合画面和镜号、原片时间、角色标识。每个摄影机视角沿用目标画幅，组合视频可以增加标签栏。
- 角色按镜头时刻更新位置、朝向与必要动作，镜头按实际参数运镜，门和道具状态连续。默认简化人偶；不得用统一静态起点或镜头文字冒充动画。
- MP4/H.264、PNG 帧序列和可编辑 `.blend`。只做空间预演，不生成配音或最终 AI 视频。精确表情、口型、手指接触、真实步态没有实现时明确剩余限制。

同目录 `job.json` 约定：

```json
{
  "fps": 12,
  "clips": [{"shot":"SHOT_01","duration":5,"original_start":0}],
  "source_layout":"spatial/STORE/layout-v002.json",
  "layout_fingerprint":"按layout.layout_fingerprint计算",
  "input_sha256":{"layout.json":"实际文件SHA256","build_previs.py":"实际文件SHA256"}
}
```

所有依赖脚本、布局副本、标签图等均登记 input_sha256，路径相对于脚本目录。job 可包含本剧需要的其他数据；绑定器核对片段镜号、原片开始秒数与已确认镜头的完整时长。多场景先分别准备空间适配，汇总任务需扩展适配器；当前绑定器一次绑定一个源布局，不声称自动支持复杂场景拼接。

另外准备覆盖范围 JSON：`{"required_shots":["SHOT_01"],"reason":"本次需要验证的动作、机位与遮挡，以及其他镜头不需预演的具体判断"}`。Codex 从全部分镜中检查必要镜头，不能为了让局部试片通过而遗漏待验证镜头。用户可选择只做部分或完全跳过，须记录该范围决定及剩余未验证项。

## 运行与检查

```sh
.venv/bin/python scripts/svd.py previs-bind PROJECT previs/blender/build_previs.py --coverage COVERAGE_JSON
.venv/bin/python scripts/svd.py previs-run PROJECT --mode smoke
.venv/bin/python scripts/svd.py previs-run PROJECT --mode render
```

先查看 smoke 帧，解决机位、比例、输入与 API 错误后再完整渲染。长任务用工具会话运行并定期报告进度；不要静默等待到整段渲染结束。每次运行保存在 `previs/runs/时间-编号/`，包含 run.json、日志与 output。失败保留日志和帧，修正后新建一次运行；不要无限重试同一错误。

适配脚本输出 `output/critical-previs.blend`、`output/comparison/000001.png` 起的连续帧、`output/frame-map.json` 与 `output/render-report.json`。frame-map 每项至少有 frame（从1开始）、shot、original_time；report 至少包含 status、rendered_frames（本次真实完成帧号）、video（MP4相对路径或null）。若适配器尚未编码，通用工具使用 Blender 自带序列编辑器将 PNG 合成 MP4，不要求额外安装 FFmpeg CLI。Blender 版本差异以实际测试为准，失败不能视为已生成视频。

实际观看对照视频后记录检查：

```sh
.venv/bin/python scripts/svd.py previs-check PROJECT previs/runs/RUN_ID --note '实际观看后的构图、走位、遮挡、节奏、状态连续性结论'
# 有问题时加 --reject；修正适配输入后重新 bind/run/check。
# 实际检查静态白模与当前布局一致后，另行记录对应布局检查：
.venv/bin/python scripts/svd.py review-layout PROJECT STORE --blockout --note '实际检查依据与剩余限制'
.venv/bin/python scripts/svd.py review-confirm PROJECT --stage previs --evidence '用户查看本版预演后明确确认的原话'
```

工具检查每帧时间／镜号、PNG完整性、Blender实际解码的帧数／尺寸／帧率、输入指纹与镜头覆盖。自动校验不判断表演或美术质量，check 的 note 必须来自实际观看。局部片段未覆盖所有 required_shots 时标记 partial，不登记为可确认的完整预演。检查通过才将视频链接放入审核资料；用户确认是独立步骤，check/run 不授予批准。修改分镜、布局、适配输入或视频使旧检查失效。

本地未装好时也可交给另一台 Blender 机器执行；脚本及输入保留相对路径，回传结果后按相同标准检查，不因为换了机器而省略确认。

Blender 的图片序列合成工作流参考：[官方动画渲染说明](https://docs.blender.org/manual/en/latest/render/output/animation.html)。

## 逐镜交付（v0.5）

新动画任务在 job.json 中设置 `"delivery":"per_shot_v1"`。默认覆盖全部已确认分镜，一镜对应一个完整时长的预演；若用户明确只做关键镜头，记录真实范围和缺失镜号。人物动作与空间状态按同一世界时间线计算，不能每镜恢复初始摆位。仅变更机位时保留人物、持物和门状态。

每个 clip 可附 `start_state` / `end_state` 对象，描述角色位置和朝向、持物、门状态等实际动画状态；不要填入未实现动作。缺少结构化状态时索引标记待人工核对，不冒充连续性已经通过。相邻镜头核对动作交接与视线；时间省略或缺镜必须明确说明。单镜重做可建立只包含该镜 clips 的新任务，保留原片 original_start 和同一状态逻辑；该局部任务不能代表全段已通过，整段串联需用更新后的完整任务重新检查。

render 适配器必须输出两套同帧编号的 PNG：`output/comparison/000001.png` 和 `output/camera/000001.png`。camera 是目标画幅的纯摄影机画面，不带俯视图、镜号、时间栏或标注；不能裁切对照拼图代替真实摄影机渲染。保留全局 frame-map 的镜号和原片时间，编码只选择帧，不改变速度。

新协议 render 完成后自动导出逐镜与串联版。已有完整帧序列可手动导出：

```sh
.venv/bin/python scripts/svd.py previs-export-shots PROJECT previs/runs/RUN_ID
```

每次输出到新的 `previs/runs/RUN_ID/exports/时间-编号/`：

- `shots/SHOT_ID/review.mp4`：该镜摄影机／俯视对照。
- `shots/SHOT_ID/reference.mp4`：该镜纯摄影机参考候选，目标系统实际可用性待验证。
- `timeline-review.mp4`、`timeline-reference.mp4`：按原镜序串联，不补造缺镜，不把局部片段叫完整整集。
- `index.json`、`README.md`：逐镜入口、时长、原片时间、缺镜、跨镜间隔、连续性要求及首末诊断帧位置。

导出检查真实视频解码帧数、尺寸、帧率，并保存源帧与视频 SHA-256。缺少 camera 源帧、时间对照错误、过期任务或损坏输出会失败。导出不授予确认；导出新版本撤销原预演确认，之后实际检查逐镜文件、串联版与状态交接，再 previs-check 和用户确认。检查或确认前再次核对指纹。网页按当前镜号筛选逐镜链接，串联版保持可访问，不自动播放。

参考候选不是 H3 已验证输入，目标单次限制仍需另行适配。超长单镜可在下游按限制细分，保留父镜号、时间范围和承接状态；不得直接加速压缩，也不把整段串联版原样作为单次模型输入。
