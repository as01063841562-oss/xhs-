---
name: xhs-topic
description: Use when the Wuhan tutoring workflow is in topic stage and the user asks for topic options, subject directions, or topic narrowing.
---

# xhs-topic

先读取：
- `clients/wuhan-tutoring/prompts/system-prompt.md`
- `clients/wuhan-tutoring/references/style-notes.md`
- `clients/wuhan-tutoring/references/source-index.json`

输出 3 到 5 个备选选题，每个必须包含：
- 标题候选
- 核心角度
- 预期标签
- 素材参考或竞品参考

限制：
- 如果 `materials_ready=false`，不要假装已经具备完整风格样本
- 选题可以利用现有本地样本标题信号，但不要编造正文级结论

