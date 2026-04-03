#!/usr/bin/env python3
"""飞书 API 客户端 — 封装 token 获取、图片上传、卡片消息发送。"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import config_state, is_placeholder, load_config, resolve_feishu_credentials


class FeishuConfigError(RuntimeError):
    """Raised when Feishu credentials or routing config are missing."""


class FeishuClient:
    """飞书 API 客户端，Token 自动刷新（2 小时有效期）。"""

    def __init__(self, config: dict[str, Any] | None = None):
        if config is None:
            config = load_config()
        feishu_cfg = config.get("feishu", {})
        resolved = resolve_feishu_credentials(feishu_cfg)
        self.app_id = resolved.get("app_id")
        self.app_secret = resolved.get("app_secret")
        self.credentials_source = resolved.get("source", "missing")
        self.receive_id = (
            feishu_cfg.get("receive_id")
            or feishu_cfg.get("receiveId")
        )
        self.receive_id_type = feishu_cfg.get("receive_id_type") or feishu_cfg.get("receiveIdType") or "open_id"
        self.api_base = feishu_cfg.get("api_base") or feishu_cfg.get("apiBase") or "https://open.feishu.cn/open-apis"
        self._token: str | None = None
        self._token_expires_at: float = 0

        if config_state(self.app_id) != "ready" or config_state(self.app_secret) != "ready":
            raise FeishuConfigError(
                "飞书 appId/appSecret 未配置。请优先在 ~/.openclaw/openclaw.json 中提供可用凭证，或在 config/config.yaml 中临时覆盖。"
            )
        if is_placeholder(self.receive_id) or not self.receive_id:
            raise FeishuConfigError(
                "飞书 receive_id 未配置。请在 config/config.yaml 中设置要接收消息的 open_id。"
            )

    # ── Token 管理 ─────────────────────────────────────────────

    def get_token(self) -> str:
        """获取 tenant_access_token，自动缓存。"""
        now = time.time()
        if self._token and now < self._token_expires_at - 60:
            return self._token

        url = f"{self.api_base}/auth/v3/tenant_access_token/internal"
        resp = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"获取飞书 Token 失败: {data}")
        self._token = data["tenant_access_token"]
        self._token_expires_at = now + data.get("expire", 7200)
        return self._token

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.get_token()}"}

    # ── 图片上传 ───────────────────────────────────────────────

    def upload_image(self, image_path: str | Path) -> str:
        """上传图片到飞书，返回 image_key。"""
        url = f"{self.api_base}/im/v1/images"
        with open(image_path, "rb") as f:
            resp = requests.post(
                url,
                headers=self._auth_headers(),
                files={"image": f},
                data={"image_type": "message"},
                timeout=30,
            )
        resp.raise_for_status()
        data = resp.json()
        image_key = data.get("data", {}).get("image_key")
        if not image_key:
            raise RuntimeError(f"上传图片失败: {data}")
        return image_key

    def upload_images(self, image_paths: list[str | Path]) -> list[str]:
        """批量上传图片到飞书，返回 image_key 列表。"""
        keys = []
        for path in image_paths:
            key = self.upload_image(path)
            keys.append(key)
        return keys

    # ── 发送消息 ───────────────────────────────────────────────

    def _send_message(self, msg_type: str, content: str | dict) -> str:
        """通用发送消息方法，返回 message_id。"""
        url = f"{self.api_base}/im/v1/messages?receive_id_type={self.receive_id_type}"
        content_str = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        payload = {
            "receive_id": self.receive_id,
            "msg_type": msg_type,
            "content": content_str,
        }
        resp = requests.post(
            url,
            headers={**self._auth_headers(), "Content-Type": "application/json"},
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        message_id = data.get("data", {}).get("message_id")
        if not message_id:
            raise RuntimeError(f"发送消息失败: {data}")
        return message_id

    def send_text(self, text: str) -> str:
        """发送纯文本消息。"""
        return self._send_message("text", json.dumps({"text": text}))

    def send_image(self, image_key: str) -> str:
        """发送图片消息。"""
        return self._send_message("image", json.dumps({"image_key": image_key}))

    def send_review_card(
        self,
        image_key: str | list[str],
        title: str,
        content: str,
        tags: str,
        note_id: str = "note1",
        template: str = "blue",
    ) -> str:
        """📋 审核卡片 — 带 ✅通过 / ✏️修改 / ❌重写 按钮。

        image_key 可以是单个字符串或列表（多图模式）。
        按钮 value 使用结构化对象，方便 card.action.trigger 回流时解析。
        """
        # 构建图片元素（支持多图）
        image_keys = image_key if isinstance(image_key, list) else [image_key]
        image_elements = []
        for i, key in enumerate(image_keys):
            label = f"图{i+1}" if len(image_keys) > 1 else "封面图"
            image_elements.append({
                "tag": "img",
                "img_key": key,
                "alt": {"tag": "plain_text", "content": label},
            })

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": template,
                "title": {"tag": "plain_text", "content": title},
            },
            "elements": [
                *image_elements,
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": content},
                },
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [{"tag": "plain_text", "content": tags}],
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "✅ 通过"},
                            "type": "primary",
                            "value": {
                                "action": "xhs_review",
                                "decision": "approve",
                                "note_id": note_id,
                            },
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "✏️ 修改"},
                            "type": "default",
                            "value": {
                                "action": "xhs_review",
                                "decision": "modify",
                                "note_id": note_id,
                            },
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "❌ 重写"},
                            "type": "default",
                            "value": {
                                "action": "xhs_review",
                                "decision": "rewrite",
                                "note_id": note_id,
                            },
                        },
                    ],
                },
            ],
        }
        return self._send_message("interactive", card)

    def send_revision_request_card(
        self,
        image_key: str,
        title: str,
        content: str,
        tags: str,
        note_id: str = "note1",
        revision_mode: str = "modify",
        template: str = "blue",
    ) -> str:
        """✏️ 修改说明卡 — 先收集修改意见，再进入重新生成。

        这个卡片会展示当前版本，并提供一个修改说明输入框，避免“修改”按钮
        直接变成无条件重生成。
        """
        mode_label = "修改" if revision_mode == "modify" else "重写"
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": template,
                "title": {"tag": "plain_text", "content": f"✏️ {mode_label}说明 — {title}"},
            },
            "elements": [
                {
                    "tag": "img",
                    "img_key": image_key,
                    "alt": {"tag": "plain_text", "content": "封面图"},
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**当前版本预览：**\n{content}\n\n"
                            f"**当前标签：** {tags}\n\n"
                            "请在下方填写你希望调整的地方。"
                        ),
                    },
                },
                {"tag": "hr"},
                {
                    "tag": "form",
                    "elements": [
                        {
                            "tag": "input",
                            "name": "revision_notes",
                            "input_type": "multiline_text",
                            "label": {
                                "tag": "plain_text",
                                "content": f"{mode_label}说明",
                            },
                            "placeholder": {
                                "tag": "plain_text",
                                "content": "例如：封面标题再聚焦一点，正文开头更口语化，保留原来的三个卖点",
                            },
                        },
                        {
                            "tag": "button",
                            "name": "submit_revision",
                            "type": "primary",
                            "action_type": "form_submit",
                            "text": {"tag": "plain_text", "content": f"确认并{mode_label}"},
                            "value": {
                                "action": "xhs_review",
                                "decision": revision_mode,
                                "note_id": note_id,
                                "step": "submit_revision",
                            },
                        },
                        {
                            "tag": "button",
                            "name": "cancel_revision",
                            "type": "default",
                            "text": {"tag": "plain_text", "content": "先不改了"},
                            "value": {
                                "action": "xhs_review_cancel",
                                "decision": "cancel",
                                "note_id": note_id,
                            },
                        },
                    ],
                },
            ],
        }
        return self._send_message("interactive", card)

    def send_final_card(
        self,
        image_key: str,
        title: str,
        full_content: str,
        tags: str,
        template: str = "green",
    ) -> str:
        """✅ 最终稿卡片 — 带 🍠发布到小红书按钮。"""
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": template,
                "title": {"tag": "plain_text", "content": f"✅ 最终稿：{title}"},
            },
            "elements": [
                {
                    "tag": "img",
                    "img_key": image_key,
                    "alt": {"tag": "plain_text", "content": "封面图"},
                },
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": full_content},
                },
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [{"tag": "plain_text", "content": tags}],
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "🍠 发布到小红书"},
                            "type": "primary",
                            "multi_url": {
                                "url": "https://creator.xiaohongshu.com",
                                "android_url": "xhsdiscover://",
                                "ios_url": "xhsdiscover://",
                            },
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "📋 复制文案"},
                            "type": "default",
                            "value": {"action": "xhs_copy_content"},
                        },
                    ],
                },
            ],
        }
        return self._send_message("interactive", card)


# ── 自测入口 ──────────────────────────────────────────────────

def _selftest():
    """快速测试飞书连通性。"""
    print("🧪 飞书客户端自测")
    client = FeishuClient()

    print("  1/3 获取 Token...")
    token = client.get_token()
    print(f"  ✅ Token: {token[:12]}...")

    print("  2/3 发送文本消息...")
    mid = client.send_text("🧪 飞书客户端自测消息 — 来自 edu-media-openclaw")
    print(f"  ✅ 消息 ID: {mid}")

    print("  3/3 完成 ✅")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="运行自测")
    args = parser.parse_args()
    if args.test:
        _selftest()
    else:
        parser.print_help()
