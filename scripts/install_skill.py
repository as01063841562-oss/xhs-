#!/usr/bin/env python3
"""把当前项目安装为本地 OpenClaw skill。

安装后，在飞书对话中说 "帮我做一个小红书笔记，主题是..." 即可触发。
流程会先发带真实封面图的初稿审核卡；点修改/重写时会先打开修改说明卡，填写说明后再继续。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
TARGET = Path(os.path.expanduser("~/.openclaw/skills/edu-media-openclaw"))


def main() -> None:
    # 清理旧安装
    if TARGET.exists() or TARGET.is_symlink():
        if TARGET.is_symlink() or TARGET.is_file():
            TARGET.unlink()
        else:
            shutil.rmtree(TARGET)

    TARGET.mkdir(parents=True, exist_ok=True)

    # 直接复制项目中的 SKILL.md（已经包含完整触发指令和流程）
    source_skill = ROOT_DIR / "SKILL.md"
    target_skill = TARGET / "SKILL.md"
    shutil.copy2(str(source_skill), str(target_skill))

    print(f"✅ Skill 已安装到: {TARGET}")
    print(f"   来源: {source_skill}")
    print()
    print("📱 现在可以在飞书 @市场智能助手 说：")
    print('   "帮我做一个小红书笔记，主题是春季穿搭"')
    print()
    print("   OpenClaw 会先：")
    print("   1. AI 生成 3 版文案 + 标签")
    print("   2. 通过 Gemini CLI / 网页自动化生成真实封面图")
    print("   3. 发送飞书初稿审核卡片")
    print("   4. 等你在卡片里点通过/修改/重写后再继续（修改会先打开说明卡）")


if __name__ == "__main__":
    main()
