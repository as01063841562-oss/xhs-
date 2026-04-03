# 第二阶段接口预留

## 私域 / 客服回复辅助

### 预期输入

- 平台
- 用户消息
- 历史对话样本
- 回复风格约束

### 预期输出

- `reply_suggestions.md`
- `risk_notes.md`
- `handoff_needed.json`

## 视频高光片段提取与字幕生成

### 预期输入

- 视频文件路径
- 目标平台
- 时长约束
- 风格偏好

### 预期输出

- `highlight_segments.yaml`
- `subtitles.srt`
- `edit_notes.md`
