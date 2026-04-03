#!/usr/bin/env python3
"""
风格管理器
- 加载/列出/切换三类风格（文风/配图/排版）
- 从范文/范图/范例 HTML 提炼风格（生成结构化 YAML）
- 管理多套风格
"""

import os
import sys
import yaml
import json

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STYLES_DIR = os.path.join(ROOT_DIR, "styles")
SAMPLES_DIR = os.path.join(ROOT_DIR, "samples")

# 风格类型定义
STYLE_TYPES = {
    "writing": {
        "name": "文风",
        "dir": os.path.join(STYLES_DIR, "writing"),
        "description": "文章写作风格",
    },
    "image": {
        "name": "配图风格",
        "dir": os.path.join(STYLES_DIR, "image"),
        "description": "配图生成风格",
    },
    "layout": {
        "name": "排版风格",
        "dir": os.path.join(STYLES_DIR, "layout"),
        "description": "文章排版样式",
    },
}


def list_styles(style_type):
    """
    列出某类型下所有可用风格（预置 + 用户自建）
    返回: list of dict, 每个包含 name, description, source(preset/custom), path
    """
    if style_type not in STYLE_TYPES:
        raise ValueError(f"未知风格类型: {style_type}，可选: {list(STYLE_TYPES.keys())}")

    base_dir = STYLE_TYPES[style_type]["dir"]
    presets_dir = os.path.join(base_dir, "_presets")
    styles = []

    # 预置风格
    if os.path.exists(presets_dir):
        for f in sorted(os.listdir(presets_dir)):
            if f.endswith(".yaml") and not f.startswith("_"):
                path = os.path.join(presets_dir, f)
                with open(path, "r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
                styles.append({
                    "name": f.replace(".yaml", ""),
                    "display_name": data.get("name", f),
                    "description": data.get("description", ""),
                    "source": "preset",
                    "path": path,
                })

    # 用户自建风格
    if os.path.exists(base_dir):
        for f in sorted(os.listdir(base_dir)):
            if f.endswith(".yaml") and not f.startswith("_"):
                path = os.path.join(base_dir, f)
                with open(path, "r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
                styles.append({
                    "name": f.replace(".yaml", ""),
                    "display_name": data.get("name", f),
                    "description": data.get("description", ""),
                    "source": "custom",
                    "path": path,
                })

    return styles


def load_style(style_type, style_name):
    """加载指定风格的完整配置"""
    if style_type not in STYLE_TYPES:
        raise ValueError(f"未知风格类型: {style_type}")

    base_dir = STYLE_TYPES[style_type]["dir"]

    # 先找用户自建
    path = os.path.join(base_dir, f"{style_name}.yaml")
    if not os.path.exists(path):
        # 再找预置
        path = os.path.join(base_dir, "_presets", f"{style_name}.yaml")
    if not os.path.exists(path):
        raise FileNotFoundError(f"找不到{STYLE_TYPES[style_type]['name']}: {style_name}")

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_style(style_type, style_name, style_data):
    """保存风格到用户自建目录"""
    if style_type not in STYLE_TYPES:
        raise ValueError(f"未知风格类型: {style_type}")

    base_dir = STYLE_TYPES[style_type]["dir"]
    os.makedirs(base_dir, exist_ok=True)

    path = os.path.join(base_dir, f"{style_name}.yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(style_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    return path


def delete_style(style_type, style_name):
    """删除用户自建风格（不能删预置）"""
    if style_type not in STYLE_TYPES:
        raise ValueError(f"未知风格类型: {style_type}")

    base_dir = STYLE_TYPES[style_type]["dir"]
    path = os.path.join(base_dir, f"{style_name}.yaml")

    if not os.path.exists(path):
        raise FileNotFoundError(f"找不到自建风格: {style_name}")

    os.remove(path)
    return True


def generate_writing_style_prompt(sample_texts):
    """
    生成用于让 AI 提炼文风的 prompt
    输入: 范文文本列表
    返回: 给 AI 的 prompt（AI 返回结构化 YAML）
    """
    schema_path = os.path.join(STYLES_DIR, "writing", "_schema.yaml")
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = f.read()

    samples = "\n\n---\n\n".join([f"【范文 {i+1}】\n{text}" for i, text in enumerate(sample_texts)])

    return f"""请分析以下范文的写作风格，并按照指定的 YAML 结构输出结构化的文风配置。

## YAML 结构要求：
```yaml
{schema}
```

## 范文内容：
{samples}

## 要求：
1. 仔细分析范文的语气、句式、结构、用词偏好
2. 提炼出可复用的风格规则
3. 输出完整的 YAML 配置（不要遗漏任何字段）
4. created_from 填 "sample"
5. samples 字段记录范文来源

请直接输出 YAML，不要其他解释。"""


def generate_image_style_prompt(sample_descriptions):
    """
    生成用于让 AI 提炼配图风格的 prompt
    输入: 对范图的描述列表（因为 AI 可能无法直接看图）
    返回: 给 AI 的 prompt
    """
    schema_path = os.path.join(STYLES_DIR, "image", "_schema.yaml")
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = f.read()

    samples = "\n\n".join([f"【范图 {i+1}】{desc}" for i, desc in enumerate(sample_descriptions)])

    return f"""请根据以下图片风格描述，生成结构化的配图风格配置 YAML。

## YAML 结构要求：
```yaml
{schema}
```

## 图片风格描述：
{samples}

## 要求：
1. 分析描述中的风格特征（色调、线条、元素、构图）
2. 生成可用于 AI 生图的 prompt 模板
3. 输出完整的 YAML 配置
4. created_from 填 "sample"

请直接输出 YAML，不要其他解释。"""


def generate_layout_style_prompt(sample_html):
    """
    生成用于让 AI 提炼排版风格的 prompt
    输入: 范例 HTML 内容
    返回: 给 AI 的 prompt
    """
    schema_path = os.path.join(STYLES_DIR, "layout", "_schema.yaml")
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = f.read()

    return f"""请分析以下公众号文章 HTML 的排版风格，并输出结构化的排版配置 YAML。

## YAML 结构要求：
```yaml
{schema}
```

## HTML 内容：
```html
{sample_html}
```

## 要求：
1. 分析 HTML 中的 inline style，提取字号、行高、颜色、间距等
2. 识别标题样式类型（centered_number / left_bar / bold_large / icon_prefix）
3. 提取高亮、引用、图片、CTA 卡片的样式
4. 输出完整的 YAML 配置
5. created_from 填 "sample"

请直接输出 YAML，不要其他解释。"""


def print_styles_table(style_type):
    """打印风格列表"""
    styles = list_styles(style_type)
    type_info = STYLE_TYPES[style_type]

    print(f"\n{'='*50}")
    print(f"📋 {type_info['name']}列表")
    print(f"{'='*50}")

    if not styles:
        print("  （暂无可用风格）")
        return

    for s in styles:
        source_tag = "📦" if s["source"] == "preset" else "✏️"
        print(f"  {source_tag} {s['name']:<20} {s['display_name']}")
        if s["description"]:
            print(f"     └─ {s['description']}")
    print()


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="风格管理器")
    sub = parser.add_subparsers(dest="command")

    # list 子命令
    list_cmd = sub.add_parser("list", help="列出可用风格")
    list_cmd.add_argument("type", choices=["writing", "image", "layout", "all"],
                          help="风格类型")

    # show 子命令
    show_cmd = sub.add_parser("show", help="查看风格详情")
    show_cmd.add_argument("type", choices=["writing", "image", "layout"])
    show_cmd.add_argument("name", help="风格名称")

    # extract 子命令
    extract_cmd = sub.add_parser("extract", help="从范文/范图/范例提炼风格（生成 prompt）")
    extract_cmd.add_argument("type", choices=["writing", "image", "layout"])
    extract_cmd.add_argument("samples", nargs="+", help="范文/范例文件路径")

    args = parser.parse_args()

    if args.command == "list":
        if args.type == "all":
            for t in STYLE_TYPES:
                print_styles_table(t)
        else:
            print_styles_table(args.type)

    elif args.command == "show":
        style = load_style(args.type, args.name)
        print(yaml.dump(style, allow_unicode=True, default_flow_style=False, sort_keys=False))

    elif args.command == "extract":
        texts = []
        for path in args.samples:
            if not os.path.exists(path):
                print(f"❌ 文件不存在: {path}")
                continue
            with open(path, "r", encoding="utf-8") as f:
                texts.append(f.read())

        if not texts:
            print("❌ 没有有效的样本文件")
            sys.exit(1)

        if args.type == "writing":
            prompt = generate_writing_style_prompt(texts)
        elif args.type == "image":
            prompt = generate_image_style_prompt(texts)
        elif args.type == "layout":
            prompt = generate_layout_style_prompt(texts[0])

        print("📝 以下 prompt 可以发给 AI 来提炼风格配置：")
        print("=" * 50)
        print(prompt)
        print("=" * 50)
        print("\n💡 把 AI 返回的 YAML 保存到对应的 styles/ 目录即可使用")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
