# 导演稿检查与版本协议

阅读 narrative-and-camera.md 后使用本协议。Python 仅发现字段缺项与少量疑点；Codex 必须实际评估剧情、人物、表演、语气和时间，不能通过填“通过”来完成任务。检查不是用户批准，也不是目标模型运行验证。

## 中文输入

新项目在建立 manifest 镜号后，提供 JSON 对象 `{ "SHOT_01": { ...完整中文字段... } }`：

```sh
.venv/bin/python scripts/svd.py review-init PROJECT --storyboard-file work/storyboard.json --system-file work/system.json
```

每镜字段为 purpose、description、framing、action、camera、dialogue、continuity、psychology、performance、delivery、rhythm、duration。除 duration 为正数秒之外，均为文本。dialogue、delivery 对无台词镜明确写无发声或画面文字，不能填虚构声音。物件插镜的心理/表演字段写信息功能与不适用原因。

旧项目读取时兼容补出新增字段，保留原内容和版本历史；缺项不能通过导演检查。已有项目不得重新初始化。页面编辑，或用以下单镜包修改（先读取最新 revision）：

```json
{"id":"SHOT_01","revision":5,"zh":{"purpose":"...其余完整字段..."}}
```

```sh
.venv/bin/python scripts/svd.py review-edit PROJECT work/edit.json
```

上例只是包的结构，zh 必须提供完整字段；它不是可直接执行的完整示例。修改语气也改变中文版本，必须同步目标原文和对照。

## 检查流程

1. 中文结构化编写完成后 review-export / review-sync，同步画面、逐句说法与衔接。正文不得混入“稍后验证”等制作待办；待办留在说明区。按目标系统规则转换，不擅自翻译原台词或添加未知情绪标签。
2. 执行 `review-check PROJECT --output work/director-request.json`。输出包括缺项、启发式警告、全部镜头的中文与目标文本、原剧本及已登记的分析、版本指纹。未通过时退出码为 1，不代表工具崩溃。
3. Codex 结合整段上下文和原文检查。问题影响画面时先修改中文再同步；尚未解决时可记录 revise，不能把问题只藏进英文。
4. 将真实判断写成下面的结果包，用 `review-director` 保存。字段通过不代表判断正确；必须给出本镜与邻镜的具体证据。无需用户为这个内部质量检查再批准。
5. 全部相关检查通过后，在页面展示依据，由用户确认镜头。页面新增“待导演检查”；这一步不能用“已同步”跳过。

结果结构：

```json
{
  "project_revision": 7,
  "context_hash": "使用本次 review-check 的原值",
  "analysis_hash": "使用本次 review-check 的原值",
  "sequence_note": "具体说明这一段信息、压力与缓冲如何变化，以及人物理解和策略如何推进。",
  "shots": [{
    "id": "SHOT_07",
    "checks": {
      "narrative": {"status":"pass","note":"说明本镜带来的新信息或变化及原文依据。"},
      "character": {"status":"pass","note":"说明人物的目标、已知信息、选择与前后状态为何一致。"},
      "performance": {"status":"pass","note":"核对可见反应、逐句语气及角色差异；若仅物件镜，写清实际适用范围。"},
      "pacing": {"status":"pass","note":"说明事件、反应、台词/阅读的时间与切点；区分估算和实测。"},
      "continuity": {"status":"pass","note":"指出动作接点、视线、持物与空间关系；尚未建立的布局不得声称已验证。"},
      "adaptation": {"status":"pass","note":"核对英文及中文对照保留了哪句台词、说法和动作；说明当前适配阶段。"}
    }
  }]
}
```

```sh
.venv/bin/python scripts/svd.py review-director PROJECT work/director-result.json
```

六项均须有具体依据。status 为 pass、revise、not_applicable；最后一种必须解释原因。示例说明文字不是可原样用于真实项目的审核证据。任何 revise 阻止该镜确认。缺项情况下可以记录问题，但不能全部标通过。警告是启发式提示，允许实际判断后说明为何无需修改，不能把简单正则表达式当作摄影规则。

## 版本与范围

检查绑定整段中文、目标文本、目标系统、原剧本和分析内容，防止局部改动让后续反应或时间仍沿用旧判断。任一镜头修改会使旧导演检查过期；重新检查全段影响，可以在说明中确认未受影响内容仍成立。分批写入时重新导出最新项目 revision；检查指纹不受仅保存审核记录或用户确认影响。

原分析或系统配置变化也要求重新检查。代码无法自动识别所有语义错误，用户看到的依据和实际导演阅读仍是必需环节。旧项目的缺项不会自动补为“合格”，已有图片和原始台词不会因迁移被覆盖。

review-check 的 ready 只表示字段齐备且记录了当前版本的检查；正式生产仍需剧情、分镜、布局和必要预演等用户确认。全段节奏不能靠填写分数自动保证。
