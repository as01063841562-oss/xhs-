# 教育自媒体 AI 自动化首期工程

本项目是首期可交付工作区。当前已经实跑并收口的主交付路径是：

- 小红书图文素材包生成
- 飞书审核卡片回流
- 客户底图模式下的刷新封面图 / 刷新内容配图 / 通过后最终稿卡片

公众号链路仍保留在仓库内，但只有在补齐真实 `wechat.app_secret` 后才算可直接交付。

整体原则是 `本机运行 + OpenClaw 调度 + 飞书交互 + 人工审核兜底`。

## 当前交付边界

- 已验收主路径：小红书 + Feishu 审核回流
- 小红书：生成 3 版文案、标签建议、封面标题、封面 prompt/封面图、发布检查清单
- 飞书：审核卡片、刷新封面图、刷新内容配图、最终稿卡片
- 公众号：代码在仓库里，但当前机器默认不宣称“真实可交付”
- 私域回复和视频高光处理只预留接口，不在首期实现

## 目录说明

```text
codex-wuhan-xhs-workflow/
├── SKILL.md                  # OpenClaw 本地 skill 入口
├── config/                   # 配置模板与本地配置
├── docs/                     # 交付文档、SOP、排障说明
├── logs/                     # 环境检查、冒烟测试、运行日志
├── output/                   # 每次任务的输出产物
├── scripts/                  # 任务脚本
├── styles/                   # 公众号文风/配图/封面/排版风格
└── requirements.txt          # Python 依赖
```

## 快速开始

### 1. 创建虚拟环境并安装依赖

```bash
PROJECT_ROOT="/Users/lmsx/.config/superpowers/worktrees/edu-media-openclaw/codex-wuhan-xhs-workflow"
cd "$PROJECT_ROOT"
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

### 2. 检查和补齐配置

项目默认读取：

- `$PROJECT_ROOT/config/config.yaml`
- 若配置里声明了 `inherit.wechat_config_path`，会先读取已有公众号 skill 配置，再由当前项目配置覆盖

建议先运行：

```bash
.venv/bin/python scripts/check_env.py --write
```

### 2.1 飞书凭证来源

参考 OpenClaw 的标准做法，飞书应用凭证优先从 `~/.openclaw/openclaw.json` 读取，项目配置只保留消息路由信息。

解析顺序如下：

1. `~/.openclaw/openclaw.json` 里的 `channels.feishu.appId` / `channels.feishu.appSecret`
2. `~/.openclaw/openclaw.json` 里的 `channels.feishu.accounts.<name>.appId` / `appSecret`
3. `config/config.yaml` 里的 `feishu.app_id` / `feishu.app_secret`，仅作为本地临时覆盖

如果你在 `openclaw.json` 里配置了多个飞书账号，可以通过环境变量 `OPENCLAW_FEISHU_ACCOUNT` 指定优先使用哪个账号。

项目配置里通常只需要：

```yaml
feishu:
  receive_id: "你的 open_id"
  receive_id_type: "open_id"
  api_base: "https://open.feishu.cn/open-apis"
```

### 2.2 切换后端

项目现在支持两类后端：

- 文本：`openai_compatible` 或 `gemini_cli`
- 生图：`gemini_web`（飞书流推荐）或 `gemini_cli`（仅在你已确认 CLI 能落盘图片时）

当前默认文本链路建议保持 `openai_compatible`，并优先从 `~/.openclaw/openclaw.json` 继承稳定配置。
如果你想强制改回本机 Gemini CLI，把 [config.yaml](/Users/lmsx/.config/superpowers/worktrees/edu-media-openclaw/codex-wuhan-xhs-workflow/config/config.yaml) 改成：

```yaml
llm_api:
  backend: "gemini_cli"

llm_cli:
  command: "/opt/homebrew/bin/gemini"
  model: "gemini-2.5-flash"
```

如果你想让飞书审核流走本机 Gemini 网页自动化（当前这条链路已验证可用），把配置里的 `gemini_image.backend` 保持或改成 `gemini_web`。

如果你明确要让配图走本机 Gemini 网页自动化，把配置改成：

```yaml
image_api:
  backend: "gemini_web"

browser_image:
  launcher: "open"
  chrome_app: "Google Chrome"
  profile_dir: "~/.openclaw/runtime/edu-media-openclaw/chrome-user-profile"
  source_profile_dir: "/Users/lmsx/Library/Application Support/Google/Chrome"
  remote_debug_port: 9227
  gemini_url: "https://gemini.google.com/app"
  launch_timeout: 90
  page_timeout: 180
```

说明：

- `openai_compatible` 是当前默认文本链路，优先用于真实文案生成
- `gemini_web` 适合飞书审核流的真实封面图输出
- `gemini_cli` 只建议在你已经确认它能真正落盘图片时再使用
- 这条生图链路复用你当前 Gemini 账号或 Chrome 登录态，不额外购买图片 API
- 如果文本或图片接口还没准备好，继续用 `--dry-run` 不会阻塞流程验证

### 2.3 OpenClaw / Feishu 回流前置

飞书卡片按钮回流不是单靠这个 Python 仓库完成的，还依赖本机 OpenClaw / Feishu bridge。

交付前必须确认：

1. `~/.openclaw/openclaw.json` 已配置可用的 `channels.feishu`
2. `openclaw status` 中 `Feishu` 为 `OK`
3. `.openclaw/extensions/openclaw-lark` 已经是支持 `refresh_cover / refresh_graphics` 的新语义
4. Chrome / Gemini 登录态可用（供 `gemini_web` 生图）

### 3. 公众号两阶段流程

先生成大纲，人工确认后再生成正文和草稿：

```bash
.venv/bin/python scripts/wechat_generate.py prepare \
  --topic "AI 自动化如何提升教育自媒体效率" \
  --audience "教育行业创始人和运营负责人"

.venv/bin/python scripts/wechat_generate.py produce \
  --task-dir output/wechat/<任务目录> \
  --outline-approved \
  --publish-draft
```

如果只是本机验证，不接真实接口：

```bash
.venv/bin/python scripts/wechat_generate.py full \
  --topic "AI 自动化如何提升教育自媒体效率" \
  --audience "教育行业创始人和运营负责人" \
  --dry-run \
  --outline-approved
```

### 4. 小红书素材包生成

```bash
.venv/bin/python scripts/xhs_generate.py \
  --topic "教培机构如何用 AI 节省内容运营时间" \
  --audience "校长和新媒体负责人" \
  --dry-run
```

如果要测试真实生图：

```bash
.venv/bin/python scripts/xhs_generate.py \
  --topic "教培机构如何用 AI 节省内容运营时间" \
  --audience "校长和新媒体负责人" \
  --render-cover
```

生图时会优先走本机 Chrome + Gemini 网页自动化，前提是：

- `browser_image.profile_dir` 里有可用的 Gemini 登录态
- `playwright` 已安装
- 本机能打开 Chrome 并连接远程调试端口

如果你是直接调用 `scripts/xhs_feishu_flow.py`，请把 `gemini_image.backend` 保持为 `gemini_web`。这样初稿和刷新封面图 / 刷新内容配图回流都会走同一条真实生图链路；只有你明确要实验 CLI 生图时，再单独切到 `gemini_cli`。历史卡片上的 `modify / rewrite` 仍然兼容，但新按钮已经改成刷新语义。

如果你要走当前最稳的客户交付路径，优先使用“客户底图模式”：

```bash
.venv/bin/python scripts/xhs_feishu_flow.py \
  --topic "测试｜客户底图模式终验" \
  --audience "武汉家长" \
  --base-image "/绝对路径/封面底图.jpg" \
  --graphic-base-image "/绝对路径/正文配图1.jpg" \
  --graphic-base-image "/绝对路径/正文配图2.jpg"
```

这条链路的特点：

- 文案走真实文本模型
- 封面和内容配图优先走本地底图叠版，不额外消耗 Gemini 生图额度
- 飞书卡片上的 `刷新封面图 / 刷新内容配图 / 通过` 已做过真实闭环验证

如果暂时还没打通文本模型，也可以直接注入本地生成好的素材包 JSON：

```bash
.venv/bin/python scripts/xhs_generate.py \
  --topic "教培机构如何用 AI 节省内容运营时间" \
  --payload-file /tmp/xhs_payload.json \
  --render-cover
```

### 5. 冒烟测试

```bash
.venv/bin/python scripts/smoke_test.py
```

### 5.1 武汉教培客户 workflow 自检

如果你只想验证武汉客户化路由，不必先走整条生成链路：

```bash
.venv/bin/python scripts/xhs_customer_router.py \
  --client wuhan-tutoring \
  --open-id ou_test_router \
  --message "汇总" \
  --dry-run
```

如果当前素材闸门还没打开，下面这条会返回 `materials_not_ready`，这是预期行为：

```bash
.venv/bin/python scripts/xhs_customer_router.py \
  --client wuhan-tutoring \
  --open-id ou_test_router \
  --message "#选题 数学 二次函数" \
  --dry-run
```

武汉客户的封面和内容配图提示词由 [clients/wuhan-tutoring/config/image_prompt_templates.yaml](/Users/lmsx/.config/superpowers/worktrees/edu-media-openclaw/codex-wuhan-xhs-workflow/clients/wuhan-tutoring/config/image_prompt_templates.yaml) 驱动，路由脚本会在 `state.image_templates.cover_template_key` 和 `state.image_templates.graphics_template_key` 里记录当前模板。要换封面或图文风格，优先改这个 YAML，比直接改脚本更稳。

### 5.2 武汉客户网页入口（第一期 MVP）

第一期网页入口采用 `FastAPI + Jinja2 + HTMX`，直接复用当前脚本和文件态状态机。

启动：

```bash
.venv/bin/python web/app.py --host 127.0.0.1 --port 8047
```

启动后终端会打印两条魔法链接：

- `Ops link` 进入运营端 `/ops`
- `Client link` 进入客户端 `/client`

这两个链接会把对应角色写进会话 cookie；token 本身保存在
`clients/wuhan-tutoring/state/web_access.json`，必要时可以重新启动服务生成新的访问串。

用法：

- 运营端从 `Ops link` 进入，看板里可以新建任务、开关素材闸门、推进阶段
- 客户端从 `Client link` 进入，可以查看任务、发起新任务、提交修改请求
- 两个页面都支持用 `account_key` 切换当前账号视图，创建任务时会沿用当前账号键

第一期定位：

- 单客户：只支持 `wuhan-tutoring`
- Feishu 是主控和审核确认结果的事实源
- 网页只做返工、可视化投影和运营操作台
- 底层生成链路继续复用现有脚本，不做重写

网页侧的任务记录会保留 `account_key` 作为未来多账号控制台的预留字段，但第一期仍按单账号默认值运行。

### 6. 安装为本地 OpenClaw skill

脚本会在 `~/.openclaw/skills/edu-media-openclaw` 下生成一个本地 wrapper skill，
并把武汉客户 workflow 的 6 个 source skill 同步到 `~/.openclaw/skills/`：

```bash
.venv/bin/python scripts/install_skill.py
```

安装后可在 OpenClaw 中直接引用本项目 skill，也可以单独复用：
- `xhs-router`
- `xhs-topic`
- `xhs-writer`
- `xhs-image-cover`
- `xhs-image-graphic`
- `xhs-feedback`

## 关键文件

- [SKILL.md](/Users/lmsx/.config/superpowers/worktrees/edu-media-openclaw/codex-wuhan-xhs-workflow/SKILL.md)
- [config.example.yaml](/Users/lmsx/.config/superpowers/worktrees/edu-media-openclaw/codex-wuhan-xhs-workflow/config/config.example.yaml)
- [check_env.py](/Users/lmsx/.config/superpowers/worktrees/edu-media-openclaw/codex-wuhan-xhs-workflow/scripts/check_env.py)
- [wechat_generate.py](/Users/lmsx/.config/superpowers/worktrees/edu-media-openclaw/codex-wuhan-xhs-workflow/scripts/wechat_generate.py)
- [xhs_generate.py](/Users/lmsx/.config/superpowers/worktrees/edu-media-openclaw/codex-wuhan-xhs-workflow/scripts/xhs_generate.py)
- [xhs_feishu_flow.py](/Users/lmsx/.config/superpowers/worktrees/edu-media-openclaw/codex-wuhan-xhs-workflow/scripts/xhs_feishu_flow.py)
- [smoke_test.py](/Users/lmsx/.config/superpowers/worktrees/edu-media-openclaw/codex-wuhan-xhs-workflow/scripts/smoke_test.py)

## 验收建议

- 先跑 `check_env.py`
- 再跑 `smoke_test.py`
- 然后做一次真实 `xhs_feishu_flow.py` 初稿
- 至少点一次飞书卡片上的 `刷新封面图` 或 `刷新内容配图`
- 最后点一次 `通过`，确认最终稿卡片已回到飞书
- 如果这次交付包含公众号，再额外补一次真实 draft push
