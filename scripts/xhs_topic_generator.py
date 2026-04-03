#!/usr/bin/env python3
"""武汉本地教育选题生成器。

提供各学科预设选题库 + AI 动态选题能力。
"""

from __future__ import annotations
import random
from typing import Any

# ── 武汉本地教育选题库 ──────────────────────────────────────

WUHAN_TOPICS: dict[str, list[dict[str, Any]]] = {
    "数学": [
        {
            "title": "武汉中考数学近3年压轴题型汇总",
            "subtitle": "函数+几何综合一网打尽",
            "audience": "初三学生家长",
            "style": "data_table",
            "tags": ["武汉中考", "数学压轴题", "函数", "几何综合", "考点汇总", "初三冲刺", "中考数学", "武汉家长"],
            "data_content": {
                "table_title": "武汉中考数学压轴题型分布(2023-2025)",
                "headers": ["年份", "题号", "题型", "考点", "难度"],
                "rows": [
                    ["2025", "22题", "函数综合", "二次函数+几何", "★★★★★"],
                    ["2025", "23题", "几何证明", "圆+相似三角形", "★★★★☆"],
                    ["2024", "22题", "函数综合", "一次函数+面积", "★★★★★"],
                    ["2024", "23题", "动点问题", "坐标系+最值", "★★★★★"],
                    ["2023", "22题", "二次函数", "抛物线+直线", "★★★★☆"],
                    ["2023", "23题", "几何综合", "圆+切线", "★★★★★"],
                ],
            },
        },
        {
            "title": "初三数学必考：二次函数题型全梳理",
            "subtitle": "掌握这些题型轻松拿高分",
            "audience": "初三学生家长",
            "style": "info_card",
            "tags": ["二次函数", "中考数学", "武汉中考", "题型梳理", "数学提分", "初三必备", "考前冲刺", "武汉家长"],
            "key_points": [
                "顶点式与一般式互换",
                "图象平移与对称",
                "与一次函数联立求交点",
                "面积最值问题",
                "实际应用（利润最大化）",
                "动点+二次函数综合",
            ],
        },
        {
            "title": "武汉四调vs元调数学考点对比",
            "subtitle": "哪个更接近中考真题？",
            "audience": "初三学生家长",
            "style": "comparison",
            "tags": ["四调", "元调", "武汉中考", "考点对比", "数学备考", "初三", "模考分析", "武汉家长"],
            "compare_data": {
                "left_title": "元调",
                "right_title": "四调",
                "items": [
                    {"label": "考试时间", "left": "1月（初三上期末）", "right": "4月（综合模考）"},
                    {"label": "难度", "left": "中等偏上", "right": "接近中考"},
                    {"label": "范围", "left": "初三上全部内容", "right": "初中全部内容"},
                    {"label": "参考价值", "left": "定位薄弱点", "right": "预估中考分数"},
                ],
            },
        },
    ],
    "英语": [
        {
            "title": "武汉中考英语阅读高频话题TOP10",
            "subtitle": "近3年真题统计",
            "audience": "初三学生家长",
            "style": "data_table",
            "tags": ["武汉中考", "英语阅读", "高频话题", "阅读理解", "英语备考", "初三冲刺", "武汉家长", "中考英语"],
            "data_content": {
                "table_title": "武汉中考英语阅读理解高频话题(近3年)",
                "headers": ["排名", "话题类别", "出现频次", "典型题型"],
                "rows": [
                    ["1", "科技与创新", "8次", "细节理解+主旨大意"],
                    ["2", "文化与传统", "7次", "推理判断+词义猜测"],
                    ["3", "环保与自然", "6次", "细节理解+观点态度"],
                    ["4", "健康与运动", "5次", "主旨大意+推理判断"],
                    ["5", "人物传记", "5次", "细节理解+推理判断"],
                    ["6", "社会热点", "4次", "观点态度+主旨大意"],
                    ["7", "校园生活", "4次", "细节理解"],
                    ["8", "旅行与地理", "3次", "细节理解+推理判断"],
                ],
            },
        },
        {
            "title": "武汉中考英语作文万能模板",
            "subtitle": "附历年真题范文",
            "audience": "初三学生家长",
            "style": "info_card",
            "tags": ["英语作文", "万能模板", "武汉中考", "英语写作", "中考英语", "作文模板", "初三备考", "武汉家长"],
            "key_points": [
                "开头段：引出话题+表明观点",
                "中间段：分点论述(First/Second/Third)",
                "结尾段：总结+呼吁",
                "高分句型：It is widely believed...",
                "连接词：However/Moreover/In addition",
                "真题演练：2025年「我的成长故事」",
            ],
        },
    ],
    "语文": [
        {
            "title": "武汉中考语文必背古诗文64篇",
            "subtitle": "默写易错字整理",
            "audience": "初中学生家长",
            "style": "info_card",
            "tags": ["古诗文", "默写", "武汉中考", "语文", "必背篇目", "易错字", "中考语文", "武汉家长"],
            "key_points": [
                "《出师表》易错：\"裨补阙漏\"的\"阙\"",
                "《岳阳楼记》：\"浩浩汤汤\"的\"汤\"读shāng",
                "《醉翁亭记》：\"觥筹交错\"的\"觥\"",
                "《鱼我所欲也》：\"蹴尔而与之\"",
                "《送东阳马生序》：\"媵人持汤沃灌\"",
                "《茅屋为秋风所破歌》全篇高频考",
            ],
        },
        {
            "title": "中考语文阅读理解答题模板",
            "subtitle": "记叙文+说明文万能公式",
            "audience": "初中学生家长",
            "style": "comparison",
            "tags": ["阅读理解", "答题模板", "记叙文", "说明文", "中考语文", "武汉中考", "语文提分", "武汉家长"],
            "compare_data": {
                "left_title": "记叙文",
                "right_title": "说明文",
                "items": [
                    {"label": "中心把握", "left": "人物+事件+情感", "right": "说明对象+特征"},
                    {"label": "结构分析", "left": "起因→经过→结果", "right": "总分/总分总/递进"},
                    {"label": "手法分析", "left": "修辞+描写+抒情", "right": "举例/列数字/作比较"},
                    {"label": "答题模板", "left": "运用了...手法，写出了...，表达了...", "right": "运用了...方法，说明了...，使..."},
                ],
            },
        },
    ],
    "物理": [
        {
            "title": "武汉中考物理实验题必考6大类型",
            "subtitle": "实验操作+数据分析全攻略",
            "audience": "初三学生家长",
            "style": "info_card",
            "tags": ["物理实验", "中考物理", "武汉中考", "实验题", "物理提分", "初三备考", "武汉家长", "实验操作"],
            "key_points": [
                "测量密度（天平+量筒）",
                "探究欧姆定律（滑动变阻器）",
                "测量小灯泡电功率",
                "探究杠杆平衡条件",
                "光的折射/反射实验",
                "凸透镜成像规律",
            ],
        },
        {
            "title": "初中物理公式大全",
            "subtitle": "力学+电学+光学一图搞定",
            "audience": "初中学生家长",
            "style": "data_table",
            "tags": ["物理公式", "初中物理", "力学", "电学", "光学", "公式大全", "中考物理", "武汉家长"],
            "data_content": {
                "table_title": "初中物理核心公式速查表",
                "headers": ["分类", "公式", "含义", "单位"],
                "rows": [
                    ["力学", "F=ma", "牛顿第二定律", "N=kg·m/s²"],
                    ["力学", "p=F/S", "压强", "Pa=N/m²"],
                    ["力学", "W=Fs", "功", "J=N·m"],
                    ["电学", "I=U/R", "欧姆定律", "A=V/Ω"],
                    ["电学", "P=UI", "电功率", "W=V·A"],
                    ["光学", "1/f=1/u+1/v", "透镜公式", "m"],
                ],
            },
        },
    ],
    "化学": [
        {
            "title": "初三化学方程式全整理",
            "subtitle": "中考必背版·按反应类型分类",
            "audience": "初三学生家长",
            "style": "info_card",
            "tags": ["化学方程式", "初三化学", "中考化学", "武汉中考", "必背", "反应类型", "化学提分", "武汉家长"],
            "key_points": [
                "化合反应：2H₂+O₂→2H₂O",
                "分解反应：2KMnO₄→K₂MnO₄+MnO₂+O₂↑",
                "置换反应：Zn+H₂SO₄→ZnSO₄+H₂↑",
                "复分解：NaOH+HCl→NaCl+H₂O",
                "燃烧反应：CH₄+2O₂→CO₂+2H₂O",
                "金属活动性顺序判断反应能否发生",
            ],
        },
    ],
    "升学规划": [
        {
            "title": "2026年武汉中考全年备考时间线",
            "subtitle": "家长必收藏·每月关键事件",
            "audience": "初三学生家长",
            "style": "timeline",
            "tags": ["中考时间线", "武汉中考", "备考规划", "2026中考", "初三家长", "升学规划", "武汉家长", "中考日历"],
            "timeline_data": [
                {"month": "7-8月", "title": "战略启航期", "desc": "定目标+暑假预习初三新课"},
                {"month": "9月", "title": "开学启动期", "desc": "初三节奏适应·建立错题本"},
                {"month": "11月", "title": "期中冲刺", "desc": "期中考试·查漏补缺"},
                {"month": "1月", "title": "元调大考", "desc": "全市统考·初步定位"},
                {"month": "3月", "title": "中考研讨", "desc": "命题方向明确·艺体招生发布"},
                {"month": "4月", "title": "四调+体考", "desc": "四调模考·指标到校考试"},
                {"month": "6月", "title": "中考决战", "desc": "志愿填报·中考·成绩查询"},
                {"month": "7-8月", "title": "录取衔接", "desc": "录取通知·新高一衔接"},
            ],
        },
        {
            "title": "武汉九大名高+领航校录取分数线",
            "subtitle": "2025年最新数据",
            "audience": "初三学生家长",
            "style": "data_table",
            "tags": ["武汉名高", "录取分数线", "九大名高", "领航校", "武汉中考", "升学数据", "武汉家长", "志愿填报"],
            "data_content": {
                "table_title": "武汉市重点高中录取数据(2025)",
                "headers": ["级别", "学校", "录取分", "招生数", "一本率"],
                "rows": [
                    ["九大名高", "华师一附中", "636", "640", "99.65%"],
                    ["九大名高", "省实验中学", "621", "750", "98.62%"],
                    ["九大名高", "武汉外国语", "639", "750", "98%"],
                    ["九大名高", "武汉二中", "634", "750", "97.20%"],
                    ["九大名高", "武汉三中", "622", "750", "98%"],
                    ["领航校", "洪山高级中学", "617", "600", "90%"],
                    ["领航校", "武汉中学", "612", "600", "90%"],
                    ["领航校", "华科大附中", "613", "620", "84.70%"],
                    ["领航校", "新洲一中", "590", "1420", "78.74%"],
                ],
            },
        },
        {
            "title": "初升高重要时间轴",
            "subtitle": "一图看懂全年关键节点",
            "audience": "初二/初三学生家长",
            "style": "timeline",
            "tags": ["初升高", "时间轴", "武汉中考", "升学规划", "家长必看", "关键节点", "武汉家长", "初升高规划"],
            "timeline_data": [
                {"month": "4-6月", "title": "初二下学期", "desc": "部分学校提前QY"},
                {"month": "7-8月", "title": "初二暑假", "desc": "学校开始摸底考试"},
                {"month": "9月", "title": "初三上开学", "desc": "开学考+初步定位"},
                {"month": "11月", "title": "期中考试", "desc": "外校自主招生高峰期"},
                {"month": "1月", "title": "元调统考", "desc": "极具参考价值的大考"},
                {"month": "2月", "title": "寒假", "desc": "最后一个长假·查漏补缺"},
                {"month": "4月", "title": "四调+体考", "desc": "指标到校·报名开始"},
                {"month": "6月", "title": "中考", "desc": "志愿填报+中考+出分"},
            ],
        },
    ],
}


def get_all_subjects() -> list[str]:
    """获取所有学科列表。"""
    return list(WUHAN_TOPICS.keys())


def get_topics_by_subject(subject: str) -> list[dict[str, Any]]:
    """获取指定学科的选题列表。"""
    return WUHAN_TOPICS.get(subject, [])


def get_random_topics(count: int = 5) -> list[dict[str, Any]]:
    """从所有学科中随机选取指定数量的选题。"""
    all_topics = []
    for topics in WUHAN_TOPICS.values():
        all_topics.extend(topics)
    return random.sample(all_topics, min(count, len(all_topics)))


def get_topic_by_title(title: str) -> dict[str, Any] | None:
    """根据标题模糊匹配选题。

    使用关键词重叠度打分，支持用户输入部分关键词。
    """
    import re
    # 提取输入中的关键词（去掉常见停用词）
    stop_words = {"帮我", "做", "一个", "一篇", "写", "生成", "小红书", "笔记",
                  "主题是", "主题", "关于", "的", "了", "和", "与"}
    input_words = set(re.findall(r'[\u4e00-\u9fff]+|\w+', title.lower()))
    input_words -= stop_words

    best_score = 0
    best_topic = None

    for topics in WUHAN_TOPICS.values():
        for topic in topics:
            topic_title = topic["title"]
            # 完全匹配
            if title in topic_title or topic_title in title:
                return topic
            # 关键词重叠打分
            topic_words = set(re.findall(r'[\u4e00-\u9fff]+|\w+', topic_title.lower()))
            # 字符级别匹配（每个输入字符是否在标题中）
            char_matches = sum(1 for c in title if c in topic_title)
            # 标签匹配
            tag_matches = sum(1 for t in topic.get("tags", []) if any(w in t for w in input_words))
            score = char_matches + tag_matches * 2
            if score > best_score and score >= len(title) * 0.4:
                best_score = score
                best_topic = topic

    return best_topic


def list_all_topics() -> str:
    """列出所有选题（用于显示）。"""
    lines = []
    for subject, topics in WUHAN_TOPICS.items():
        lines.append(f"\n📚 {subject}（{len(topics)}个选题）")
        for i, t in enumerate(topics, 1):
            style_emoji = {"data_table": "📊", "info_card": "📋", "comparison": "⚖️", "timeline": "📅"}.get(t["style"], "📝")
            lines.append(f"  {i}. {style_emoji} {t['title']} — {t['subtitle']}")
    return "\n".join(lines)


if __name__ == "__main__":
    print("🎯 武汉本地教育选题库")
    print("=" * 50)
    print(list_all_topics())
    print(f"\n共 {sum(len(v) for v in WUHAN_TOPICS.values())} 个选题")
