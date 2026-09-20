# 下载、留存与复用三维资产

人物预演默认使用简化占位体：圆柱或胶囊身体加球形头部即可表达位置、身高、朝向和走位；需要坐姿、伸手或接触关系时升级为关节人偶。场景与道具按入镜、互动、遮挡和光影需要细化，允许自行建模、生成模型或导入有来源的资产。精确表演需要时才使用成熟绑定或 Kimodo，缺少人体模型不阻断普通空间预演。导入资产仍记录来源、许可和确切版本；代理人物不是最终外观资产，平移走位不是已完成的步态或表演。

##助手如何自行选用

1. 先 `library-list` 查询本机缓存与内置目录，按人物、道具、结构及剧情需要选择。需要新资源时用可用浏览工具查官方来源，不批量抓取整个网站。确认尺寸、复杂度、授权与用途适合再下载。
2. 可自动获取已核实的 CC0 或 CC-BY 4.0 免费资源。内置 Snow 来源为 Blender Studio。自选物件同样需真实下载地址及许可依据；需要购买、账户登录、授权不明或其他许可时先说明具体缺项，不把“免费下载”当可任意使用。
3. 下载是素材取得，不是质量通过。先列出 .blend 集合，选择实际角色或物件集合，生成预览；人物至少查看正面、侧面和当前动作需要的弯肘、屈膝、足底支撑、手部接触。明确尚未验证的动作；不能从一个 T-pose 推断所有动画正确。
4. 锁定具体版本到项目。项目复制依赖和署名，渲染 adapter 再复制使用版本并登记文件指纹。缓存和后续版本不得自动改变已确认项目。

## 持久缓存与命令

默认缓存为 `SKILL_ROOT/.model-cache/`，已被本仓库 .gitignore 排除；可设置 `SVD_MODEL_CACHE` 或每条命令 `--cache PATH` 使用其他磁盘。缓存是普通文件夹，重启会保留。可以保存多个独立版本。只在清理用户指定范围时删除，不能因“重跑剧情”连共享模型库一起清空。

```bash
.venv/bin/python scripts/svd.py library-list
.venv/bin/python scripts/svd.py library-fetch blender-snow
.venv/bin/python scripts/svd.py library-pin PROJECT blender-snow 3
.venv/bin/python scripts/svd.py library-check PROJECT
```

首次下载记录来源、作者、许可链接、署名、原包 SHA-256、各文件 SHA-256、版本及时间。已有缓存会校验后复用；损坏、同版本元数据改变或远端与项目锁定内容不一致时拒绝静默替换。下载中断不产生有效缓存。支持 ZIP 和单独模型文件，拒绝路径穿越、ZIP 符号链接与无模型的登录 HTML。

命令不会自行猜网上的许可或模型下载地址。对于不在目录里的资源，助手 核实后编写 descriptor：

```json
{
  "id":"vendor-prop", "version":"2026-09-16",
  "title":"实际物件名称", "author":"实际作者",
  "source_url":"https://供应方/实际作品页",
  "download_url":"https://供应方/实际文件.zip",
  "license":"CC0-1.0", "license_url":"https://creativecommons.org/publicdomain/zero/1.0/",
  "attribution":"实际来源与作者", "license_evidence":"实际查到的许可依据及核查日期"
}
```

这是字段示意，不是可用下载地址。`library-fetch vendor-prop --descriptor FILE` 下载；已知官方校验值可增加 `sha256`。当前自动许可集合刻意限定 CC0-1.0、CC-BY-4.0。贴图、bin 和外部资源必须包含在 ZIP 内；单个 glTF 引用的文件不会自动联网补齐。

## 检查与复用

```bash
# 不指定 collection 时，blend 检查只列出集合供选择。
.venv/bin/python scripts/svd.py library-inspect PROJECT blender-snow@3 snow_v03.blend NEW_INSPECTION_DIR --collection CH-snow
```

生成 inspection.json、蓝色 preview.png、preview.blend 和日志。记录骨架名称、骨名、资源边界、缺失贴图、无效驱动与嵌入脚本；始终不自动批准。导入运行禁用 embedded Python 自动执行；依赖自定义脚本的模型需单独检查适配，不能直接打开自动运行。

白模场景可添加组件：

```json
{
  "id":"lead", "type":"asset", "category":"actor",
  "asset_key":"blender-snow@3", "model":"snow_v03.blend", "collection":"CH-snow",
  "position":[0,0,0], "rotation_z":0, "scale":1
}
```

同一入口支持 `category=prop/structure` 的物件，以及 `.glb/.gltf`。模型必须已 pin 到场景 JSON 所在项目目录；不接受任意绝对文件路径。model-build/model-bind 会带走模型、依赖、锁文件和署名。人物蓝色、结构灰色、物件褐色，预演材质不改变缓存原模型。

动作可使用根节点 keys 与 `pose_keys`：frame、rig、bone，以及可选 rotation（本地 XYZ 欧拉角，单位度）、location（骨骼本地坐标）、properties（该骨已有数值属性）。必须先检查实际控制器和 IK/FK 属性，不按名字猜轴向。模型自带控制器不等同于我们原始 actor 的 hand/foot 通用 IK 接口；尚未完成统一自动重定向。

导入模型没有自动获得完整碰撞代理。可配置 collision_boxes 供场景障碍检查；其自身人物网格、自碰撞与接触尚需专门适配。含导入模型的报告为 `partial`（已有可检测问题仍是 failed），可以生成诊断视频但不能说“几何全部通过”。`model-build` 对 partial 返回 1 并保留诊断输出；整场渲染允许 partial，须实际看视频、明确未检查范围，再沿既有用户确认流程处理。视频仍是预演，不是最终 AI 成片。

## 换电脑与离线迁移

- Git 保存 `model-assets.lock.json`、场景 JSON、署名与代码，不必保存大模型。生产项目若自行建 Git，应加入 `/model-assets/` 忽略规则。
- 新电脑执行 `library-restore PROJECT`：按锁文件补下载，校验确切内容；有合格缓存时可离线恢复。下载源失效会明确失败，不替换成“相似版本”。
- `library-bundle PROJECT NEW.zip` 输出包含锁文件、模型、贴图和署名的离线包。解压到新目录后 `library-check NEW_PROJECT`；再带上该制作项目的其他文件即可迁移。
- 当前库状态只区分下载未验证与文件完整性；视觉审核和用户确认仍属于具体项目，不把一次检查当作所有用途认证。

## 已接入资源

Snow v3：官方 https://studio.blender.org/characters/snow/v3/ ，CC-BY 4.0。保留署名：Snow Rig © Blender Foundation | studio.blender.org。本技能提供下载描述，模型二进制不随 Git 发布。一般物件可以按同一机制注册；并不意味着所有种类的模型已经预装。


## 动作素材与重定向

现成绑定提供控制能力，不自带自然表演。需要明确跑跳、扑倒、滑行等身体动作时，先判断已有动作素材能覆盖哪些段落，再决定补做范围。核实来源条款并记录片段、帧段、帧率、坐标单位和修改内容；模型许可不自动覆盖动作许可。来源描述可能不准确，必须看动作本身，不能用相近但不同的行动替换用户要求。没有适合的完整动作时，可试做局部动捕与补做动画，但在审阅页区分两者，不声称整段都是动捕。

重定向按实际骨架和控制器适配。优先保留目标人物的肢体长度、关节朝向与接触关系，不能只把不同骨架的同名旋转直接复制。更换已有角色动画时，只解除旧 action／相关 NLA；不要对带绑定驱动的 armature 调用 `animation_data_clear()`，它也会删除驱动器，使 IK/FK 控制失效。外部脚本自动执行仍关闭；检查所需驱动是否有效，不用开启全部脚本来掩盖适配问题。

先检查少量关键姿态，再渲染完整视频。保存后重新载入，检查实际动画回放的支撑、足部滑动、落地缓冲、速度变化、接触与障碍间隙；构建时的正确姿态不证明保存后的动画正确。若靠整体抬升修正地面穿插，记录修正量并检查是否破坏脚或手的接触，不能用整体漂浮掩盖错误姿态。

适配代码和源片段随项目保存，角色控制器映射与故事时间表分开。当前没有跨所有角色自动重定向的成熟通用入口；一次样片成功不代表所有体型与动作都已支持。简化动作预演先作为空间、时间审阅素材，只有实际观看自然性合格后，才提议用于目标视频系统的动作参考；几何检查通过不能替代该判断。
