---
name: edu-media-openclaw
version: 3.0.0
description: 小红书图文笔记审核流（v3多图版）。用户说"帮我做一个小红书笔记"就触发：匹配预设选题→HTML渲染3张图→AI生文案→飞书审核卡片→通过后发布。支持武汉本地教育选题库。
metadata:
  openclaw:
    emoji: "🍠"
---

# 小红书笔记自动化 Skill v3.0

## 什么时候触发这个 Skill

当用户说以下类似的话时，触发此 Skill：

- "帮我做一个小红书笔记，主题是..."
- "生成小红书内容，关于..."
- "做一篇小红书，主题..."
- "帮我写小红书文案"
- "生成小红书图文"
- "做个小红书帖子"
- "小红书卡片交互"
- "通过 / 修改 / 重写 小红书卡片"
- "帮我生成武汉中考/升学/XX学科的小红书笔记"
- "批量生成小红书笔记"
- 任何涉及"小红书"+"生成/做/写/创建"的请求

## 触发后怎么做

### 第一步：从用户消息中提取参数

从用户的消息中提取：
- **主题**（必须）：用户想要的小红书笔记主题，如"武汉中考数学压轴题"、"初升高时间轴"等
- **目标受众**（可选）：如果用户没说，默认用"初中学生家长"

### 第二步：调用脚本生成初稿并发送审核卡片

```bash
cd "/Users/lmsx/Documents/Playground/edu-media-openclaw" && "/Users/lmsx/Documents/Playground/edu-media-openclaw/.venv/bin/python" scripts/xhs_feishu_flow.py --topic "用户提取的主题" --audience "提取的受众" --mode draft
```

**v3.0 新能力：**
- 自动匹配预设选题库（武汉本地教育 13 个选题，覆盖数学/英语/语文/物理/化学/升学规划）
- 匹配到预设选题时，使用 HTML 模板渲染 3 张高质量图片（封面+内容+CTA）
- 未匹配到时，回退到 AI 生成封面图（单图模式）
- 审核卡片展示多张图片预览

**参数说明：**
- `--topic`：填入从用户消息中提取的主题（必须）
- `--audience`：填入受众（可选，默认"教育行业运营负责人"）
- `--mode draft`：只生成初稿并发送审核卡片，停在用户确认前

### 第三步：告诉用户结果

脚本执行完毕后：
1. 告诉用户"小红书初稿已生成并发送到飞书审核"
2. 告诉用户去飞书查看审核卡片
3. 卡片上有✅通过 / ✏️修改 / ❌重写按钮
4. 如果用户点修改/重写，先打开"修改说明卡"，等用户填写修改意见后再继续
5. 只有用户点通过后，才进入最终稿阶段

### 第四步：处理卡片回流

当飞书卡片按钮被点击后，OpenClaw 会收到一条新的"卡片交互"消息，内容里会带：
- `小红书卡片交互：通过/修改/重写`
- `source_message_id=...`
- 也可能包含 `card_message_id=...` 或 `reply_to_message_id=...`
- 如果消息里带 `resume_command=...`，优先直接执行这条命令，不要自己重写参数
  或二次猜测

这时不要重新从头生成，而是：

```bash
cd "/Users/lmsx/Documents/Playground/edu-media-openclaw" && "/Users/lmsx/Documents/Playground/edu-media-openclaw/.venv/bin/python" scripts/xhs_feishu_flow.py --topic "同一主题" --mode resume --action approve --message-id "source_message_id 中的值"
```

- 回流模式主要靠 `--message-id` 定位任务，`--topic` 只用于日志，必要时也可以沿用原主题但不是关键
- 如果卡片消息是"修改"或"重写"，先打开"修改说明卡"，不要立刻重生成
- 如果是 `通过`，就继续发送最终稿卡片
- 如果是 `修改` 或 `重写`，先等用户填完修改说明，再重新生成一版审核卡
- 如果消息里已经给了 `resume_command`，直接照着执行即可，`--message-id`
  仍然用 `source_message_id`

## 预设选题库

当主题包含以下关键词时，系统会自动匹配预设选题并使用 HTML 模板渲染多图：

### 数学
- 武汉中考数学近3年压轴题型汇总（📊数据表格）
- 初三数学必考：二次函数题型全梳理（📋知识卡片）
- 武汉四调vs元调数学考点对比（⚖️对比图）

### 英语
- 武汉中考英语阅读高频话题TOP10（📊数据表格）
- 武汉中考英语作文万能模板（📋知识卡片）

### 语文
- 武汉中考语文必背古诗文64篇（📋知识卡片）
- 中考语文阅读理解答题模板（⚖️对比图）

### 物理
- 武汉中考物理实验题必考6大类型（📋知识卡片）
- 初中物理公式大全（📊数据表格）

### 化学
- 初三化学方程式全整理（📋知识卡片）

### 升学规划
- 2026年武汉中考全年备考时间线（📅时间线）
- 武汉九大名高+领航校录取分数线（📊数据表格）
- 初升高重要时间轴（📅时间线）

## 完整流程说明

```
用户在飞书说"帮我做一个小红书笔记，主题是武汉中考数学压轴题"
  ↓
AI 提取主题："武汉中考数学压轴题"
  ↓
步骤0：匹配预设选题库 → 找到"武汉中考数学近3年压轴题型汇总"(data_table)
  ↓
步骤1：AI 生成 3 版文案 + 标签 + 封面标题（用预设选题的标签覆盖）
  ↓
步骤2：HTML模板渲染 3 张图片（封面数据表+内容图+CTA引导图）
  ↓
步骤3：上传 3 张图片到飞书
  ↓
步骤4：发送多图审核卡片到飞书（带 ✅通过/✏️修改/❌重写 按钮）
  ↓
用户点击卡片按钮
  ↓
如果点通过：发送最终稿卡片（带 🍠发布到小红书 按钮 + 完整文案）
如果点修改/重写：先弹出修改说明卡，用户填完修改意见后再重新生成一版审核卡
  ↓
用户在飞书点击🍠按钮 → 跳转小红书发布
```

## 示例对话

**用户：** 帮我做一个小红书笔记，主题是武汉中考数学压轴题

**助手执行：**
```bash
cd "/Users/lmsx/Documents/Playground/edu-media-openclaw" && "/Users/lmsx/Documents/Playground/edu-media-openclaw/.venv/bin/python" scripts/xhs_feishu_flow.py --topic "武汉中考数学压轴题" --audience "初三学生家长" --mode draft
```

**助手回复：** ✅ 小红书初稿已生成（3张图片+3版文案），已发送到飞书审核。请去飞书查看卡片，点通过/修改/重写。

---

**用户：** 写一篇关于初升高时间轴的小红书

**助手执行：**
```bash
cd "/Users/lmsx/Documents/Playground/edu-media-openclaw" && "/Users/lmsx/Documents/Playground/edu-media-openclaw/.venv/bin/python" scripts/xhs_feishu_flow.py --topic "初升高时间轴" --audience "初二初三学生家长" --mode draft
```

---

**用户：** 做个小红书帖子，主题是宠物护理攻略

**助手执行：**
```bash
cd "/Users/lmsx/Documents/Playground/edu-media-openclaw" && "/Users/lmsx/Documents/Playground/edu-media-openclaw/.venv/bin/python" scripts/xhs_feishu_flow.py --topic "宠物护理攻略" --audience "养宠人群" --mode draft
```

（此主题不在预设选题库中，将自动回退到AI生成封面图的单图模式）

## 其他功能

### 查看选题库

```bash
cd "/Users/lmsx/Documents/Playground/edu-media-openclaw" && "/Users/lmsx/Documents/Playground/edu-media-openclaw/.venv/bin/python" scripts/xhs_topic_generator.py
```

### 公众号内容生成

当用户说"帮我写一篇公众号文章"时：

```bash
cd "/Users/lmsx/Documents/Playground/edu-media-openclaw" && "/Users/lmsx/Documents/Playground/edu-media-openclaw/.venv/bin/python" scripts/wechat_generate.py prepare --topic "主题" --audience "目标读者"
```

### 环境检查

```bash
cd "/Users/lmsx/Documents/Playground/edu-media-openclaw" && "/Users/lmsx/Documents/Playground/edu-media-openclaw/.venv/bin/python" scripts/check_env.py --write
```

## 重要限制

- 不绕过任何平台的人机验证
- 不承诺无人值守自动发布
- 最终发布需要用户点击飞书卡片按钮手动完成
