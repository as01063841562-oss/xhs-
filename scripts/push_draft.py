#!/usr/bin/env python3
"""
草稿箱推送工具
将文章推送到公众号草稿箱
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wx_api import add_draft, add_draft_multi, upload_thumb_image, load_config


def main():
    parser = argparse.ArgumentParser(description="推送文章到公众号草稿箱")
    parser.add_argument("--title", required=True, help="文章标题")
    parser.add_argument("--file", required=True, help="HTML 文章文件路径")
    parser.add_argument("--thumb", required=True, help="头图图片路径")
    parser.add_argument("--author", default="", help="作者名")
    parser.add_argument("--digest", default="", help="文章摘要")

    args = parser.parse_args()

    # 检查文件
    if not os.path.exists(args.file):
        print(f"❌ 文章文件不存在: {args.file}")
        sys.exit(1)
    if not os.path.exists(args.thumb):
        print(f"❌ 头图文件不存在: {args.thumb}")
        sys.exit(1)

    # 读取默认作者
    if not args.author:
        config = load_config()
        args.author = config.get("article", {}).get("author", "")

    # 读取文章内容
    with open(args.file, "r", encoding="utf-8") as f:
        content = f.read()

    # 上传头图获取 media_id
    print(f"📤 上传头图: {args.thumb}")
    thumb_media_id = upload_thumb_image(args.thumb)
    print(f"✅ 头图 media_id: {thumb_media_id}")

    # 推送草稿
    print(f"📝 推送草稿: {args.title}")
    result = add_draft(
        title=args.title,
        content=content,
        thumb_media_id=thumb_media_id,
        author=args.author,
        digest=args.digest,
    )
    print(f"✅ 推送成功! media_id: {result['media_id']}")


if __name__ == "__main__":
    main()
