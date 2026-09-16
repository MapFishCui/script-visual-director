# 吸收官方 H3 skill 的适配规则

核对日期：2026-09-16。本文是本项目自行整理的接入约定，未安装或整体复制上游 skill，也不代表获得官方托管 H3-Context-IR 能力。

## 上游依据与读取时机

- 提示词入口：[h3-prompt-writing](https://github.com/MiniMax-AI/MiniMax-H3/blob/main/skills/h3-prompt-writing/SKILL.md)。选定 H3 后，先明确素材用途，再选择模式。
- [基础指南](https://github.com/MiniMax-AI/MiniMax-H3/blob/main/skills/h3-prompt-writing/references/base-en.txt)：文本、首帧、尾帧、首尾帧任务读取。保留它规定的图像对齐指令和三字段结构，不能套 Ref2VA 六章节。首尾图须由用户提供或另有授权取得，本 skill 不因此扩大为首尾帧生成器。
- [全参考指南](https://github.com/MiniMax-AI/MiniMax-H3/blob/main/skills/h3-prompt-writing/references/ref-en.txt)：多模态参考时读取。使用六章节，并明确参考来源、用途、保留程度和生效镜头。运镜参考不自动成为原视频编辑，音色参考不自动成为原音频复制。
- [动画分镜说明](https://github.com/MiniMax-AI/MiniMax-H3/blob/main/skills/3d-animation-short-generator/references/shot-table-spec.md)：仅借鉴连续性检查的观察角度，整理到 director-review.md；不继承卡通比例、夸张表演、强制荷兰角、固定钩子密度、逐秒填表或 Hub 专用工具。

这些链接跟随上游 main，不是锁定副本。更新时检查差异再修改本地代码和测试；不能宣称自动与上游最新版本完全一致。公开发布源码不等于任意再分发许可，本项目保留出处并独立实现检查，未打包上游正文。

## 模式与素材用途先于格式

运行 `scripts/h3.py INPUT.json OUTPUT.json --route`，输入 `media` 数组。每项 label、type、roles；音视频还需 duration。roles 是本项目内部用途枚举，不输出成 H3 控制码：

- image：first_frame、last_frame、appearance、environment、style、composition。
- video：motion、expression、camera、rhythm、environment、appearance、source_edit、source_continue。
- audio：voice、delivery、sound_style、copy_audio。

无素材 → T2VA；只用首图 → I2VA；只用尾图 → L2VA；首尾图 → FL2VA；出现其他参考用途 → Ref2VA。输入有歧义时先明确真实目的，不能看文件名或默认看到视频就选编辑模式。

路由核对素材数量与自报时长，不解码媒体、不证明真实绑定。当前确定性正文编译器仍只实现 Ref2VA；其他模式返回 compiler_supported=false，按所选官方指南编写及人工核验，不自动输出错误格式。模式路由不是新增基础模式编译能力。

## Ref2VA 编译与审阅

已有编译输入可增加 media，与 labels 对齐。编译器将其用途与 summary 类型核对；标签声明和文件真实性仍须由 groups-sync 与交付检查核实。旧输入无 media 时保留兼容，但不宣称已验证用途语义。新任务应提供 media。

定义行开头的标签才算独立定义；在另一人物说明中提到标签，不等于定义了该主体。程序检查重复定义、遗漏的保留说明、关系标记类型、summary 类型前缀，以及完整对白误放到总体声场/配乐章节。它不能判定中文与英文是否完全同义，或人物表演是否自然。

公共提示词属于导演台拼接方式，不是 H3 的独立全局记忆。最终每个任务必须形成一份自足、无重复章节的官方文本。现有导演包已经按任务输出完整文本时，不再把同一份 subject_definitions 复制进公共区；如改为公共定义，须在拼接后核对每段实际素材编号与定义。正文继续引用参与当前镜头的 Subject，不因定义移到公共区就删掉动作中的标签。

## 白模参考的边界

media 标记 previs=true 时，approved_roles 必须包含本次用途；此字段由助手根据真实审阅记录填写，不把布尔值当审核证据。若只确认了空间或摄影机，不能填 motion；未审阅的预演留在内部，不默认上传。路由会拒绝未声明相应用途批准的输入，并提示即使只参考运镜，其他外观/动作影响也未被硬隔离。

动作与摄影机、外观与体型分别解释来源；用户要求人物图负责外观、视频负责运动时，说明这种用途分工并不保证完全隔离。需要用目标系统小样核实，不用“官方 skill 已接入”代替实际生成验证。
