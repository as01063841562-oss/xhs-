---
name: xhs-feedback
description: Use when the Wuhan tutoring workflow message contains summary, rollback, regenerate, or scoped modification language that must be parsed before execution.
---

# xhs-feedback

先把用户消息结构化，再交回对应模块执行。

重点识别：
- `汇总`
- `回到文案`
- `重新来当前阶段`
- `标题换一个`
- `文案第N段`
- `封面图背景`
- `配图风格`

限制：
- 只做解析和范围判断
- 不直接重写正文或图片
- 推断不清时，宁可返回 `unknown` 也不要误伤已确认内容

