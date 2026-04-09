---
name: xhs-router
description: Use when handling the Wuhan tutoring Xiaohongshu private-DM workflow and you need stage-aware routing, materials gate enforcement, or a safe state summary.
---

# xhs-router

先读取 `clients/wuhan-tutoring/state/feishu_dm/<open_id>.json`。

如果 `materials_ready=false`：
- 只允许汇总当前状态
- 只允许继续素材收集、风格分析、缺口报告
- 不允许进入选题、文案、封面图、配图生产流

如果 `materials_ready=true`，按顺序路由：
1. 选题请求 -> `xhs-topic`
2. 文案生成或局部改写 -> `xhs-writer`
3. 封面图请求或局部封面修改 -> `xhs-image-cover`
4. 配图请求或局部配图修改 -> `xhs-image-graphic`
5. 回退、汇总、重来当前阶段、局部修改解析 -> `xhs-feedback`

补充规则：
- 如果客户消息里带参考图片、本地图片路径、图片 URL，或“按这个/照这个/参考链接”之类表述，优先进入严格参考生图模式
- 严格参考模式会把参考素材写入 `state.reference_materials`
- 同一阶段后续再次生成时，默认复用最近一次参考素材

硬规则：
- 未明确确认，不得推进到下一阶段
- 已确认内容默认锁定
- “汇总”是旁路指令，不改变状态
