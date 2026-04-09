# Feishu Review Image Refresh Design

## Goal

将当前飞书审核卡中的 `修改 / 重写` 图片侧动作，收敛成更明确的 `刷新封面图 / 刷新内容配图`，并让按钮点击后的回流、命令拼接、续跑逻辑全部对齐到同一套端到端语义。

这次设计的重点不是改按钮文案，而是把“用户点了什么”和“系统实际做了什么”重新对齐。

## Explicit Requirements

- 飞书审核卡保留 `✅ 通过`。
- 飞书审核卡把 `✏️ 修改` / `❌ 重写` 替换成：
  - `刷新封面图`
  - `刷新内容配图`
- 新按钮必须带正确的回调参数。
- 新按钮点击后不再进入“修改说明卡”流程。
- `refresh_cover` 和 `refresh_graphics` 都应直接续跑。
- 现有桥接层如果依赖 `resume_command`，要同步给出新的命令。

## Inferred Priorities

- 用户实际想控制的是图片重生，而不是文案重写。
- 飞书卡片、OpenClaw bridge、`xhs_feishu_flow.py` 三层必须一起调整，否则会出现“卡片名字对了，但回流仍是旧动作”的半坏状态。
- 这次先把飞书审核流内部语义收正，不强行把它和武汉客户 router 状态机合并。
- 旧卡片应尽量保持一段时间兼容，避免刚发出的历史卡片全部失效。

## Current Reality

### Review card layer

- `scripts/feishu_client.py` 的 `send_review_card()` 当前发出三类动作：
  - `approve`
  - `modify`
  - `rewrite`
- 它们通过交互卡 `value` 回流，而不是普通 URL 按钮。

### Resume layer

- `scripts/xhs_feishu_flow.py` 的 `resume_review_action()` 当前只识别：
  - `approve`
  - `modify`
  - `rewrite`
- `modify / rewrite` 当前语义是：
  - 重新生成 payload
  - 重新生成标题和正文
  - 重新发审核卡
- 这和“只刷新图片”不是同一类动作。

### Bridge layer

- 仓库内没有 Feishu HTTP 回调服务实现。
- 文档和历史链路表明，交互卡事件由 OpenClaw / Lark bridge 转成一条新的合成消息。
- `.openclaw/extensions/openclaw-lark/src/tools/auto-auth.js` 当前会为旧动作生成 `resume_command=... scripts/xhs_feishu_flow.py --mode resume --action <approve|modify|rewrite> --message-id ...`

## Design Summary

采用“保留 approve、替换图片动作、兼容旧动作”的方案：

- 新审核卡动作：
  - `approve`
  - `refresh_cover`
  - `refresh_graphics`
- 新按钮仍走交互卡 `value` 回流。
- bridge 继续生成 `resume_command`，但命令改为新的 action。
- `xhs_feishu_flow.py` 扩展新 action，并把它们定义为“只刷新图片，不刷新文案”。
- `modify / rewrite` 暂时保留兼容解析，但不再作为新卡默认按钮。

## Interaction Contract

### Card button payload

`send_review_card()` 的三个按钮统一维持以下结构：

```json
{
  "action": "xhs_review",
  "decision": "<approve|refresh_cover|refresh_graphics>",
  "note_id": "<note_id>"
}
```

### Bridge synthetic message

OpenClaw bridge 收到卡片动作后，继续构造带以下字段的合成消息：

- `source_message_id`
- `card_message_id` 或 `reply_to_message_id`（如果可得）
- `resume_command=...`

新的 `resume_command` 目标命令为：

```bash
cd "<workspace>" && "<python>" scripts/xhs_feishu_flow.py --mode resume --action refresh_cover --message-id "<source_message_id>"
```

或：

```bash
cd "<workspace>" && "<python>" scripts/xhs_feishu_flow.py --mode resume --action refresh_graphics --message-id "<source_message_id>"
```

如果 bridge 已经给出 `resume_command`，上层 Agent 仍然优先直接执行它，不再自行拼命令。

## Runtime Semantics

### `approve`

- 保持现有行为不变。
- 继续发送最终稿卡片。

### `refresh_cover`

- 不重新生成 payload。
- 不改 `variants`、`hashtags`、`cover_title`。
- 只重生成封面相关图片。
- 重生完成后：
  - 上传新图片
  - 发送新的审核卡
  - 继续等待审核

### `refresh_graphics`

- 不重新生成 payload。
- 不改正文内容。
- 只重生成内容配图。
- 重生完成后：
  - 上传新的配图集合
  - 发送新的审核卡
  - 继续等待审核

### Legacy compatibility

- 已发出的历史卡片如果回流 `modify / rewrite`：
  - 仍由现有兼容分支处理
  - 不强行报错
- 新发出的卡片不再展示 `modify / rewrite`

## State Changes

`review_state.json` 维持现有结构，同时新增少量字段帮助区分链路：

- `review_action_mode`
  - `revision`
  - `image_refresh`
- `cover_refresh_count`
- `graphics_refresh_count`

这些字段只服务于：

- 诊断当前审核卡属于哪种模式
- 判断已经刷新过多少次
- 排查“为什么这次文案没变、只有图片变了”

## UI Rules

### Review card buttons

- `✅ 通过`
- `刷新封面图`
- `刷新内容配图`

### Review card copy

建议在卡片 note 或正文补一条轻提示：

- `当前为图片刷新模式：文案不变，仅刷新视觉产物。`

这不是硬性功能，但能减少误解。

## File Changes

### In repo

- `scripts/feishu_client.py`
  - 修改审核卡按钮文案和 `decision`
- `scripts/xhs_feishu_flow.py`
  - 扩展 CLI `--action`
  - 扩展 `resume_review_action()`
  - 新增图片刷新分支
  - 不再让新按钮进入修改说明卡流程
- `SKILL.md`
  - 更新飞书卡片交互说明
- 相关测试 / smoke test

### Out of repo but required by actual architecture

- `/Users/lmsx/.openclaw/extensions/openclaw-lark/src/tools/auto-auth.js`
  - 把回流动作和 `resume_command` 切到 `refresh_cover / refresh_graphics`
- 如有对应类型声明或说明文件，也同步更新

## Verification Plan

- 单测：
  - 审核卡按钮 payload 正确
  - `resume_review_action(action="refresh_cover")` 只刷新图片，不改 payload
  - `resume_review_action(action="refresh_graphics")` 只刷新图片，不改 payload
  - 旧动作 `modify / rewrite` 仍兼容
- 冒烟验证：
  - `xhs_feishu_flow.py --mode draft --dry-run`
  - `xhs_feishu_flow.py --mode resume --action refresh_cover --message-id ... --dry-run`
  - `xhs_feishu_flow.py --mode resume --action refresh_graphics --message-id ... --dry-run`
- bridge 侧验证：
  - 点击飞书卡片按钮后，合成消息里出现新的 `resume_command`
  - 命令参数中的 `--action` 与按钮一致

## Non-Goals

- 这次不把飞书审核流整体迁移到 `xhs_customer_router.py`
- 这次不引入新的 Web 回调服务
- 这次不统一飞书流与武汉客户 router 的完整状态模型
- 这次不设计“修改说明卡”的替代品

## Risks

- 如果只改仓库内按钮、不改 `.openclaw` bridge，卡片会显示新按钮，但回流仍可能走旧语义。
- 如果直接删除 `modify / rewrite` 兼容分支，已发出的历史卡片会失效。
- `xhs_feishu_flow.py` 当前本质上是一条独立旧链路，和武汉客户 router 并未共享状态；本次只能保证这条飞书链内部语义一致，不能假装两条链已经统一。

## Recommended Implementation Order

1. 改 `scripts/feishu_client.py`，发出新的按钮 payload
2. 改 `scripts/xhs_feishu_flow.py`，支持 `refresh_cover / refresh_graphics`
3. 改 `.openclaw` bridge，生成新的 `resume_command`
4. 补测试和文档
5. 用 dry-run 做端到端回归
