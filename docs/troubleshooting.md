# 排障手册

## 1. `llm_api 未配置完成`

- 检查 [config.yaml](/Users/lmsx/Documents/Playground/edu-media-openclaw/config/config.yaml)
- 补齐 `llm_api.base_url`、`llm_api.api_key`、`llm_api.model`
- 如果只是本机验证，先加 `--dry-run`

## 2. `image_api.api_key` 还是占位值

- 如果 `image_api.backend` 是 `gemini_web`，图片生成不会依赖外部图片 API Key
- 请确认以下条件都满足：
  - `browser_image.profile_dir` 指向已有 Gemini 登录态的 Chrome profile
  - `playwright` 已安装
  - 本机能启动 Chrome 并连上 `remote_debug_port`
- 如果只是联调，可先让脚本回退到占位图，再逐步切回真实生图

## 2.1 Gemini 网页生图失败

- 检查 `config/config.yaml` 里的 `image_api.backend` 是否为 `gemini_web`
- 检查 `browser_image.profile_dir` 是否存在且包含登录态
- 检查当前 Chrome 是否已经占用了同一个 profile，必要时先关掉旧实例
- 如果页面上按钮文案变化，先重启 OpenClaw / 浏览器自动化桥接再试

## 3. 公众号 token 获取失败

- 检查现有公众号 AppID / AppSecret
- 确认公众号后台 IP 白名单包含当前出口 IP
- 先运行：

```bash
.venv/bin/python scripts/check_env.py --write
```

### 当前机器已验证到的真实报错

微信接口返回：

```text
invalid ip 119.97.37.60, not in whitelist
```

如果继续在这台机器上联调，请先把当前出口 IP 加入公众号后台白名单。

## 4. 草稿箱推送失败

- 确认 `--publish-draft` 已传入
- 确认不是 `--dry-run`
- 检查 `config/config.yaml` 是否能继承到有效的公众号凭证

## 5. OpenClaw 找不到 skill

- 先安装：

```bash
.venv/bin/python scripts/install_skill.py
```

- 再运行：

```bash
openclaw skills list
```

## 6. 飞书卡片点了“修改 / 重写”但没继续

- 确认 OpenClaw / Feishu bridge 是最新代码
- 确认卡片按钮 value 里有 `action=xhs_review` 或 `decision=modify|rewrite`
- 确认卡片交互消息里带了 `source_message_id`、`card_message_id` 或 `reply_to_message_id`
- 如果还是没有回流，先重启 bridge，再点一次卡片按钮
