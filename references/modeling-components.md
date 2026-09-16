# 可复用白模组件 v1

用于已确认中文导演稿和平面图之后的调度白模。组件提供可编辑的结构与骨架，不替代导演设计，也不自动从文本推断完整动作。依据当前情节选择必要精度，不把某个故事的抓握点、路线或机关写成通用规定。

## 现有能力与边界

- `box`：结构或道具；`wall_opening`：由实体墙段构成真实洞口；`stairs`：真实阶高、踏面；`door`：以铰链为原点转动的门板。
- `actor`：默认蓝色的标准比例分节代理人物，含手掌、分开的四指与拇指，以及踝部、足跟、前脚掌和趾端；真实 Blender 骨骼、四肢双骨 IK、膝肘 pole 控制点。高度可配；尚不支持写实角色拓扑、面部、服装、自动步态、手指抓握或足掌姿态锁定。
- `anchor` 与 `contacts`：在指定帧段把手腕或踝部 IK 目标固定于独立世界坐标接触点。锁踝部位置不等于足掌完整贴地；需逐帧看支撑、膝向和脚掌姿态。目标不可达会报告，不拉长肢体补偿。
- `attachments`：简单道具随实际肢端变换；offset 是肢端局部坐标。与刚体、独立道具动画互斥，避免多套驱动争抢。
- `physics`：none/static/dynamic/kinematic。首版动态仅独立 box；门等导演驱动结构用 kinematic。动态场景缓存刚体结果供检查和渲染复用。人物是导演控制骨骼，不是刚体角色控制器。
- `model-check.json`：逐帧和子帧检查肢体、躯干、头部胶囊代理与定向盒体；前臂/小腿与躯干/头的部分自碰撞；IK 到达误差和接触误差。报告具体对象、部位、最早帧、最坏误差。

检查不覆盖完整网格、人物之间碰撞、手指、衣服、所有肢体对，也不自动避障或保证快速运动绝不漏检。`passed` 仅表示该检查范围无超差，始终 `user_approved=false`。允许接触必须限制到人物、部位、物体、帧范围和小幅容差；不能全局忽略穿插。

## 使用方式

先由助手按已确认平面图编写项目内 `model-scene.json`，结构由 `scripts/modeling.py` 的 `SPEC` 严格校验。建模构件以米为单位，Z 向上；人物正面为 -Y。box.position 是中心，墙/台阶是底部原点，门是左铰链底端。rotation_z/angle 使用角度；人物 targets 使用人物根节点局部坐标米，不随 height 自动缩放。锚点为世界坐标。

```bash
.venv/bin/python scripts/svd.py model-validate PROJECT/model-scene.json
.venv/bin/python scripts/svd.py model-build PROJECT/model-scene.json NEW_OUTPUT_DIRECTORY
```

独立构建生成 `.blend`、`preview.png`、`model-check.json`、输入和脚本副本。输出目录必须是新目录，检查失败退出码为 1，仍保留诊断图；Blender 执行失败为 2。它不登记生产项目确认。

整场白模沿用现有审核流程：

```bash
# 用户已经选择生成白模、平面图已确认后：
.venv/bin/python scripts/svd.py model-bind PROJECT model-scene.json --layout layout.json
.venv/bin/python scripts/svd.py blocking-run PROJECT --mode smoke
# 查看诊断帧、报告、修正后再完整渲染：
.venv/bin/python scripts/svd.py blocking-run PROJECT --mode render
```

`model-bind` 复制当前组件代码、场景、布局到项目内版本目录并登记指纹。修改场景后重新绑定，旧版本保留。布局指纹证明版本一致，不证明场景几何自动匹配平面图：需要对照核查尺寸、方位、洞口、物体位置。完整 MP4 实际检查后，执行 `blocking-check` 并提交用户确认；构建或检查不代替用户确认。白模与最终分镜、逐镜参考的关系见 [流程](layout-first-workflow.md)。

## 场景规范示意（不是叙事模板）

```json
{
  "schema_version": 1,
  "fps": 12,
  "frames": 12,
  "components": [
    {"id":"person","type":"actor","position":[0,0,0],"height":1.75},
    {"id":"floor","type":"box","position":[0,0,-0.1],"size":[6,6,0.2]},
    {"id":"support","type":"anchor","position":[-0.105,0,0.09]}
  ],
  "contacts": [
    {"actor":"person","effector":"foot.L","target":"support","start":1,"end":12}
  ],
  "beats": [
    {"id":"beat01","duration":1,"action":"保持站立","start_state":"双脚着地","end_state":"双脚着地"}
  ]
}
```

`keys` 包含 frame、可选 position/angle/targets；effector 为 hand.L/R、foot.L/R；对应 pole 目标名追加 `/pole`。同一肢端接触帧段不能重叠。beats 是整场行动段，时长总计等于 frames/fps，各段落在整数帧；不是最终镜头号，也不受单个 H3 视频任务时长限制。

根据镜头需要继续扩展新的通用构件。若某段需要复杂攀爬、软体、精细抓握或自然行走，需编写专门动画/导入合适资产并实际验证，不能声称首版组件已自动解决。

## 验证

普通测试：`PYTHONPATH=scripts .venv/bin/python -m unittest discover -s tests`。
真实 Blender 检查：`blender --background --factory-startup --python-exit-code 1 --python tests/blender_modeling_check.py`，覆盖默认骨架、穿插拒绝、不可达接触、移动根节点接触及持物绑定。使用独立测试场景，不确认真实生产资产。

手部随前臂骨骼运动；脚部位置跟随实际踝点，朝向独立跟随人物根节点，避免腿部 IK 扭转把脚尖带偏。尚未增加独立手指关节、脚掌滚动或坡面贴合控制；现有穿插检查仍不覆盖这些末端网格。人物材质同时设置视口颜色与渲染节点颜色，保证渲染视频中为蓝色。


需要成熟人物或现成物件时，优先使用 [三维资产库](model-library.md) 与 type=asset。基础 actor 保留为调度粗代理。导入模型的碰撞与统一 IK 适配未完成时报告 partial，不能把没有代理的模型当作检查通过。
