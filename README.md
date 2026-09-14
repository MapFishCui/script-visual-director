# Script Visual Director · 操作手册

将剧本转为剧情与角色心理分析、中文导演分镜、目标系统文本及中文对照、空间布局，以及角色、场景和道具参考资产。可选用本地 Blender 制作白模预演，帮助检查走位、遮挡和运镜。

这是一个 **Codex skill 加本地 Python 工具**。Codex 负责理解剧本、导演设计和目标格式适配；Python 负责数据、审核页面、依赖校验与打包；图片需要实际可用的图像生成工具。只执行 Python 命令不会自动写完分镜或生成图片。

## 1. 环境与安装

- Python 3.9 或更高，始终使用项目虚拟环境。
- 可读取本项目的 Codex 环境；制作真实图片时需要可用的图像生成能力。
- Blender 为可选依赖：选择本机预演时安装，不需要预先打开软件。已有 macOS + Blender 5.2.1 LTS 后台渲染验证；其他系统和版本以实际测试为准。
- MiniMax-H3 可以在另一台机器运行，制作前期资料无需在开发机安装 H3。

克隆自己的 GitHub 仓库后，在仓库根目录运行以下命令。不要复制旧电脑的 `.venv`。

macOS / Linux：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python scripts/svd.py --help
```

Windows PowerShell：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe scripts\svd.py --help
```

后文命令使用 macOS / Linux 路径；Windows 将 `.venv/bin/python` 换为 `.\.venv\Scripts\python.exe`。无需激活虚拟环境，也无需向系统 Python 安装 `bpy`；Blender 使用自身的 Python。

若二进制依赖安装失败，先检查 Python 版本与系统架构，确保依赖与解释器匹配，不要直接修改锁定版本来掩盖问题。

## 2. 在 Codex 中使用

最直接的方式是在对话中给出本机 `SKILL.md` 的绝对路径，让 Codex 读取并按它执行。将下例路径换成新机器的实际位置：

```text
请使用 /实际路径/script-visual-director/SKILL.md。
资产输出目录：/实际路径/productions/雨夜来客-test-01。
目标：MiniMax-H3，具体部署方式是……，16:9，时长按剧情合理安排。
风格：电影写实。
先分析紧张度与角色心理，再制作中文导演分镜、目标系统文本及完整中文对照。
分镜确认后制作布局；布局确认后询问我是否预演。
前置确认完成后再生成基准图，确认基准后扩展资产。
剧本：……
```

也可将仓库放入自己的 skill 目录：通常是 `~/.codex/skills/script-visual-director`；若配置了 `CODEX_HOME`，则位于该目录的 `skills/` 下。确保 `SKILL.md` 直接位于 skill 文件夹根部，保留 `scripts/`、`assets/`、`references/` 等配套目录。确认 Codex 能发现后，可用 `$script-visual-director` 调用。

**Skill 仓库和制作项目是两个目录。** 建议把制作项目放在仓库之外；若放仓库内，请放在已忽略的 `outputs/` 中。代码、模板和示例应进入 Git；具体剧本、图片、预演文件和用户确认记录单独保存。

## 3. 一次完整制作的顺序

| 阶段 | 产物与检查 | 用户操作 |
|---|---|---|
| 目标与剧情 | 确定视频系统、模式、画幅；分析节拍、紧张度、心理与必要改编 | 确认剧情分析 |
| 导演分镜 | 景别、机位、动作起止、运镜、心理、可见表演、逐句口气、节奏；目标文本与完整中文对照 | 修改或确认分镜 |
| 空间布局 | 平面图、物件尺寸、人物路线、机位与通行关系 | 确认布局 |
| 可选预演 | 后台 Blender 白模动画，检查动作、遮挡、路线与镜头覆盖 | 选择生成或跳过；生成后查看并确认 |
| 资产基准 | 按镜头需要整理人物、场景、关键道具需求并生成基准图 | 确认基准图 |
| 扩展资产 | 基于已确认基准生成角度、状态或细节变体 | 检查一致性，必要时修订 |
| 交接 | 绑定真实资产顺序与版本、适配目标输入、校验和打包 | 在目标机器进行实际导入测试 |

人物默认交付四张独立图：**颈部以下正视、含头部背视、含头部左侧视、头部特写**。四图共用人物基准，保持脸型、服装和身材一致。家庭角色依亲缘设计安排基准顺序，通常先确认父母，再据其特征设计子女。

台词逐句描述语气，例如慵懒、愤怒、害羞，同时交代音量、速度、停顿和情绪变化。描述声音不等于制作音频；本 skill 不生成配音、分镜首尾帧或最终 AI 视频。

同一对话中直接说“确认分镜”“确认布局”“继续预演”“同步修改”即可，不必每步重新调用 skill。普通“确认”只对应刚展示的明确对象；“继续”不代替对未知版本的确认。修改已确认内容后，受影响的分镜、布局或资产需要重新检查。

## 4. 网页审核与中文修改

Codex 建好制作项目并初始化审核数据后，在仓库根目录启动：

```sh
.venv/bin/python scripts/svd.py review-serve /实际路径/制作项目
```

打开终端返回的完整链接。服务只监听本机 `127.0.0.1`，端口和访问令牌自动生成。它不需要上传到 GitHub Pages。终端按 `Ctrl+C` 停止；重启后使用新链接，项目中已保存的数据仍在。

1. 查看分析和分镜，在左侧修改中文导演稿或时长，点击保存。
2. 旧系统文本保留作对照，并标记待同步；相关确认可能失效。
3. 返回 Codex 说“同步修改”。Codex 会理解修改、检查前后镜头和空间影响，更新目标文本与完整中文对照。
4. 刷新页面，检查同步结果和导演检查结论，再确认当前版本。

**网页保存不会自动翻译、调用 Codex 或启动 Blender。** 页面选择预演后，返回 Codex 说“继续预演”。预演页面默认显示状态与结果链接，点击后按需查看视频，不自动播放。

## 5. Blender 预演

布局确认后可以选择预演，也可以明确跳过。跳过会记录未验证的动态空间范围，不会标为预演检查通过。

检测本机 Blender：

```sh
.venv/bin/python scripts/svd.py previs-doctor
# 自动检测失败时，指定实际可执行文件，例如 macOS：
.venv/bin/python scripts/svd.py previs-doctor --blender /Applications/Blender.app/Contents/MacOS/Blender
```

选择生成后，Codex 根据本剧编写动画脚本、输入数据和镜头覆盖说明，再绑定任务。布局 JSON 本身不会自动生成合理的人物动作。

以下为高级命令顺序，路径必须替换为该项目的真实文件；不要复制示例确认文字来伪造用户批准：

```sh
.venv/bin/python scripts/svd.py previs-choice /实际路径/制作项目 generate --evidence '用户实际选择预演的原话'
.venv/bin/python scripts/svd.py previs-bind /实际路径/制作项目 previs/blender/build_previs.py --coverage /实际路径/覆盖范围.json
.venv/bin/python scripts/svd.py previs-run /实际路径/制作项目 --mode smoke
# 查看诊断帧、处理问题后再完整渲染：
.venv/bin/python scripts/svd.py previs-run /实际路径/制作项目 --mode render
.venv/bin/python scripts/svd.py previs-check /实际路径/制作项目 previs/runs/实际运行编号 --note '实际观看后的检查结论'
```

有问题时检查命令增加 `--reject`。修订影响已确认机位或布局的内容，需要重新确认；修改动画输入后重新绑定并运行。检查通过后才提交用户确认预演。

每次运行保存到制作项目的 `previs/runs/时间-编号/`，保留日志、`.blend`、PNG 帧序列和 MP4。MP4 使用 H.264；当前工具可用 Blender 自带序列编辑器编码，不要求额外安装 FFmpeg CLI。

必须区分：少量诊断帧、部分关键片段和完整预演。预演只覆盖部分镜头时，明确范围；不能把 37 秒关键片段说成约 100 秒整集已完成。简化人偶未实现精确表情、口型、步态或手指接触时，应在检查结论中说明。

### 预演用于 H3 的当前边界

带俯视图、镜号和时间标注的对照 MP4 用于人工审核。作为 H3 输入时，需要另外提供纯摄影机画面，并按目标部署的参考视频数量、时长、分辨率等限制分段；角色外观与场景美术还需要已确认的真实参考图。

**v0.5 已实现逐镜审核版、逐镜纯摄影机参考候选与串联版导出；尚未完成 H3 特定部署的自动限长细分与另一台机器上的端到端验证。** 不要将审核视频直接标为 H3 可用交付。实际接入前核对 [H3 官方模型说明](https://huggingface.co/MiniMaxAI/MiniMax-H3) 和所用部署接口，再用一小段进行实测。其他视频系统同样按其实际接口适配。

### 逐镜预演文件

新任务设置 `job.json` 的 `delivery` 为 `per_shot_v1` 后，render 自动导出逐镜文件。已有当前任务的完整双视角帧序列可执行：

```sh
.venv/bin/python scripts/svd.py previs-export-shots /实际路径/制作项目 previs/runs/实际运行编号
```

每镜提供 `shots/镜号/review.mp4` 与 `reference.mp4`，另有串联审核版和纯摄影机版。网页按当前镜号显示该镜链接；输出目录的 README 列出全部镜头。文件保持原帧率和时长，导出不会补造缺镜，也不会自动确认。查看逐镜结果和串联节奏后，再完成检查与用户确认。

## 6. 资产生成、校验与交接

人物四图规格保持不变；场景图按 [预演到场景资产](references/scene-reference.md) 绑定已确认机位与几何结构，先确认美术基准再扩展所需方位。

前置确认齐备后，由 Codex 整理资产清单、调用可用图像工具、检查实际图片并登记。缺少生图工具时保存待办，不用提示词或白模冒充真实资产。

```sh
.venv/bin/python scripts/svd.py queue /实际路径/制作项目
.venv/bin/python scripts/svd.py validate /实际路径/制作项目
# 所有必要资料和确认齐备后：
.venv/bin/python scripts/svd.py validate /实际路径/制作项目 --strict
.venv/bin/python scripts/svd.py package /实际路径/制作项目 /实际路径/交接-v001.zip
# 仅交阶段成果、仍有待办时：
.venv/bin/python scripts/svd.py package /实际路径/制作项目 /实际路径/交接-draft-v001.zip --draft
```

普通 `validate` 可返回待办；`--strict` 要求错误和待办均为空。阶段包不能冒充正式完成。打包只包含索引登记的文件，不递归收集整个目录；动画辅助脚本等需要交付时必须纳入登记并检查压缩包内容。

`manifest.json` 是本项目的资产索引，不是 H3 原生任务，也不是可直接导入的 ComfyUI 工作流。绑定最终资产、逐段目标提示词和模型实际导入是后续交接工作；当前工具的报告保留 `target_h3_validated=false`。

## 7. 在另一台机器上测试或接续

**重新测试完整流程：** 克隆 skill 仓库，重新建立 `.venv`，按需安装 Blender，确认图片工具可用，然后指定一个新的制作项目目录，从剧本重新开始。旧测试资产不会随 Git 仓库自动出现。

**接续既有制作项目：** 另行复制完整制作项目目录，或使用已核对内容的阶段包。保留 `manifest.json`、`review/state.json`、已登记文档、图片、布局及需要的预演脚本与输入；迁移完整目录最适合继续开发预演。先停止旧机器审核服务，再复制稳定的数据；浏览器未保存的草稿不会随项目迁移。

在新机器告诉 Codex：

```text
请使用 /新机器/实际路径/script-visual-director/SKILL.md。
从 /新机器/实际路径/制作项目 恢复，先检查保存的状态和待办。
沿用仍然有效的确认，不重新初始化审核数据，也不直接开始批量生图。
```

启动新的 `review-serve`，使用新 URL；不要沿用旧机器的 localhost 链接。若要重新渲染，检查 Blender 路径与输入完整性。项目内部使用相对路径，但运行记录可能保留旧机器诊断路径，不能把历史运行路径当作新机器可执行配置。

## 8. 开发检查与示例

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python examples/make_demo.py outputs/planning-demo-01
.venv/bin/python scripts/svd.py validate outputs/planning-demo-01
```

示例输出目录必须是新的。示例只演示规划、平面布局和静态白模，不调用 AI 生图、不自动完成新版交互确认，也不证明完整视频流程通过。单元测试不能代替实际渲染、观看视频或 H3 导入测试。

## 9. 推送 GitHub

`.gitignore` 已排除虚拟环境、Python 缓存、本地环境变量文件、编辑器文件，以及仓库根目录下的 `outputs/`、`work/` 等运行产物。`assets/` 是工具模板与前端资源，必须提交；`requirements.lock`、示例、测试和技能说明也应提交。不要用忽略所有 PNG、MP4 或 JSON 的方式隐藏有效源码资源。

在尚未初始化 Git 的仓库根目录执行：

```sh
git init
git add .
git status --short
git diff --cached --stat
git commit -m "Add script visual director skill and operation manual"
git branch -M main
# 将下一行地址换成自己的真实仓库地址：
git remote add origin https://github.com/YOUR_ACCOUNT/script-visual-director.git
git push -u origin main
```

如果已有 Git 仓库或 `origin`，保留现有分支与远程设置，按正常提交流程处理，无需重复初始化或添加远程。`.gitignore` 不会取消已有文件的跟踪；若虚拟环境以前已进入 Git，检查后从索引移除相应目录，再提交。

推送前确认暂存区没有具体制作项目、访问令牌或本机配置。忽略规则只匹配已列出的路径；放在任意其他目录的私有剧本或图片不会自动被识别。

## 10. 生成分组与 AIMixer 导演包（v0.6）

在分镜阶段告诉 Codex 使用哪个导演台；未确定时选择通用适配。当前支持 `generic` 与 `aimixer-h3`。Codex 根据连续动作、反应、时长和输入限制提出分组；你可以在网页阅读组级中英稿、修改导演意图、成员镜号和衔接，并点击确认。保存修改后回 Codex 说“同步分组”。拆组或合组可直接在对话提出，Codex 一次更新完整方案。

一个镜头保留一份独立预演，一个生成组包含连续的一镜或多镜，并可导出组内串联版。每组镜头从0计时，保留原整集时间。原分镜或分组改变会使旧提示词和确认失效；换适配器保留中文、镜号和资产文件，重新编译交付格式。

```sh
# Codex 编写与同步方案后可检查：
.venv/bin/python scripts/svd.py groups-check /实际路径/制作项目
# 从当前逐镜导出生成各组视频，缺镜组会列出待办：
.venv/bin/python scripts/svd.py groups-previs /实际路径/制作项目 previs/runs/RUN/exports/EXPORT/index.json
# 素材与确认全部就绪后：
.venv/bin/python scripts/svd.py groups-package /实际路径/制作项目 /实际路径/导演交接-v001.mmxpack.zip
# 阶段草稿：
.venv/bin/python scripts/svd.py groups-package /实际路径/制作项目 /实际路径/导演交接-draft-v001.mmxpack.zip --draft
```

在 AIMixer 导演台中使用“导入导演包”打开 `.mmxpack.zip`，查看公共参考图片、各素材组的提示词和对应预演。导入动作会按目标工具提示替换该节点时间轴。中文对照、镜号映射和交付状态保存在 ZIP 的 `extra/`；不是塞进模型提示词。格式已对接不代表模型生成已验证，正式/草稿包都会明确保留实际验证状态。

AIMixer 导出使用 r2v、24fps 与默认画布864×480，按17k+5帧对齐并报告增加的尾部时长；段间引导默认关闭。导入后依目标机器调整画布、采样和衔接设置。每组独立检查参考数量与视频时长，多个组批量运行也不突破单组限制。当前不自动切分超限组，不生成配音或最终视频。

完整协议与 JSON 字段见 [生成分组](references/generation-groups.md)。

## 11. 详细规范入口

- [技能入口](SKILL.md)：Codex 的执行顺序与完成标准。
- [项目设计](PROJECT_DESIGN.md)：整体设计与数据流。
- [操作与数据约定](references/asset-schema.md)：资产登记、依赖、修订和确认。
- [交互审核](references/interactive-review.md)：中文同步、版本和迁移。
- [导演检查](references/director-review.md)：节奏、心理、表演与逐句语气。
- [本地预演](references/local-previs.md)：动画适配协议、绑定和检查。
- [人物四图](references/character-reference.md)：人物资产规格。
- [生成分组](references/generation-groups.md)：跨工具分组、组预演与导演包导出。
- [H3 交接](references/h3-handoff.md)：目标格式与交付边界。
