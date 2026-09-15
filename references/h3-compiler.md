# H3 Ref2VA 结构化编译

运行 `.venv/bin/python scripts/h3.py INPUT.json OUTPUT.json`，再将输出的 text、translation_zh 与实际 check_note 放入 groups-sync 对应任务。路径由调用者指定；结果不自动登记或批准。输出 syntax_validated 仅代表本编译器已覆盖的结构规则，target_h3_validated 始终为 false。

输入示例（合成工具示例，不是导演教学或真实素材批准）：

```json
{
  "mode": "Ref2VA",
  "labels": ["<Picture 1>"],
  "sections": {
    "subject_definitions": {"en": "<Subject 1> is the woman in <Picture 1>.", "zh": "人物1是图片1中的女人。"},
    "summary": {"en": "[reference generation] A woman speaks in a room.", "zh": "参考生成：女人在房间里说话。"},
    "retention_analysis": {"en": "<Subject 1>: fully_preserved - her appearance is retained.", "zh": "保留人物1的外貌。"},
    "overall_soundscape": {"en": "Quiet room tone.", "zh": "安静的室内环境声。"},
    "non_diegetic_music": {"en": "No music.", "zh": "无配乐。"}
  },
  "shots": [{
    "duration": 5,
    "camera": {"en": "a static medium shot of the woman.", "zh": "女人的固定中景。"},
    "scene": {"en": "She sits beside a window.", "zh": "她坐在窗旁。"},
    "action": [{"speaker": "S1", "language": "Chinese", "text": "你回来啦？", "voiceover": false,
      "delivery": {"en": "The woman softly", "zh": "女人轻声"}}]
  }]
}
```

无对白的 action 项为 `{"en":"She turns toward the door.","zh":"她转头看向门。"}`。action 可混合多个动作和台词项，顺序即播放顺序。说话者由导演按本任务首次发声顺序提供，程序负责格式，模型核对实际人物归属。camera 提供具体取景，编译器直接在其前加入官方切镜句，不插“以下画面”。台词仅一个原文源，双语输出共用它，程序不翻译或改写台词。

labels 必须来自真实任务槽位；编译时允许无素材的结构草稿，但不得使用未列出的标签。分组同步会再次按项目真实槽位核查，不信任输入自报标签。媒体存在、版本和批准仍由交付就绪检查负责。

当前自动核对：六章节的顺序、非空与重复；正文镜号及任务内切点；首镜无切点；任务4–15秒；素材槽位和人物引用；对白语言标记、标签闭合及未知控制标签；本地直白表达约定。章节中的镜头引用不会被误算为正文镜头。

当前不证明：英文语义与中文完全对应、口气能否实现、镜头可见范围与表演是否兼容、人物动机、完整官方语法覆盖、真实口型或实际生成质量。复杂跨镜对白和歌词应走官方人工编写并核验流程；不把本工具当完整自然语言编译器。FL2VA等其他模式暂不使用本Ref2VA编译入口。
