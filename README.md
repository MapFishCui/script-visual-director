# Script Visual Director · 操作手册

将剧本转为剧情与角色心理分析、中文导演分镜、目标系统文本及中文对照、空间布局，以及角色、场景和道具参考资产。默认用 Blender 建立场景、互动道具和简化人物的连续走位预演，向视频模型提供空间、遮挡和运镜参考。

这是一个 **通用 Skill 加本地 Python 工具**。助手 负责理解剧本、导演设计和目标格式适配；Python 负责数据、审核页面、依赖校验与打包；图片需要实际可用的图像生成工具。只执行 Python 命令不会自动写完分镜或生成图片。

## 1. 环境与安装

- Python 3.9 或更高，始终使用项目虚拟环境。
- 可读取本项目的助手环境；制作真实图片时需要可用的图像生成能力。
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

## 2. 在支持本地 Skill 的助手中使用

最直接的方式是在对话中给出本机 `SKILL.md` 的绝对路径，让助手读取并按它执行。将下例路径换成新机器的实际位置：

```text
请使用 /实际路径/script-visual-director/SKILL.md。
资产输出目录：/实际路径/productions/雨夜来客-test-01。
目标：MiniMax-H3，具体部署方式是……，16:9，时长按剧情合理安排。
风格：电影写实。
先确认中文导演稿，再确认人物基准和四视图合图。
然后制作场景与互动道具，用简化人物做连续走位和摄影机预演。
配合人物外观参考，编写动作提示词与中文对照；九宫格和 Kimodo 按需使用。
剧本：……
```

也可将完整仓库放入所用平台的 skill 目录。以 Codex 为例，通常是 `~/.codex/skills/script-visual-director`；若配置了 `CODEX_HOME`，则位于该目录的 `skills/` 下。确保 `SKILL.md` 直接位于 skill 文件夹根部，保留 `scripts/`、`assets/`、`references/` 等配套目录。其他平台按其技能安装与调用方式使用，不假定同样的目录或调用语法。`agents/openai.yaml` 仅供 Codex 展示与发现使用，不是核心运行依赖。

**Skill 仓库和制作项目是两个目录。** 建议把制作项目放在仓库之外；若放仓库内，请放在已忽略的 `outputs/` 中。代码、模板和示例应进入 Git；具体剧本、图片、预演文件和用户确认记录单独保存。

### 按需制作，不必跑全流程

可以直接这样调用：

```text
$script-visual-director 只生成一张人物参考图：……
$script-visual-director 用这两张参考图，只写 MiniMax-H3 提示词，带中文对照：……
$script-visual-director 生成这个情节需要的参考图和 H3 提示词，不做平面图和白模：……
```

单项任务直接在对话交付图片和文本，文件保存到输出目录；不要求先建完整审核项目。完整人物资产默认四张独立图，明确指定一张则只做一张。H3 仍按实际素材选择模式并检查格式与绑定；未做白模或实际视频测试会如实说明。回复“确认／继续”只延续当前范围。详见 references/on-demand-delivery.md。

## 3. 默认制作顺序：空间预演参考

中文导演稿 → 场景与道具 → 简化人物站位和走位 → 摄影机连续预演 → 人物外观参考与动作提示词 → 文件交付。详见 [空间预演参考流程](references/spatial-reference-workflow.md)。普通走位允许圆柱身体加球头；镜头需要手脚接触时用关节人偶，精确表演才使用成熟绑定或 Kimodo。场景细节按入镜和互动需要分配，不要求全场高精建模。

此新默认是创作与交付协议，可用现有 Blender 组件和项目内脚本执行；尚未新增专用审核网页或自动视频模型调用。下面的 grid 命令只适用于选用九宫格的项目，不要求新流程创建九宫格。

### 可选：九宫格关键画面

中文导演稿 → 人物基准与四视图合图 → 每段九宫格完整关键画面 → H3提示词与中文对照 → 文件交付。平面图和白模按需使用，不是必经阶段。每格包含完整的人物、环境、动作与光影，九格不等于九个镜头。人物图提供身份参考，九宫格提供视频画面参考，二者都不是硬锁定。

使用 `scripts/grid_workflow.py` 记录四阶段确认与文件版本，并生成统一进度页面。执行方法、检查要求和当前手动导入边界见 [九宫格流程](references/keyframe-grid-workflow.md)。下文旧review命令与打包器仍供既有项目使用，不用于新模式伪造旧阶段批准。

### 九宫格审核网页

在 skill 仓库根目录运行（替换为实际制作项目路径）：

```sh
.venv/bin/python scripts/grid_workflow.py serve /实际路径/九宫格制作项目
```

项目需先通过 `grid_workflow.py init` 初始化；生成的真实文件再按阶段登记。打开命令输出的完整带token链接，不能直接双击静态index.html来编辑。Windows使用 `.venv/Scripts/python.exe`。停止服务用Ctrl+C，重启后使用新链接，已保存资料保留。

页面可编辑中文导演稿、查看人物图和九宫格、阅读提示词与中文对照、提交修改意见并确认阶段。每3秒检查更新，有未保存输入时提示而不覆盖；旧页面版本不能覆盖新成果。修改上游会撤销下游确认，修改意见处理并重新登记后才能再次批准。保存／确认后回当前对话继续，页面不会自动生图或调用H3。

新流程支持通用 ZIP 和 AIMixer 导演台格式包导出；格式检查不代表目标视频采样通过。旧项目继续使用 review-serve，不自动迁移。

## 4. 校验、交付和跨集复用

选择九宫格的完整项目维护 `grid-delivery.json`，与中文导演稿一起登记；以人物编号和任务编号逐项记录素材、依赖和用户确认。已有整体登记项目保持兼容，不静默转换为逐项模式。完整数据示例与命令见 [九宫格交付与复用](references/grid-delivery.md)。

```sh
.venv/bin/python scripts/svd.py grid validate /实际制作项目
.venv/bin/python scripts/svd.py grid package /实际制作项目 --output /交付目录/v001.zip
.venv/bin/python scripts/svd.py grid package /实际制作项目 --adapter aimixer-h3 --output /交付目录/v001.mmxpack.zip
```

确认仅记录用户意见；`validate` 另外核对图片可读性、人物版本、九格编号和时间、镜号与切点、提示词及中文对照、素材槽位、逐项依赖和继承文件哈希。正式打包须同时满足完整性和当前版本确认。`--draft` 只允许缺少确认，仍不允许缺文件或错误映射。所有包保留 `target_h3_validated=false`；实际导入和视频效果仍需目标环境验证。

ZIP 内 `project/` 是可恢复制作目录，保留全部已登记原件、状态和交付清单。复制或解压到另一台机器后，在该目录重新启动审核服务。图像工具和 Blender 路径按新机器配置。

`series-publish` / `series-inherit` 自动识别九宫格项目，按完整人物四图、合图和来源记录处理。共享库锁定确切版本，不自动升级其他剧集；继承只创建本集待审核人物，不复制上集阶段批准。

## 5. 当前功能支持

| 能力 | 九宫格默认流程 | 原布局优先流程 |
|---|---|---|
| 中文稿、素材网页审阅 | 支持草稿撤销、冲突对照 | 支持 |
| 确认粒度 | 整体阶段；新项目可逐人物／任务 | 镜头与既有阶段 |
| 局部修改 | 逐项模式只影响相关依赖 | 沿用原依赖机制 |
| 完整性校验与通用包 | grid validate / package | validate / package |
| AIMixer 包 | grid package --adapter aimixer-h3 | groups-package / groups-bundle |
| 跨集复用 | 人物四图＋合图套件 | 人物／场景／道具单图 |
| 场景／道具跨集自动入库 | 暂未接入，按真实文件人工复用 | 支持，场景需本集空间检查 |
| 目标视频效果验证 | 尚未完成 | 尚未完成 |

旧项目的空间、白模、预演和导演组操作集中在 [旧流程操作手册](references/legacy-operations.md) 和 [旧执行协议](references/legacy-workflow.md)。

## 6. 开发验证

```sh
.venv/bin/python -m unittest discover -s tests -v
node --test tests/grid_frontend.test.js
```

前端事件回归需要 Node.js 18+，不属于生产运行依赖；Python 测试在找不到 Node 时明确跳过该项。真实导演台导入器契约测试需设置 `SVD_AIMIXER_SOURCE` 为本机源码目录。所有测试图片和确认依据均为隔离的合成夹具，不进入生产项目。

创作效果另按 [导演行为试题与观察记录](references/directing-evaluation.md) 检查。单元测试不证明导演质量，不代替实际观看图片和目标视频。

`.gitignore` 排除虚拟环境和运行产物。提交代码、资源、文档与测试；真实制作项目保存在仓库之外或已忽略的 outputs/ 中。
