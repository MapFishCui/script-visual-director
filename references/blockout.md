# 可编辑三维白模

三维白模使用布局中的长方体几何与摄像机；实现直接导出自包含 glTF 2.0，嵌入网格缓冲，不依赖本机 Blender。实际空间由可编辑网格构成，不能用生图模型画“白模风格图”替代。

```sh
.venv/bin/python scripts/svd.py blockout PROJECT spatial/LOC_001/layout-v001.json
```

先运行 render-layout 注册该版本。输出：

- `spatial/LOC_001/v001/blockout/scene.gltf`：真实几何、法线、白色材质、摄像机和场景单位。
- 各机位 PNG：CPU 深度缓冲渲染的白模检查预览。
- `blockout-check.json`：连续线段与旋转长方体的碰撞／目标点遮挡检查，人工检查状态仍为 pending。

坐标从布局 `[x,y,z]` 映射为 glTF `[x,z,-y]`，保持米制和右手坐标。摄像机朝向通过节点矩阵保存，观察方向为局部 -Z。对象可以在支持 glTF 的三维编辑器中分别选择；布局 JSON 是重建来源。

白模仅表示长方体近似。楼梯可用多个台阶表达，门窗由墙段真实留洞；曲面、柔性形变、角色骨骼、复杂光照和门扇动态扫掠未实现。摄像机路径保存在 extras 元数据；当前导出静态机位和预览，不导出运镜动画。需要多位置检查时增加关键位置机位，不声称已完整验证整段动画构图。

PNG 预览辅助观察，不替代模型导入后的专业检查。检查几何近似、机位、遮挡及可执行性后，才可执行：

```sh
.venv/bin/python scripts/svd.py review-layout PROJECT LOC_001 --blockout --note '已检查几何机位预览与布局对应关系；记录剩余限制。'
```

需要白模的布局将 `blockout_required` 设为 true；生成白模本身不等于通过检查。复杂要求超出实现时，将该镜头保持待验证，继续其他独立工作。H3 是否接收白模图由具体下游工作流验证，默认只交付为规划资料。

格式依据：[Khronos glTF 2.0 规范](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html)。


## 动态阶段与跳过

用户选择生成时，按 [本地预演](local-previs.md) 在 Blender 后台驱动人物、运镜与物件状态，生成同步对照 MP4；blockout 命令本身仍是静态工具。用户可明确跳过白模预演，记录未验证范围后进入资产流程，不把未检查的模型改成 passed。
