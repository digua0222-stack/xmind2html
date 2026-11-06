#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xmind2html — 将 .xmind 思维导图转换为独立可交互、可编辑的 HTML 页面

主入口是同目录下的 index.html：一个纯前端应用，双击打开后把 .xmind
文件拖进去即可查看/编辑脑图（增删改、拖拽移动、撤销重做、深浅主题）。

本 CLI 的作用：把 .xmind 的数据预先嵌进 index.html，生成一个
「打开即是这张图」的独立页面，适合分发或归档。

特性：
- 纯 Python 标准库实现，零第三方依赖
- 同时支持新版（content.json）与旧版（content.xml）XMind 文件格式
- 生成的页面与 index.html 完全一致，只是预装了数据

用法：
    python xmind2html.py 导图.xmind                 # 输出同目录同名 .html
    python xmind2html.py 导图.xmind -o out.html     # 指定输出路径
    python xmind2html.py 导图.xmind --title 标题    # 覆盖页面标题
"""

import argparse
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

__version__ = "1.4.0"

# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------

def _topic_from_json(t):
    """把 content.json 里的 topic 转成统一结构。"""
    node = {"title": (t.get("title") or "").strip() or "(未命名)"}
    notes = t.get("notes")
    if isinstance(notes, dict):
        plain = notes.get("plain") or {}
        content = (plain.get("content") or "").strip()
        if content:
            node["note"] = content
    children = (t.get("children") or {}).get("attached") or []
    kids = [_topic_from_json(c) for c in children]
    if kids:
        node["children"] = kids
    return node


def _localname(tag):
    return tag.rsplit("}", 1)[-1]


def _child(elem, name):
    for c in elem:
        if _localname(c.tag) == name:
            return c
    return None


def _topic_from_xml(elem):
    """把 content.xml 里的 <topic> 转成统一结构（兼容旧版 XMind）。"""
    title_el = _child(elem, "title")
    node = {"title": (title_el.text or "").strip() if title_el is not None else "(未命名)"}
    if not node["title"]:
        node["title"] = "(未命名)"
    notes_el = _child(elem, "notes")
    if notes_el is not None:
        plain_el = _child(notes_el, "plain")
        if plain_el is not None and plain_el.text and plain_el.text.strip():
            node["note"] = plain_el.text.strip()
    kids = []
    children_el = _child(elem, "children")
    if children_el is not None:
        for topics_el in children_el:
            if _localname(topics_el.tag) != "topics":
                continue
            if topics_el.get("type") not in (None, "attached"):
                continue  # 跳过 summary 等非主干分支
            for t in topics_el:
                if _localname(t.tag) == "topic":
                    kids.append(_topic_from_xml(t))
    if kids:
        node["children"] = kids
    return node


def parse_xmind(path):
    """解析 .xmind 文件，返回 {'sheets': [{'title': ..., 'root': {...}}, ...]}。"""
    if not zipfile.is_zipfile(path):
        raise ValueError("不是有效的 .xmind 文件（应为 zip 容器）：%s" % path)

    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())

        if "content.json" in names:  # XMind 8 Update 之后的新格式 / XMind Zen
            sheets_raw = json.loads(z.read("content.json").decode("utf-8"))
            sheets = []
            for i, s in enumerate(sheets_raw):
                root = _topic_from_json(s.get("rootTopic") or {})
                sheets.append({
                    "title": (s.get("title") or "画布 %d" % (i + 1)).strip(),
                    "root": root,
                })
            if not sheets:
                raise ValueError("content.json 中没有任何画布")
            return {"sheets": sheets}

        if "content.xml" in names:  # 旧版 XMind 格式
            xml_root = ET.fromstring(z.read("content.xml"))
            sheets = []
            for i, sheet_el in enumerate(xml_root):
                if _localname(sheet_el.tag) != "sheet":
                    continue
                title_el = _child(sheet_el, "title")
                topic_el = _child(sheet_el, "topic")
                if topic_el is None:
                    continue
                sheets.append({
                    "title": ((title_el.text or "").strip() if title_el is not None else "")
                             or "画布 %d" % (i + 1),
                    "root": _topic_from_xml(topic_el),
                })
            if not sheets:
                raise ValueError("content.xml 中没有任何画布")
            return {"sheets": sheets}

    raise ValueError("压缩包中未找到 content.json 或 content.xml")


def count_stats(root):
    """返回 (节点总数, 叶子节点数)。"""
    kids = root.get("children") or []
    if not kids:
        return 1, 1
    n = l = 0
    for c in kids:
        cn, cl = count_stats(c)
        n += cn
        l += cl
    return n + 1, l


# ---------------------------------------------------------------------------
# 生成：以同目录 index.html 为模板，注入数据与标题
# ---------------------------------------------------------------------------

_DATA_SCRIPT_RE = re.compile(
    r'(<script id="mindmap-data" type="application/json">)[\s\S]*?(</script>)')


def load_template():
    """读取与脚本同目录的 index.html 作为模板。"""
    here = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(here, "index.html")
    if not os.path.isfile(template_path):
        raise RuntimeError("未找到模板文件 index.html（应与 xmind2html.py 同目录）")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


def render_html(data, doc_title, template=None):
    if template is None:
        template = load_template()
    payload = json.dumps(data, ensure_ascii=False)
    # 防止数据中出现 </script> 提前闭合标签
    payload = payload.replace("</", "<\\/")
    html, n = _DATA_SCRIPT_RE.subn(
        lambda m: m.group(1) + payload + m.group(2), template, count=1)
    if n != 1:
        raise RuntimeError("模板中未找到 mindmap-data 数据注入点")
    html = html.replace("<title>xmind2html</title>",
                        "<title>%s</title>" % _escape_html(doc_title), 1)
    return html


def _escape_html(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def convert(input_path, output_path=None, title=None):
    data = parse_xmind(input_path)
    if output_path is None:
        base, _ = os.path.splitext(input_path)
        output_path = base + ".html"
    if title is None:
        title = data["sheets"][0]["root"]["title"]
    html = render_html(data, title)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="xmind2html",
        description="将 .xmind 思维导图转换为独立可交互、可编辑的 HTML 页面")
    parser.add_argument("input", help="输入的 .xmind 文件路径")
    parser.add_argument("-o", "--output", help="输出的 .html 文件路径（默认与输入同名）")
    parser.add_argument("--title", help="覆盖页面标题（默认使用根节点标题）")
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    args = parser.parse_args(argv)

    if not os.path.isfile(args.input):
        print("错误：文件不存在：%s" % args.input, file=sys.stderr)
        return 1

    try:
        out = convert(args.input, args.output, args.title)
    except Exception as e:
        print("转换失败：%s" % e, file=sys.stderr)
        return 2

    print("已生成：%s" % os.path.abspath(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
