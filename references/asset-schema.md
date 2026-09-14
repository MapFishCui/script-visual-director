# 操作与数据约定

## 环境

Python 3.9 或更高。项目内使用独立虚拟环境，不提交或打包 `.venv`。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m unittest discover -s tests -v
```

也可使用 `uv venv --python python3 .venv`，然后 `uv pip sync --python .venv/bin/python requirements.lock`。命令在 Skill 根目录运行。Windows 将解释器路径替换为 `.venv/Scripts/python.exe`。

Apple 芯片机器若 uv 自身是 Intel 程序，可能误选 x86_64 wheel；先核对 `.venv/bin/python -c 'import platform; print(platform.machine())'`。输出 arm64 时，可在 uv pip sync 后加 `--python-platform aarch64-apple-darwin`，使二进制依赖匹配解释器。

## 创建一次制作任务

```sh
.venv/bin/python scripts/svd.py init PROJECT --script SCRIPT_TXT_OR_MD --name '项目名称'
.venv/bin/python scripts/svd.py validate PROJECT
.venv/bin/python scripts/svd.py queue PROJECT
```

`init` 只复制原文、创建 manifest，不假装解析剧本。Codex 按参考规范撰写分析、视觉指南、交接文档和 manifest。读取 Word/PDF 剧本时先用环境中的相应能力提取文本，并保留原文对应关系。

机器结构以 `scripts/schema.py` 为准；完整可运行示例由 `examples/make_demo.py` 创建。JSON 不允许未知字段和非有限数值，编号只用英文字母、数字、下划线和短横线，路径用项目内 POSIX 相对路径。

## manifest.json

根字段：`schema_version=1`、`name`、`documents`、`shots`、`assets`、`layouts`、`gates`。

- documents：`path` 与 `role`，角色为 source、analysis、visual-guide、handoff。实际已写出的文档才登记。
- shots：`id`、`beat`、`purpose`、`description`、`assets`、`layout`（`{id,version}` 或 null）、`camera`（编号或 null）、`continuity`。未启用审核时详细导演信息写在 camera-plan.md；启用审核后，时长、心理、表演、逐句语气和运镜以 review/state.json 为准，camera-plan.md 仅作标明版本的导出或历史文档。镜头与资产互相引用。
- assets：`id`、`type`（character/scene/prop）、`name`、`description`、`sources`（每项 basis 与 text）、`shots`、`current_version`、`versions`。变体用独立编号，versions 表示该资产的修订历史。
- layouts：由 render-layout 登记 id、version、path、outputs、review、blockout_required、blockout_review。
- gates：`id`、`refs`（若干 `{id,version}`）、`status`（pending/approved/rejected）、`evidence`（实际用户确认）。refs 只引用本关卡确认的基准，不包含等待此关卡的变体。

一个待生成的版本：

```json
{
  "version": 1,
  "file": null,
  "production": "prompt_ready",
  "validity": "current",
  "review": {"status": "pending", "note": ""},
  "approval": {"status": "pending", "evidence": ""},
  "prompt": "角色基准图的实际生图要求",
  "tool": "",
  "dependencies": [],
  "gates": [],
  "note": ""
}
```

普通变体若无需用户确认，approval.status 设为 not_required。dependencies 每项为 `{kind: asset或layout, id, version}`，用于身份参考、场景布局或家庭外貌等真实依赖。`gates` 为必须已确认的关卡编号。文件生成后才能有 file；review passed 必须有检查说明；approval approved 必须有实际用户证据。

## 出图后登记与版本修改

```sh
.venv/bin/python scripts/svd.py register PROJECT CHAR_DAD --image GENERATED_IMAGE --tool image_gen
.venv/bin/python scripts/svd.py review PROJECT CHAR_DAD --note '已检查脸部、年龄和服装一致性'
.venv/bin/python scripts/svd.py approve PROJECT CHAR_DAD --note '用户明确确认该版本的原回复摘要'
.venv/bin/python scripts/svd.py approve-gate PROJECT GATE_PARENTS --evidence '用户确认这两张父母基准图'
.venv/bin/python scripts/svd.py revise PROJECT CHAR_DAD --reason '根据用户要求调整发型'
```

revise 创建新版本，不修改旧文件；旧版 superseded，直接及间接资产依赖 stale，受影响关卡回到 pending。新版本继承 prompt、依赖与关卡以便编辑，但不会自动改成最新参考版本；Codex 必须检查并明确更新依赖，避免未经复核就跟随新设计。

`validate` 返回 errors（数据或文件错误）与 pending（未完成事项）；规划阶段 pending 不导致失败。`--strict` 要求两者均为空。`queue` 只列出实际可生成的项目，已生成图片应检查或 revise，不重复覆盖。

数据结构表达和校验依赖，但不能判断用户的文字是否真是确认、心理推断是否合理、图片是否好看；这些仍由 Codex 结合实际对话和图片负责。
