"""
Obsidian 文档清洗
处理双链语法、frontmatter 等，输出干净的 Markdown 文本。
"""

import re


def strip_frontmatter(text: str) -> str:
    """
    去掉 Obsidian 的 YAML frontmatter（--- 开头的一段）。

    例:
        ---
        类型: 方法论
        名称: 数据治理六步法
        ---
        正文...

    只保留正文。
    """
    if text.startswith("---"):
        # 找第二个 --- 的位置
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[2].lstrip("\n")
    return text


def clean_obsidian_links(text: str) -> str:
    """
    处理 Obsidian 双链语法：

    1. [[目标文件|显示文本]] → 显示文本
       例：[[方法论-治理六步法-Step1现状调研|查看详情]] → 查看详情

    2. [[目标文件]] → 目标文件名（作为普通文本保留）
       例：[[模板-数据质量检核规则]] → 模板-数据质量检核规则

    目的：双链要么换成可读文本，要么只留标题名，避免 [[]] 污染向量化。
    """
    # 先处理带管道符的 [[a|b]]：保留 b
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)

    # 再处理无管道符的 [[a]]：保留 a
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)

    return text


def remove_callouts(text: str) -> str:
    """
    去掉 Obsidian 的 callout 语法标记（> [!type] 和 > 前缀引用）。

    例：
        > [!note] 标题
        > 内容
    →
        内容
    """
    # 去掉 callout 类型行，保留内容行
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # 跳过 callout 标记行： > [!xxx]
        if stripped.startswith("> [!") or stripped.startswith(">[!"):
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def clean_document(text: str) -> str:
    """
    完整清洗流程：frontmatter → 双链 → callout。
    """
    text = strip_frontmatter(text)
    text = clean_obsidian_links(text)
    text = remove_callouts(text)
    return text