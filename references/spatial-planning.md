# 场景平面布局

多机位、人物走位、重要遮挡或多角度场景应建平面图。简单单视角可省略，写明理由。先拟布局和镜头，再互相校验；场景资产依赖稳定且检查过的布局版本。

数据范例：`examples/living-room.layout.json`。精确字段由 `scripts/schema.py` 的 LAYOUT 定义，禁止默默忽略未知字段。

## 坐标与结构

- 单位固定米。`center`、机位与路径点为 `[x,y,z]`：x 平面向右，y 平面向上，z 高度。平面原点在图的左下方；不代表现实方位。
- `size=[宽,深,高]`，均为正数。`rotation` 是绕高度轴从平面 +x 朝 +y 逆时针的角度。
- `boxes` 用长方体表达墙、家具、道具、门窗、人物和光源。`solid` 决定碰撞与遮挡检查；标签不决定是否阻挡。
- 门窗必须真实留出洞口：墙拆成洞口两侧、窗下和过梁等段。仅在完整墙上叠一个门窗符号不会产生洞口。开门可用旋转的门板表达，另一状态应单独建版本或场景状态，不声称已验证门扇扫掠体。
- 未知尺寸、灯具高度等以 `source.basis=proposed` 并在 `assumptions` 中记录；已有测量不改成猜测。
- `cameras` 含 position、target、竖直视场角 yfov（度）、aspect（宽/高）、路径 path 和 shot；路径由初始机位接续各点。
- `paths` 是人物脚底轨迹，含 actor、shot、points、水平 clearance。当前碰撞检查采用 1.7m 人物高度，特殊身高或动作需人工核对。

## 运行

先把布局 JSON 放进资产项目，例如 `spatial/LOC_001/layout-v001.json`，然后执行：

```sh
.venv/bin/python scripts/svd.py render-layout PROJECT spatial/LOC_001/layout-v001.json
.venv/bin/python scripts/svd.py check-layout PROJECT/spatial/LOC_001/layout-v001.json
```

工具生成版本目录下的 `floor-plan.svg/png`、各机位 SVG/PNG、检查报告和内容指纹，并登记到 manifest.layouts。重新导出同一数据允许；更改数据必须增加布局版本，并使用新的布局 JSON 路径。机位图将基础布局与当前镜头标注组合，避免全部路线堆叠。

查看 PNG，检查标签、比例、关键物件和路线；需要编辑时优先修改 JSON 后重新绘制，避免 SVG 与数据分离。`--font` 或 `SVD_FONT` 可指定中文字体；缺字体应明确处理，不能交付乱码标注。

确认检查范围、记录未解问题后，执行：

```sh
.venv/bin/python scripts/svd.py review-layout PROJECT LOC_001 --note '已查看布局与两个机位，门口路线通畅；机位遮挡符合剧情。'
```

这个命令记录 Codex 的视觉检查，不是额外要求用户批准。自动碰撞报告不会自动写成“人工检查通过”。检测到实体相交可能是有意遮挡，应结合原文解释，而不是机械移走物体。

平面布局不能证明复杂高度、真实物体形状、门扇扫掠、读字清晰度和叙事合理性。需要时转到 [白模](blockout.md)。布局更新后工具标记直接依赖资产失效；继续检查间接依赖、修改 shots.layout 和新版本依赖，不直接清除 stale。
