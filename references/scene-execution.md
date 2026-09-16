# 导演稿到可执行场面计划 v1

在需要整场白模时读取。模型根据中文导演稿与已确认布局编写 `scene-plan.json`；Python 不从关键词生成表演，也不把剧情示例固化为动作模板。该文件是内部协议，不是 H3 提示词。

## 可用入口

```bash
.venv/bin/python scripts/svd.py scene-compile PROJECT/scene-plan.json PROJECT/compiled-plan.json
.venv/bin/python scripts/svd.py scene-diff OLD_PLAN.json NEW_PLAN.json
.venv/bin/python scripts/svd.py scene-build PROJECT/scene-plan.json NEW_OUTPUT --render
# 生产项目沿用已确认布局和已有审阅页：
.venv/bin/python scripts/svd.py scene-bind PROJECT scene-plan.json --layout layout.json
.venv/bin/python scripts/svd.py blocking-run PROJECT --mode smoke
.venv/bin/python scripts/svd.py blocking-run PROJECT --mode render
```

scene-build 是隔离测试入口，不登记生产批准。模型锁文件须位于输入计划同级目录；scene-bind 从 PROJECT 读取锁文件。生产须先确认布局并记录用户选择生成白模，不能通过新入口绕过阶段。构建输出包含计划、锁定资产、执行器副本、scene.blend、诊断图、检查报告、index.html；--render 在检查未失败时编码 MP4。partial 只表示已实现检查未发现问题，不代表动作合格。

## 输入协议

完整 JSON Schema 位于 `assets/scene-plan.schema.json`，权威运行校验在 scripts/scene_plan.py。顶层字段：schema_version=1、fps、duration、scene、actors、anchors、actions、cameras、contacts。scene 复用组件场景协议；fps/frames 由场面时间轴统一确定。坐标为米，Z 上、人物前方 -Y，角度为度。

- actors：id 对应 scene 中已锁定的 asset 人物；adapter 当前仅支持 snow-v3、blender-snow@3、CH-snow。不得把其他模型改名当已适配角色。
- actions：id、object、kind、intent、origin(explicit/inferred/proposed)、start、duration；可加 from_state/to_state。start 为 `{at: 秒}` 或 `{after: 行动ID, offset: 非负秒}`，after 指行动结束。依赖环、时间越界、同对象重叠、状态冲突会拒绝。
- **hold** 保持此前已确定的姿态；人物不能以未定义模型默认姿态开始 hold。
- **object_motion** 支持非人物道具的 end_position / end_angle，线性变化。不能移动人物代理来冒充跑步；与既有关键帧或动态物理冲突会拒绝。
- **rig_pose** 执行已经设计/适配好的姿态 samples。每个 sample 含 time、position(人物根节点世界坐标)、rotation(根节点 XYZ)、targets。四个 targets 为 hand.L/R、foot.L/R，各含 position、rotation、pole；均在人物根节点局部坐标。rotation 指真实控制骨变换，不是脚掌表面的欧拉角；须依据绑定校准，不能猜。时间从 0 到动作 duration；位置线性插值、旋转四元数插值；连续轨迹端点不一致则拒绝，需提供过渡动作。当前不自动生成接触感知混合或步态。
- 未实现的 kind（包括直接填写 walk、run、dive_slide）返回 blocked 和具体行动编号，不降级为平移或默认动画。动作片段自动检索、FBX 自动重定向、通用运动匹配库尚未实现。
- anchors：id、object、offset、rotation，随父物体世界变换；contacts：actor、effector、anchor、start、duration。接触通过目标位置与朝向约束；pole 仍由轨迹提供，不保证任意目标可达。当前检查使用固定的 3.5cm 肢端到达阈值，尚无脚掌滚动及完整接触物理。
- cameras：id、target、offset、target_offset、lens、follow、start、duration。target_offset 在目标局部空间，offset 在世界空间。follow=true 跟随目标；false 固定在该段开始时的机位与朝向。按计划切换摄像机参数，时间轴必须连续覆盖全段。当前尚无自动景别求解、银幕位置约束和摄影机避障；不可把未经实现的摄影字段塞入计划。

所有输入字段严格校验，未知字段拒绝而不是忽略。最后一帧落到该动作终点；渲染帧数等于 fps×duration。不同对象可以并行；不会因碰撞擅自调整导演给定事件时间。

## 骨架与回放检查

Snow 适配器保留驱动器，只解除旧 action/NLA，禁用嵌入脚本自动运行。四肢目标通过真实 IK 控制器执行，禁用 IK 拉伸。保存后重新载入检查：实际腕/踝是否到达目标、膝盖弯曲平面是否与角色标定前向冲突、过度屈膝、驱动器失效。膝向以角色坐标系为依据，不采用固定世界 Z 判断，避免人物趴下后判断颠倒。该启发式适用于此绑定，不能宣称通用人体解剖验证。

摄影机检查目标点是否在画面内、视线射线遮挡和是否处在组件盒体中；不是完整主体包围盒构图分析，故意遮挡的镜头目前需人工修改计划/专门执行器，不会自动放行。现有组件碰撞检查仍执行；导入模型完整网格碰撞、自碰撞、支撑平衡、足掌滚动和动作自然性未覆盖，报告保留 partial。

网页列出具体问题和诊断图。空间、摄影机、动作三种参考资格初始均 unreviewed，编译和渲染不会自动改为 approved，不自动送 H3。用于检查空间的白模不等于可供 H3 模仿的表演。

## 变更依赖

scene-diff 根据规范化数据指纹返回 changed / invalidate：空间变化影响动画与摄影机；动画变化影响摄影机；镜头变化不要求改动画数据；均使检查、渲染和审阅过期。当前仅计算影响范围，尚未实现自动部分缓存重建，scene-build 仍输出新版本、完整重建。锁定模型由现有库校验，改变模型须重新绑定并审阅。


## 验证命令

`PYTHONPATH=scripts .venv/bin/python -m unittest discover -s tests` 验证编译、依赖与生产确认门槛。
真实绑定回归需本机已下载 Snow：

```bash
blender --background --factory-startup --disable-autoexec --python-exit-code 1 \
  --python tests/blender_scene_plan_check.py -- \
  --model .model-cache/blender-snow/3/files/snow_v03.blend --out NEW_TEST_DIRECTORY
```

它在独立目录检查转向后的正常屈膝与故意反折负例；不是导演样片，也不登记生产批准。
