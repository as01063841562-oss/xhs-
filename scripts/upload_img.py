#!/usr/bin/env python3
"""
图片上传工具 - 上传图片到微信素材库
返回 mmbiz.qpic.cn URL
"""

import argparse
import os
import sys

# 添加 scripts 目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wx_api import upload_image_for_article, upload_thumb_image


def main():
    parser = argparse.ArgumentParser(description="上传图片到微信素材库")
    parser.add_argument("images", nargs="+", help="要上传的图片路径")
    parser.add_argument("--thumb", action="store_true",
                        help="作为永久素材上传（用于头图缩略图，返回 media_id）")

    args = parser.parse_args()

    for image_path in args.images:
        if not os.path.exists(image_path):
            print(f"❌ 文件不存在: {image_path}")
            continue

        try:
            if args.thumb:
                media_id = upload_thumb_image(image_path)
                print(f"✅ {os.path.basename(image_path)} → media_id: {media_id}")
            else:
                url = upload_image_for_article(image_path)
                print(f"✅ {os.path.basename(image_path)} → {url}")
        except Exception as e:
            print(f"❌ {os.path.basename(image_path)} 上传失败: {e}")


if __name__ == "__main__":
    main()
