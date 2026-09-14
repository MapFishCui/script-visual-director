# 通用生成分组与导演台适配（v0.6）

分镜是独立制作单位，生成组是一次模型任务的组织单位。分组保持与目标工具分离；AIMixer 是当前支持的一个适配器，不把它的 UI 或任务类型写进原始分镜。当前提供通用 ZIP 和 AIMixer r2v `.mmxpack.zip` 两种导出。

## 工作顺序

1. 在分镜阶段，Codex 按连续动作、信息投放、人物反应、场景和时间省略提出分组，同时考虑目标时长、参考视频和素材数量。所有镜头按顺序连续覆盖一次，不任意跳镜凑组。
2. 保留每镜原时长；为每组计算从0开始的切镜时间，写导演意图、承接状态和结束状态。组内起止与原片时间同时保留，避免把整集时间直接交给单次生成。
3. 根据目标模式编译组级完整系统提示词与完整中文对照。AIMixer H3 r2v 使用六部分结构；公共主体定义、参考保留规则、各镜动作和逐句口气均有依据，不能把逐镜片段随意拼成缺少上下文的最终提示词。
4. 用户确认分镜与分组后，继续布局、可选预演及资产流程。分组确认是导演计划确认，不等于图片已生成或模型已验证。
5. 预演保留逐镜文件，用 `groups-previs` 输出组内串联版。一个组缺少任何成员镜头时，整组标为缺失，不能把已有部分伪装完整组。
6. 基准图确认后绑定实际资产编号与版本、预演索引与对应项。素材槽位发生改变时重新编译、核对中文并确认组方案。按目标限制导出；不执行模型生成。

用户更换工具时，重新保存 adapter 并编译组文本；镜号、中文导演稿、预演源和资产文件保留。新工具限制不同，可以调整分组，但需重查受影响的提示词、组预演与衔接。当前没有为未实现的适配器伪造原生格式。

## 数据与命令

状态独立保存在项目 `groups/state.json`，历史位于 `groups/history/`，均登记为交接文档，不扩展 manifest 顶层字段。分组修改采用分组 revision 和审核项目 project_revision 双重检查；源分镜、目标格式或剧情变更会使旧方案失效。

保存方案的 JSON 例子（必须替换为真实镜号并覆盖全部镜头）：

```json
{
  "revision": 0,
  "project_revision": 12,
  "adapter": "aimixer-h3",
  "shared_references": [
    {"key":"hero","kind":"image","asset":"CHAR_HERO_HEAD","version":1}
  ],
  "groups": [{
    "id":"G01","title":"进门与取水","shots":["SHOT_01","SHOT_02"],
    "intent_zh":"先建立普通顾客的行动，再让异常停顿产生疑问。",
    "continuity_in":"男人在前门外，尚未持有水瓶。",
    "continuity_out":"男人持水瓶站在顾客区，冰柜门关闭。",
    "references":[
      {"key":"store","kind":"image","asset":"SCENE_STORE_LEFT","version":1},
      {"key":"motion","kind":"video","index":"previs/groups/RUN/index.json","item":"G01"}
    ]
  }]
}
```

图片必须引用资产编号和确切版本，不接受任意未登记图片路径。视频引用本工具已校验的逐镜或组预演索引：逐镜时 item 为镜号，组预演时 item 为组号；只选择纯摄影机视频。公共素材当前仅支持图片，预演视频按组挂载。本 skill 不生成配音，当前分组导出也不提供音频素材绑定。

```sh
.venv/bin/python scripts/svd.py groups-apply PROJECT PLAN_JSON
.venv/bin/python scripts/svd.py groups-request PROJECT work/groups-request.json
# Codex 实际阅读全部上下文并编译后：
.venv/bin/python scripts/svd.py groups-sync PROJECT SYNC_JSON
.venv/bin/python scripts/svd.py groups-confirm PROJECT --evidence '用户实际确认当前分组及中英稿的原话'
.venv/bin/python scripts/svd.py groups-check PROJECT
.venv/bin/python scripts/svd.py groups-previs PROJECT previs/runs/RUN/exports/EXPORT/index.json
.venv/bin/python scripts/svd.py groups-package PROJECT DELIVERY.mmxpack.zip
# 尚未确认或缺少素材的明确阶段交付：
.venv/bin/python scripts/svd.py groups-package PROJECT DELIVERY.draft.mmxpack.zip --draft
```

`groups-request` 输出最新两种 revision、源分镜指纹、组内／原片时间、原中文与目标文本、素材槽位。同步 JSON 包含同一组 revision、project_revision、storyboard_fingerprint，以及完整 groups 列表；每项为 id、text、translation_zh、check_note。每组必须有完整中文对照与实际导演检查说明。H3 会检查六部分、从1开始的 Shot 编号、切点时间以及引用槽位，不能用此机械检查代替语义检查。

网页显示当前镜头所属组、组内时间、系统原文和中文对照；可编辑组名、成员镜号、导演意图和承接说明。每次保存会检查全段覆盖并撤销组确认，返回 Codex 说“同步分组”。跨组挪镜、拆组、合组建议让 Codex 一次提交完整方案；逐组保存不能暂时破坏全段覆盖。网页未保存组稿在会话中保留，旧版本草稿供手工合并。实际确认可在网页点击，也可在当前对话回复“确认分组”。

## AIMixer 适配约定

对照 [AIMixer 导入源码](https://github.com/AIMixer/ComfyUI_MiniMaxH3_Director/blob/52f8fb7b8d8eb6bebf33ebb534827efa8f95484c/director/pack.py)，适配版本记录为 `52f8fb7b8d8eb6bebf33ebb534827efa8f95484c`。

- 任务为 r2v，每个通用组映射到一个 asset_groups 子目录，保存 group.json 和本组媒体。
- 公共图片占据 Picture 1 起的槽位，组内图片接续编号。检查提示词中的编号与最终文件映射，不能在每组重新从1覆盖公共角色。
- 原生目录使用 ASCII，pack.json 指定 format、formatVersion 和 taskType；不手写 timeline.json，让上游导入器组装时间轴。
- 中文对照、原镜号／组内时间、素材用途、原始资产版本与 SHA-256 放在 extra/ 中，不塞进模型英文提示词。
- 原时长保留为 durationSec。frameCount 按当前上游24fps、17k+5规则向上对齐，报告尾部增加时长；不修改原分镜或加速预演。画布采用导演台默认864×480，导入后按实际部署调整，当前不声称自动选择最优分辨率。
- 每次任务最多9图、3视频，单段参考视频2–15秒且视频总时长≤15秒；一秒特写可与邻镜预演合成合规组，不能单独作为不合规视频输入。超限需重新分组或下游细分。多个组可批量运行，限制作用于每个组，不是整个导演包。
- 公共提示词留空，每组写完整六部分，避免把多份主体定义或声景段盲目串接。公共图片仍共享。
- 段间引导默认关闭，用户依连续动作需要在目标导演台开启；切镜或时间省略不自动开启。当前不自动注入上段生成结果，也不生产最终视频。

`groups-check` 检查组计划、素材状态和输入约束；正式 `groups-package` 还要求整个项目的前置确认、资产检查及关卡无待办。草稿可供查看结构，缺失素材不伪造文件、不改编号；草稿也不能包含超限槽位或超限参考视频。所有导出均保留 target_h3_validated=false。

## 验证范围

项目包含可选的上游契约测试。设置 `SVD_AIMIXER_SOURCE` 指向已检出的 AIMixer 仓库后运行 unittest；测试执行其真实 ZIP 解压、时间轴组装、媒体复制和路径重写函数，仅替换宿主路径与HTTP传输导入，不启动 ComfyUI 或模型采样。普通机器未提供该源码时此项会跳过，不要求把导演台安装进 skill 的虚拟环境。

格式导入测试通过不等于视频生成通过。用户目标机器的 ComfyUI、节点版本、显存、帧率及最终推理效果仍需实测；未来升级上游后重新运行契约测试。
