# 武汉教培小红书工作流 Design

## Goal

在现有 [edu-media-openclaw](/Users/lmsx/Documents/Playground/edu-media-openclaw) 仓库内，为武汉教育补习班搭建一套可运行的小红书教育内容工作流。该工作流复用现有 OpenClaw、Feishu 和 Gemini 链路，通过新增客户化目录、显式状态机、6 个本地 Skill 和素材模板，实现从选题、文案、封面、配图到汇总的受控生成流程。

## Confirmed Constraints

以下内容来自已确认需求，不作为推断处理：

- 不新建飞书 bot，复用现有 OpenClaw + Feishu 通道。
- 改造落在现有仓库 [edu-media-openclaw](/Users/lmsx/Documents/Playground/edu-media-openclaw) 内。
- 本次按单客户方案实现，不提前抽象多客户通用框架。
- 用户交互发生在飞书私聊场景。
- 会话状态必须落本地持久化，不能只靠聊天历史推断。
- 用户提供的 3 个小红书账号链接作为默认素材池。
- 素材未收齐时，不允许进入真实生产流。
- 业务状态保留 5 个：选题、文案、封面图、配图、完成。

## Current Repo Context

当前仓库已经具备以下可复用基础：

- [scripts/xhs_feishu_flow.py](/Users/lmsx/Documents/Playground/edu-media-openclaw/scripts/xhs_feishu_flow.py)：现有小红书 + 飞书端到端链路。
- [SKILL.md](/Users/lmsx/Documents/Playground/edu-media-openclaw/SKILL.md)：现有本地 skill 入口。
- [SOUL.md](/Users/lmsx/Documents/Playground/edu-media-openclaw/SOUL.md)：仓库级 Agent 行为基线。
- 现有 OpenClaw `main` agent、Feishu channel、Gemini 生图能力已经可用。

因此本次设计不重写外部集成层，重点新增“客户化模板层 + 状态机编排层”。

## Design Summary

本方案采用“客户化子模块 + 轻量编排层”：

- 客户差异沉淀到 `clients/wuhan-tutoring/` 目录。
- 业务状态机由新的 router 脚本维护。
- 6 个 `xhs-*` skills 只负责边界清晰的单一职责。
- 状态文件按飞书私聊 `open_id` 持久化。
- 素材池、本地风格模板和系统提示词构成长期约束。
- 现有文案、图片、飞书卡片链路继续复用，不另起一套平行实现。

## Scope

本次设计覆盖：

- 客户化目录结构
- 素材抓取与模板建立
- 5 状态状态机和前置素材闸门
- 6 个 Skill 的职责分工
- 系统提示词和状态摘要注入方式
- 本地状态文件结构
- 测试和验收顺序

本次设计不覆盖：

- 新建飞书 bot 或新建 OpenClaw 实例
- 多客户 profile 抽象
- 无人值守自动发布
- 对 Gemini 或 Feishu 基础配置做底层重构

## Directory Layout

新增目录如下：

```text
/Users/lmsx/Documents/Playground/edu-media-openclaw/
├── clients/
│   └── wuhan-tutoring/
│       ├── config/
│       │   └── workflow.yaml
│       ├── output/
│       │   └── sessions/
│       ├── prompts/
│       │   └── system-prompt.md
│       ├── references/
│       │   ├── article/
│       │   ├── images/
│       │   ├── source-index.json
│       │   ├── style-notes.md
│       │   ├── 文案风格指南.md
│       │   └── 图片风格模板.md
│       └── state/
│           └── feishu_dm/
├── skills/
│   └── xhs-edu-wuhan/
└── scripts/
    ├── xhs_customer_router.py
    ├── xhs_material_collector.py
    └── xhs_style_analyzer.py
```

设计原则：

- `clients/wuhan-tutoring/` 是本次客户化边界。
- `references/` 是素材事实层。
- `prompts/` 是长期行为约束层。
- `state/` 是运行态状态层。
- `output/` 是单次任务产物层。

## Materials Gate

业务状态机之外新增一个前置闸门：`materials_ready`。

规则如下：

- 当 `materials_ready=false` 时，系统不进入真实内容生成流。
- 此时允许的动作只有：
  - 收集素材
  - 汇总当前素材
  - 报告素材缺口
  - 生成或更新风格模板
- 当以下条件满足时，才能切换为 `materials_ready=true`：
  - `references/article/` 至少有 3 篇可解析样本
  - `references/images/` 至少有 3 张可用样本
  - `文案风格指南.md` 已生成
  - `图片风格模板.md` 已生成

采用这个闸门的原因是：仅靠在线账号主页不适合作为长期风格约束来源，必须先落成本地可复用样本，再进入稳定生产。

## Source Material Collection

默认素材池来自用户提供的 3 个小红书账号链接。系统默认先从这些公开账号抓取，不额外要求客户先手工上传文章和图片。

抓取流程：

1. 读取 3 个账号主页链接。
2. 抓取候选笔记列表与详情页。
3. 从中筛选 3 到 5 篇代表性内容保存到 `references/article/`。
4. 抽取 3 到 5 张代表性封面或讲解图保存到 `references/images/`。
5. 生成 `references/source-index.json`，记录原始链接、账号来源、抓取时间和用途标签。
6. 基于本地样本分析并产出风格模板。

补充原则：

- 如果默认素材池抓取失败或样本不足，再追加向客户索要人工素材。
- `style-notes.md` 保留为“客户口头偏好补充层”，但不是启动框架的前置依赖。

## Style Template Files

### 文案风格指南

文件路径：
[clients/wuhan-tutoring/references/文案风格指南.md](/Users/lmsx/Documents/Playground/edu-media-openclaw/clients/wuhan-tutoring/references/文案风格指南.md)

内容必须包括：

- 开头钩子写法
- 正文段落结构
- 结尾收束方式
- 常用词汇和语气
- 标签风格和数量
- CTA 偏好
- 禁止出现的表达

要求写成“可执行写作约束”，避免空泛审美判断。

### 图片风格模板

文件路径：
[clients/wuhan-tutoring/references/图片风格模板.md](/Users/lmsx/Documents/Playground/edu-media-openclaw/clients/wuhan-tutoring/references/图片风格模板.md)

内容必须包括：

- 主色调与背景风格
- 字体和花字倾向
- 构图方式
- 信息密度
- 封面图风格
- 正文配图风格
- 禁止出现的画面倾向

要求写成“可执行出图约束”，例如大标题布局、强调词高亮、信息块数量限制等。

## State Machine

业务状态严格保留 5 个：

### `state_0_topic`

- 触发：用户发送 `#选题 + 学科 + 关键词`，或发送学科/方向类自然语言请求。
- 输出：3 到 5 个备选选题。
- 每个备选项包含：
  - 标题候选
  - 核心角度
  - 预期标签
  - 竞品参考
- 退出条件：用户明确选择一个选题或明确指定方向。

### `state_1_copywriting`

- 进入条件：用户已明确确认选题。
- 输出：
  - 3 个标题候选
  - 800 到 1200 字正文
  - 5 到 8 个标签
  - 发布时间建议
- 正文必须按段落组织，每段有明确主题。
- 退出条件：用户明确确认文案。

### `state_2_cover`

- 进入条件：用户确认文案后，且用户提供底图或明确要求生成封面图。
- 输出：1 到 2 张封面图。
- 退出条件：用户明确确认封面图。

### `state_3_graphics`

- 进入条件：用户明确说“生成配图”或同义指令。
- 输出：2 到 3 张正文配图。
- 配图类型可包括：
  - 考点总结图
  - 文章脉络图
  - 思维导图
- 退出条件：用户明确确认配图。

### `state_4_done`

- 进入条件：用户确认配图后。
- 输出：
  - 完整文案
  - 图片文件路径或引用
  - 发布注意事项
- 支持在任意后续时点重复查看汇总。

## State Transition Rules

硬规则如下：

- 未确认时不得自动跳转到下一状态。
- 已确认内容默认锁定。
- 用户仅在明确指定时，才允许回退到上游状态。
- “汇总”是旁路指令，不改变状态。
- “重新来当前阶段”只重建当前阶段草稿，不清空上游已确认内容。
- “回到文案”会把当前状态设为 `state_1_copywriting`，保留已确认选题，废弃封面和配图草稿。

## Persistent State Storage

状态文件目录：
[clients/wuhan-tutoring/state/feishu_dm](/Users/lmsx/Documents/Playground/edu-media-openclaw/clients/wuhan-tutoring/state/feishu_dm)

主键采用飞书私聊 `open_id`。

单个状态文件结构如下：

```json
{
  "materials_ready": false,
  "current_state": "state_0_topic",
  "current_topic_id": null,
  "confirmed": {
    "topic": null,
    "title": null,
    "copywriting": null,
    "cover": null,
    "graphics": null
  },
  "drafts": {
    "topics": [],
    "copywriting": null,
    "cover_images": [],
    "graphic_images": []
  },
  "last_revision_scope": null,
  "last_user_intent": null,
  "session_output_dir": null,
  "updated_at": ""
}
```

约束如下：

- `confirmed` 只存已确认内容。
- `drafts` 只存当前阶段候选内容。
- 返工默认针对 `drafts` 或指定字段，不得隐式修改其他确认块。

## Skills

本次新增 6 个本地 Skill，目录位于 `~/.openclaw/skills/`，同时在仓库 `skills/xhs-edu-wuhan/` 中保留源文件和安装模板。

### `xhs-router`

职责：

- 读取当前私聊状态文件
- 识别用户意图
- 判断当前允许的动作
- 调度对应 skill 或脚本

不负责生成正文或图片。

### `xhs-topic`

职责：

- 根据学科和关键词生成备选选题
- 结合默认素材池与教育行业语境输出备选项

不负责正文生成。

### `xhs-writer`

职责：

- 根据已确认选题生成文案
- 处理标题级或段落级局部修改
- 强制引用 `文案风格指南.md`

### `xhs-image-cover`

职责：

- 根据底图、标题和核心信息构造封面图 prompt
- 调用现有 Gemini 生图链路生成封面图
- 强制引用 `图片风格模板.md`

### `xhs-image-graphic`

职责：

- 根据完整正文构造正文配图 prompt
- 调用现有 Gemini 生图链路生成配图
- 输出 2 到 3 张讲解图

### `xhs-feedback`

职责：

- 识别返工命令
- 将返工命令结构化为范围和操作类型
- 将结构化结果交回相应生成模块执行

`xhs-feedback` 不直接修改正文或图片，只输出结构化修改意图。

示例输出：

```json
{
  "target_state": "state_1_copywriting",
  "operation": "partial_update",
  "scope": {
    "type": "paragraph",
    "index": 2
  },
  "instruction": "第二段太啰嗦，压缩到更利落、更像家长能看完的表达"
}
```

## System Prompt Design

客户专用系统提示词文件位于：
[clients/wuhan-tutoring/prompts/system-prompt.md](/Users/lmsx/Documents/Playground/edu-media-openclaw/clients/wuhan-tutoring/prompts/system-prompt.md)

必须包含以下章节：

- 角色定位
- 工作流定义
- 各状态触发方式
- 用户确认规则
- 返工规则
- 风格引用
- 素材闸门
- 输出契约
- 禁止行为

设计原则：

- 系统提示词只放长期稳定规则。
- 当前轮状态信息由 router 以短摘要形式额外注入。

示例状态摘要：

```md
当前会话摘要：
- materials_ready: true
- current_state: state_1_copywriting
- confirmed.topic: 初三数学必考-二次函数题型全梳理
- confirmed.title: null
- confirmed.copywriting: null
- locked_sections: ["topic"]
- current_revision_scope: "title_only"
```

## Command Semantics

关键指令语义固定如下：

- “标题换一个”：只修改标题，不改正文。
- “文案第几段太啰嗦”：只修改指定段落。
- “封面图换个背景色”：只重出封面图，且仅调整背景。
- “配图要简洁一点”：只重出配图。
- “重新来当前阶段”：只重建当前阶段草稿。
- “回到文案”：回退到 `state_1_copywriting`。
- “汇总”：输出当前已生成内容快照，不改变状态。

## Customer Defaults Used For Scaffolding

以下是为了便于先落框架而采用的默认值，不代表客户已最终确认：

- 返工次数：默认不限次数
- 文案长度：默认 800 到 1200 字
- 配图风格：默认“专业、清晰、讲解导向”
- 封面花字：默认“模板化大字报风格”
- 发布时间：默认给出建议时段，由客户自行安排
- 发布提醒：默认关闭，后续可在 Feishu 中追加提醒能力

这些值允许后续在 `workflow.yaml` 中被客户确认结果覆盖。

## Scripts

### `scripts/xhs_customer_router.py`

职责：

- 统一入口
- 读取状态文件
- 注入状态摘要
- 调用相应 skill 或复用现有脚本

### `scripts/xhs_material_collector.py`

职责：

- 从默认小红书素材池抓取文章和图片
- 生成本地素材索引
- 写入 `references/`

### `scripts/xhs_style_analyzer.py`

职责：

- 分析 `references/article/`
- 分析 `references/images/`
- 生成风格模板文件
- 评估 `materials_ready`

### Existing Script Reuse

以下脚本继续复用，不整体重写：

- [scripts/xhs_feishu_flow.py](/Users/lmsx/Documents/Playground/edu-media-openclaw/scripts/xhs_feishu_flow.py)
- 现有 Gemini 生图相关脚本
- 现有 Feishu 客户端脚本

## Testing Strategy

验收重点如下：

1. 素材收集成功落地到本地目录
2. 素材未就绪时无法进入生产流
3. 5 状态链路只在明确确认后推进
4. 局部返工只影响指定范围
5. 飞书私聊跨轮次续跑仍能恢复正确状态

测试分三层：

### 离线验收

- 目录结构创建
- 状态文件读写
- 素材抓取与模板生成
- router 意图识别

### 半链路验收

- 模拟飞书消息
- 测试状态推进和返工
- 不依赖真实生图成功

### 真实链路验收

- 真实 Feishu 私聊跑一遍完整流程
- 至少覆盖一次确认推进
- 至少覆盖一次局部返工

## Implementation Order

推荐按以下顺序实施：

1. 创建客户目录、状态目录和 prompt 目录
2. 实现素材抓取脚本和风格分析脚本
3. 实现状态文件与 router
4. 编写 6 个 Skill 定义
5. 接入现有 `xhs_feishu_flow.py` 与生图链路
6. 完成端到端测试与修补

这个顺序优先解决最容易造成后续返工的部分：素材事实层和状态边界。

## Risks And Mitigations

### 小红书抓取不稳定

风险：

- 页面登录要求
- 反爬
- 页面结构变动

缓解：

- 先使用用户给定账号作为默认素材池
- 抓取失败时回退为向客户补充本地素材
- 素材一旦落地，本地模板不再依赖在线页面实时可用

### 状态错跳

风险：

- 模型根据历史“脑补”推进下一阶段

缓解：

- 使用本地状态文件作为主事实来源
- router 注入短状态摘要
- 在系统提示词中明确未确认不得推进

### 返工误伤

风险：

- 修改标题时误改正文
- 回到文案时误清空选题

缓解：

- `confirmed` 与 `drafts` 分离存储
- `xhs-feedback` 只生成结构化修改范围
- 生成模块只处理被授权字段

## Out Of Scope Follow-Up

后续仍需要和客户确认的业务项，但不阻塞本次框架搭建：

- 是否对返工次数做上限
- 是否明确偏好“简约 / 活泼 / 专业 / 插画”中的某一配图风格
- 是否明确偏好某种封面花字风格
- 发布时间是否要固定时段
- 内容完成后是否追加飞书提醒

当前设计已为这些业务项预留 `workflow.yaml` 和 `style-notes.md` 覆盖位。
