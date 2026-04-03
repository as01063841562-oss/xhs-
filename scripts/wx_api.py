#!/usr/bin/env python3
"""
微信公众号 API 封装
- access_token 自动获取和缓存（2小时有效期）
- 图片上传到素材库
- 草稿管理
- 不走代理直连微信 API
"""

import json
import os
import time
import requests
import yaml

# 配置文件路径（相对于项目根目录）
CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
TOKEN_CACHE_FILE = os.path.join(CONFIG_DIR, ".token_cache.json")


def load_config():
    """加载主配置文件"""
    config_path = os.path.join(CONFIG_DIR, "config.yaml")
    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"配置文件不存在: {config_path}\n"
            f"请复制 config.example.yaml 为 config.yaml 并填入你的信息"
        )
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_wechat_config():
    """获取微信公众号配置"""
    config = load_config()
    wechat = config.get("wechat", {})
    if not wechat.get("app_id") or not wechat.get("app_secret"):
        raise ValueError("请在 config/config.yaml 中配置 wechat.app_id 和 wechat.app_secret")
    return wechat


def get_access_token(force_refresh=False):
    """
    获取 access_token，自动缓存
    微信 access_token 有效期 7200 秒（2小时），提前 300 秒刷新
    """
    # 尝试从缓存读取
    if not force_refresh and os.path.exists(TOKEN_CACHE_FILE):
        try:
            with open(TOKEN_CACHE_FILE, "r") as f:
                cache = json.load(f)
            if cache.get("expires_at", 0) > time.time() + 300:
                return cache["access_token"]
        except (json.JSONDecodeError, KeyError):
            pass

    # 请求新 token
    wechat = get_wechat_config()
    url = "https://api.weixin.qq.com/cgi-bin/token"
    params = {
        "grant_type": "client_credential",
        "appid": wechat["app_id"],
        "secret": wechat["app_secret"],
    }

    # 微信 API 不走代理
    resp = requests.get(url, params=params, timeout=10,
                        proxies={"http": None, "https": None})
    resp.raise_for_status()
    data = resp.json()

    if "access_token" not in data:
        raise Exception(f"获取 access_token 失败: {data}")

    # 缓存 token
    cache = {
        "access_token": data["access_token"],
        "expires_at": time.time() + data.get("expires_in", 7200),
    }
    os.makedirs(os.path.dirname(TOKEN_CACHE_FILE), exist_ok=True)
    with open(TOKEN_CACHE_FILE, "w") as f:
        json.dump(cache, f)

    return data["access_token"]


def upload_image(image_path):
    """
    上传图片到微信素材库（临时素材）
    返回 media_id 和 url
    """
    token = get_access_token()
    url = f"https://api.weixin.qq.com/cgi-bin/media/upload?access_token={token}&type=image"

    with open(image_path, "rb") as f:
        files = {"media": (os.path.basename(image_path), f, "image/png")}
        resp = requests.post(url, files=files, timeout=30,
                             proxies={"http": None, "https": None})

    resp.raise_for_status()
    data = resp.json()

    if "media_id" not in data:
        raise Exception(f"上传图片失败: {data}")

    return data


def upload_image_for_article(image_path):
    """
    上传图片到微信（用于文章内的图片）
    返回 url（mmbiz.qpic.cn 格式）
    """
    token = get_access_token()
    url = f"https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token={token}"

    with open(image_path, "rb") as f:
        files = {"media": (os.path.basename(image_path), f, "image/png")}
        resp = requests.post(url, files=files, timeout=30,
                             proxies={"http": None, "https": None})

    resp.raise_for_status()
    data = resp.json()

    if "url" not in data:
        raise Exception(f"上传文章图片失败: {data}")

    return data["url"]


def upload_thumb_image(image_path):
    """
    上传永久素材（用于头图缩略图）
    返回 media_id
    """
    token = get_access_token()
    url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={token}&type=image"

    with open(image_path, "rb") as f:
        files = {"media": (os.path.basename(image_path), f, "image/png")}
        resp = requests.post(url, files=files, timeout=30,
                             proxies={"http": None, "https": None})

    resp.raise_for_status()
    data = resp.json()

    if "media_id" not in data:
        raise Exception(f"上传缩略图失败: {data}")

    return data["media_id"]


def add_draft(title, content, thumb_media_id, author="", digest=""):
    """
    添加草稿
    """
    token = get_access_token()
    url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}"

    article = {
        "title": title,
        "author": author,
        "digest": digest,
        "content": content,
        "thumb_media_id": thumb_media_id,
        "content_source_url": "",
        "need_open_comment": 0,
    }

    data = {"articles": [article]}
    # 必须用 ensure_ascii=False，否则中文变成 \uXXXX 微信会乱码
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    resp = requests.post(url, data=payload, headers=headers, timeout=30,
                         proxies={"http": None, "https": None})
    resp.raise_for_status()
    result = resp.json()

    if "media_id" not in result:
        raise Exception(f"推送草稿失败: {result}")

    return result


def add_draft_multi(articles):
    """
    添加多条草稿（头条+次条+三条...）
    articles: list of dict，每个包含 title, content, thumb_media_id, author, digest
    """
    token = get_access_token()
    url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}"

    formatted = []
    for art in articles:
        formatted.append({
            "title": art["title"],
            "author": art.get("author", ""),
            "digest": art.get("digest", ""),
            "content": art["content"],
            "thumb_media_id": art["thumb_media_id"],
            "content_source_url": art.get("content_source_url", ""),
            "need_open_comment": 0,
        })

    data = {"articles": formatted}
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    resp = requests.post(url, data=payload, headers=headers, timeout=30,
                         proxies={"http": None, "https": None})
    resp.raise_for_status()
    result = resp.json()

    if "media_id" not in result:
        raise Exception(f"推送多条草稿失败: {result}")

    return result


if __name__ == "__main__":
    # 测试 access_token 获取
    try:
        token = get_access_token()
        print(f"✅ access_token 获取成功: {token[:20]}...")
    except Exception as e:
        print(f"❌ 失败: {e}")
