# 九宫格交付、逐项确认与跨集复用

命令以 `.venv/bin/python scripts/svd.py grid` 为统一入口，`scripts/grid_workflow.py` 仍可直接调用。下文 PROJECT 为制作目录；文件路径均相对 PROJECT，外部输入方案路径按当前命令目录解释。不要将测试依据复制为生产批准。

## 项目清单

新完整项目在写导演稿时规划 `grid-delivery.json`，与 `director.md` 一起登记。清单列出未来文件路径，不要求此时图片已生成。示例为一个人物和一个任务：

```json
{
  "schema_version": 1,
  "director": "director.md",
  "characters": [{
    "id": "C1", "version": 1,
    "views": {
      "front": "characters/C1/front.png",
      "back": "characters/C1/back.png",
      "left": "characters/C1/left.png",
      "head": "characters/C1/head.png",
      "sheet": "characters/C1/sheet.png"
    },
    "source": "characters/C1/source.json"
  }],
  "tasks": [{
    "id": "T1", "duration": 5, "characters": {"C1": 1},
    "grid": "tasks/T1/grid.png",
    "panel_map": "tasks/T1/panel-map.json",
    "prompt_spec": "tasks/T1/spec.json",
    "prompt": "tasks/T1/prompt.json",
    "references": [
      {"label": "<Picture 1>", "path": "characters/C1/sheet.png", "roles": ["appearance"]},
      {"label": "<Picture 2>", "path": "tasks/T1/grid.png", "roles": ["composition"]}
    ]
  }]
}
```

无人物时 `characters` 使用空列表、增加 `no_characters` 指向说明文件；任务 `characters` 使用空对象。逐项模式将说明登记为人物项 `NONE`，九宫格用 `--depends NONE`。不能凭空生成角色补阶段。

人物来源文件记录生成工具、提示词、引用的真实基准与版本、检查结果；继承时工具会写入共享库快照、版本和本集连续性说明。四图和合图必须为五个独立可读图片文件；它们是否满足构图和身份一致性仍需实际查看。

## 逐项登记与确认

```sh
.venv/bin/python scripts/svd.py grid init PROJECT
.venv/bin/python scripts/svd.py grid register PROJECT --stage director --files director.md grid-delivery.json
# 展示后，使用真实用户原话确认导演稿；之后才能登记下游。
.venv/bin/python scripts/svd.py grid confirm PROJECT --stage director --evidence '本次真实用户确认原话'

.venv/bin/python scripts/svd.py grid register-item PROJECT --stage characters --item C1 --files characters/C1/front.png characters/C1/back.png characters/C1/left.png characters/C1/head.png characters/C1/sheet.png characters/C1/source.json
.venv/bin/python scripts/svd.py grid confirm-item PROJECT --stage characters --item C1 --evidence '本次真实用户确认原话'

.venv/bin/python scripts/svd.py grid register-item PROJECT --stage grids --item T1 --depends C1 --files tasks/T1/grid.png tasks/T1/panel-map.json
.venv/bin/python scripts/svd.py grid confirm-item PROJECT --stage grids --item T1 --evidence '本次真实用户确认原话'

.venv/bin/python scripts/svd.py grid register-item PROJECT --stage prompts --item T1 --files tasks/T1/spec.json tasks/T1/prompt.json
.venv/bin/python scripts/svd.py grid confirm-item PROJECT --stage prompts --item T1 --evidence '本次真实用户确认原话'
```

人物基准仍先实际展示并确认，再扩展四图；完整图套登记不代替这个创作步骤。多人物任务在 `--depends` 后列出实际引用的所有人物编号。提示词自动依赖同编号九宫格。可先完成 T1 的图和文本，再继续 T2；无需等待全部九宫格制作完成。

网页自动显示逐项确认和意见按钮。修改意见可用 `feedback-item --stage grids --item T1 --evidence '实际意见'` 登记。重新登记增加该项版本，即使文件内容相同也不复用旧批准；下游依赖重新登记后才能确认。改变 C1 只影响实际使用 C1 的任务，改变 T1 只影响 T1 的提示词。导演稿和任务规划变动仍影响全项目。

已有整体登记的阶段继续使用 `register/confirm`；程序拒绝静默转成逐项模式，不丢弃既有文件或确认。需要逐项生产时从新项目规划。状态历史保留前一版记录，不自动复制旧图片；修订原图仍须另存版本。

## 九格时间与提示词

`panel-map.json` 包含 `task_id`、`duration`、与清单相同的 `characters`，以及恰好九个 `panels`。每项为：

```json
{"panel": 1, "time_seconds": 0, "shot_id": "S1", "description": "完整可见画面描述", "transition": "continuous"}
```

panel 必须依次为 1–9。时间为任务内有限数、非递减且不超时长；同一时刻的重复格，上一格用 `hold`。`transition` 描述到下一格的连接，取 `continuous/cut/hold`。换镜时上一格标 `cut`，新镜第一格对齐提示词的切点。所有镜头至少被一格覆盖；格子可描述同一动作的渐变，不能为凑数加戏。

`spec.json` 使用 [H3 编译器协议](h3-compiler.md)，镜头可增加 `id` 与 panel-map 对应；未给 id 时默认 S1、S2 等。`labels` 与清单 references 必须顺序一致；`media` 为 references 对应的 `label/type=image/roles` 列表，不包含 path。任务只绑定本段九宫格与实际使用的人物合图，按这个顺序生成 `<Picture N>`；不使用首尾帧槽。

```sh
.venv/bin/python scripts/h3.py PROJECT/tasks/T1/spec.json PROJECT/tasks/T1/prompt.json
```

编译输出同时包含系统文本与中文对照。登记 spec 和输出；修改任一输入后重新编译。校验会重新编译并比较保存的两份文本，不接受只改英文、留下旧中文。

## 完整性与交付

```sh
.venv/bin/python scripts/svd.py grid validate PROJECT
.venv/bin/python scripts/svd.py grid package PROJECT --output /交付目录/v001.zip
.venv/bin/python scripts/svd.py grid package PROJECT --adapter aimixer-h3 --output /交付目录/v001.mmxpack.zip
```

`validate` 将 `errors`（材料或结构错误）与 `pending`（未确认、过期、待修改）分开，任一非空返回失败退出码。`status` 仍只是进度记录，四阶段 confirmed 不等于完整交付。

正式包要求两类问题均为空；`--draft` 仅放宽确认条件，不放宽图片、时间、槽位等结构要求。拒绝覆盖已有包；导出再次核对输入文件，避免打包期间混入新版本。原生包一个任务一个 asset_group，所有参考图为任务内自足槽位。帧数沿用现有 AIMixer 适配规则；实际采样时长和效果仍需目标环境测试。

`project/` 保存全部已登记原件、grid-workflow.json 和清单；`tasks/` 提供可读双语提示词；`extra/bindings.json` 保存真实文件映射；`extra/delivery.json` 保存时长、哈希、待办和 `target_h3_validated=false`。恢复时只取 `project/` 目录，在新机器启动审核服务。

当前自动导出限本项目 Ref2VA 图片参考任务；其他视频模型、音视频混合任务沿用对应适配规范，不能伪装为已支持。图片内容的九格数量、视觉一致性和真实生成效果不由结构校验证明。

## 跨集人物套件

沿用现有共享库与 series 命令，按 grid-workflow.json 自动识别新流程：

```sh
.venv/bin/python scripts/svd.py series-init LIBRARY --name '剧集名称'
.venv/bin/python scripts/svd.py series-publish EP01 LIBRARY --episode EP01 --assets C1,C2
.venv/bin/python scripts/svd.py series-list LIBRARY
.venv/bin/python scripts/svd.py series-inherit EP02 LIBRARY inherit.json
.venv/bin/python scripts/svd.py series-check EP02
```

入库需要导演稿、清单和所选人物当前版本已确认，不要求其他任务完成。保存四张原图、合图、来源记录及确认快照；同快照重复入库复用版本，不能覆盖旧文件。旧流程共享版本为单图，新版本为完整人物套件，工具会拒绝混用。

EP02 先确认本集导演稿和清单，声明目标人物和空闲素材路径，然后使用：

```json
{
  "episode": "EP02",
  "items": [{"source_id": "C1", "version": 1, "target_id": "C1", "continuity_note": "本集与上集同一天、同一服装，沿用确切外观版本。"}]
}
```

version 为共享库版本，清单中的人物 version 为本集版本，两者不必相同。继承复制真实文件并登记为本集待审核项；不自动批准下游、不覆盖已有文件。来源记录携带原始快照和文件哈希，离开共享库后仍能验证。换装和其他实质变化按新版本制作，不直接覆盖已继承图片。当前新流程自动复用限人物套件，场景和道具仍按本集实际需要人工复用并登记。
