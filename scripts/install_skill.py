#!/usr/bin/env python3
"""把当前项目安装为本地 OpenClaw skill。

安装后，在飞书对话中说 "帮我做一个小红书笔记，主题是..." 即可触发。
流程会先发初稿审核卡；当前主按钮是通过 / 刷新封面图 / 刷新内容配图。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SKILL_TARGET_ROOT = Path(os.path.expanduser("~/.openclaw/skills"))
PROJECT_TARGET = SKILL_TARGET_ROOT / "edu-media-openclaw"
WUHAN_SKILL_SOURCE_ROOT = ROOT_DIR / "skills" / "xhs-edu-wuhan"
WUHAN_SKILL_NAMES = [
    "xhs-router",
    "xhs-topic",
    "xhs-writer",
    "xhs-image-cover",
    "xhs-image-graphic",
    "xhs-feedback",
]


def _replace_tree(source_dir: Path, target_dir: Path) -> None:
    if target_dir.exists() or target_dir.is_symlink():
        if target_dir.is_symlink() or target_dir.is_file():
            target_dir.unlink()
        else:
            shutil.rmtree(target_dir)
    shutil.copytree(source_dir, target_dir)


def install_project_wrapper() -> None:
    if PROJECT_TARGET.exists() or PROJECT_TARGET.is_symlink():
        if PROJECT_TARGET.is_symlink() or PROJECT_TARGET.is_file():
            PROJECT_TARGET.unlink()
        else:
            shutil.rmtree(PROJECT_TARGET)

    PROJECT_TARGET.mkdir(parents=True, exist_ok=True)

    source_skill = ROOT_DIR / "SKILL.md"
    target_skill = PROJECT_TARGET / "SKILL.md"
    shutil.copy2(str(source_skill), str(target_skill))


def install_wuhan_skills() -> list[Path]:
    installed: list[Path] = []
    SKILL_TARGET_ROOT.mkdir(parents=True, exist_ok=True)
    for skill_name in WUHAN_SKILL_NAMES:
        source_dir = WUHAN_SKILL_SOURCE_ROOT / skill_name
        target_dir = SKILL_TARGET_ROOT / skill_name
        _replace_tree(source_dir, target_dir)
        installed.append(target_dir)
    return installed


def main() -> None:
    install_project_wrapper()
    installed_wuhan_skills = install_wuhan_skills()

    print(f"✅ Skill 已安装到: {PROJECT_TARGET}")
    print(f"   来源: {ROOT_DIR / 'SKILL.md'}")
    print()
    print("✅ 已同步武汉客户 workflow skills：")
    for target_dir in installed_wuhan_skills:
        print(f"   - {target_dir}")
    print()
    print("📱 现在可以在飞书 @市场智能助手 说：")
    print('   "帮我做一个小红书笔记，主题是春季穿搭"')
    print()
    print("   OpenClaw 会先：")
    print("   1. AI 生成 3 版文案 + 标签")
    print("   2. 通过稳定文本后端 + Gemini 网页/底图模式生成审核素材")
    print("   3. 发送飞书初稿审核卡片")
    print("   4. 等你在卡片里点通过/刷新封面图/刷新内容配图后再继续")
    print()
    print("🧭 武汉客户化 workflow 也可通过本地 skills 单独复用。")


if __name__ == "__main__":
    main()
