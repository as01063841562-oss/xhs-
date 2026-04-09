# 武汉教培 Workflow Web Product Design

## Goal

在现有 `edu-media-openclaw` 仓库内，为武汉教培客户新增一套单客户网页入口，用来把当前小红书 workflow 产品化验证。第一期目标不是平台化，而是尽快把“运营主控 + 客户协作 + 现有脚本链路”跑通。

## Confirmed Scope

- 只服务 `wuhan-tutoring` 单客户。
- 首页形态是工作流看板。
- 运营侧是主控界面。
- 客户会高频使用网页。
- 登录第一期采用 magic-link 风格的 tokenized access link。
- 第一阶段直接接现有真实脚本链路，不重写底层生成引擎。
- Feishu 继续承担通知和兜底确认通道，不被网页完全替代。

## Product Shape

第一期采用“双面工作流产品”：

- `运营端 /ops`
  - 查看全部任务和阶段状态
  - 触发选题、文案、封面、配图的真实链路
  - 查看脚本结果、Feishu 审核卡状态、错误日志
- `客户端 /client`
  - 查看任务列表和当前阶段产物
  - 发起新任务
  - 提交确认、修改、重跑请求
- `任务详情 /tasks/{task_id}`
  - 统一展示阶段时间线、已确认内容、当前草稿、操作历史、Feishu 关联信息

## Architecture

第一期采用“薄壳产品化”：

- 新增轻量 Python Web 服务作为编排层
- 继续复用现有脚本：
  - `scripts/xhs_customer_router.py`
  - `scripts/xhs_feishu_flow.py`
  - `scripts/xhs_material_collector.py`
  - `scripts/xhs_style_analyzer.py`
- 继续复用本地文件作为事实源：
  - `clients/wuhan-tutoring/state/`
  - `clients/wuhan-tutoring/references/`
  - `output/xhs_feishu/`

## Tech Choice

第一期采用 `FastAPI + Jinja2 + HTMX`：

- Python 侧集成现有脚本最直接
- 不新建 Node 前端工程
- 够用的交互能力可以覆盖看板、任务详情、按钮触发、轮询刷新

## Data Model

新增一个轻量任务注册表，任务记录字段至少包括：

- `task_id`
- `client_slug`
- `role_owner`
- `title`
- `topic`
- `audience`
- `open_id`
- `current_state`
- `materials_ready`
- `status`
- `session_output_dir`
- `review_message_id`
- `client_change_request`
- `last_error`
- `created_at`
- `updated_at`

单任务的运行态仍由现有 state / review_state / result 文件补充。

## Auth Model

第一期不做完整账号体系，采用 tokenized magic-link 风格：

- 维护一个本地 `web_access.json`
- 至少包含一个 `ops` token 和一个 `client` token
- `GET /magic-link?token=...` 成功后写入 session cookie
- 页面按 session role 决定可见操作

## Workflow Mapping

网页动作和现有状态机映射如下：

- 新建任务 -> 创建任务记录 + 初始化 synthetic `open_id`
- 生成选题 -> router `topic_request`
- 选定选题 -> router `selection_or_confirmation`
- 生成文案 -> router / payload generator
- 确认文案 -> router `confirm_copywriting`
- 生成封面 -> router `cover_request`
- 确认封面 -> router `confirm_cover`
- 生成配图 -> router `graphic_request`
- 确认配图 -> router `confirm_graphics`

客户的“修改”和“重跑请求”第一期可以先记为任务事件，并由运营端显式执行对应动作。

## Non-Goals

- 多客户平台
- 数据库和复杂权限系统
- 完整替代 Feishu
- 自动发布闭环
- WebSocket 实时更新

## Verification Goal

第一期完成标准：

- 运营端和客户端都能打开网页并进入各自视图
- 可以创建任务并看到阶段推进
- 可以从网页触发真实脚本链路
- 可以在网页中读取并展示 Feishu 审核卡状态
- 至少一条武汉客户任务能从网页发起并推进到封面/配图/完成链路
