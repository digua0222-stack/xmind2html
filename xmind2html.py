#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xmind2html — 将 .xmind 思维导图转换为独立可交互的 HTML 页面

特性：
- 纯 Python 标准库实现，零第三方依赖
- 同时支持新版（content.json）与旧版（content.xml）XMind 文件格式
- 多画布（sheet）自动转为标签页切换
- 生成的 HTML 为单文件、无外部依赖：XMind 风格横向脑图、节点折叠、缩放、测试点/叶子统计
- 节点备注（notes）以悬浮提示展示

用法：
    python xmind2html.py 导图.xmind                 # 输出同目录同名 .html
    python xmind2html.py 导图.xmind -o out.html     # 指定输出路径
    python xmind2html.py 导图.xmind --title 标题    # 覆盖页面标题
"""

import argparse
import json
import os
import sys
import zipfile
import xml.etree.ElementTree as ET

__version__ = "1.0.0"

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
# HTML 模板
# ---------------------------------------------------------------------------

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__DOC_TITLE__</title>
<style>
  :root {
    --c-root: #1f2329;
    --c-text: #1f2329;
    --c-sub: #646a73;
    --c-border: #dee0e3;
    --c-hover: #f2f3f5;
    --c-bg: #ffffff;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    font-family: "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
    background: var(--c-bg); color: var(--c-text);
    overflow: hidden; display: flex; flex-direction: column;
  }
  header {
    flex: none; display: flex; align-items: center; gap: 16px;
    padding: 12px 20px; border-bottom: 1px solid #e5e6eb; flex-wrap: wrap;
  }
  header h1 { font-size: 18px; font-weight: 600; }
  .stats { font-size: 13px; color: var(--c-sub); }
  .legend { display: flex; gap: 14px; font-size: 12px; color: var(--c-sub); flex-wrap: wrap; }
  .legend .item { display: inline-flex; align-items: center; gap: 6px; }
  .dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
  .spacer { flex: 1; }
  .btns { display: flex; gap: 8px; }
  .btns button {
    font: inherit; font-size: 13px; padding: 5px 14px;
    border: 1px solid var(--c-border); border-radius: 6px; background: #fff;
    color: var(--c-text); cursor: pointer;
  }
  .btns button:hover { background: var(--c-hover); }

  .tabs { flex: none; display: flex; gap: 4px; padding: 6px 20px 0; border-bottom: 1px solid #e5e6eb; }
  .tabs button {
    font: inherit; font-size: 13px; padding: 6px 14px; border: none; background: none;
    color: var(--c-sub); cursor: pointer; border-bottom: 2px solid transparent;
  }
  .tabs button.active { color: var(--c-text); font-weight: 600; border-bottom-color: var(--c-root); }

  #viewport { flex: 1; overflow: auto; position: relative; }
  #canvas { position: relative; display: inline-block; padding: 40px 60px; transform-origin: 0 0; }
  #wires { position: absolute; inset: 0; pointer-events: none; overflow: visible; }
  #wires path { fill: none; stroke-width: 1.5; }
  #tree { position: relative; }

  .node { display: flex; align-items: center; }
  .kids { display: flex; flex-direction: column; justify-content: center; margin-left: 44px; }
  .kids.hidden { display: none; }

  .box {
    flex: none; display: inline-flex; align-items: center; gap: 6px;
    margin: 5px 0; padding: 6px 12px;
    font-size: 13px; line-height: 20px; white-space: nowrap;
    background: #fff; border: 1px solid var(--c-border); border-radius: 8px;
    box-shadow: 0 1px 2px rgba(31,35,41,.04);
  }
  .box.parent { cursor: pointer; }
  .box.parent:hover { background: var(--c-hover); }
  .box.noteflag::after { content: ""; }

  .depth-0 > .box {
    background: var(--c-root); border-color: var(--c-root);
    color: #fff; font-size: 17px; font-weight: 600;
    padding: 10px 20px; border-radius: 10px;
  }
  .depth-1 > .box { font-size: 14px; font-weight: 600; color: #fff; }
  .depth-2 > .box { font-weight: 500; }
  .node.leaf > .box { color: var(--c-sub); }

  .toggle {
    flex: none; width: 16px; height: 16px; border-radius: 50%;
    display: inline-flex; align-items: center; justify-content: center;
    font-size: 12px; line-height: 1; font-weight: 600;
    background: rgba(0,0,0,.06); color: var(--c-sub); user-select: none;
  }
  .depth-0 > .box .toggle, .depth-1 > .box .toggle { background: rgba(255,255,255,.25); color: #fff; }
  .count { font-size: 11px; color: #8f959e; font-weight: 400; }
  .depth-0 > .box .count, .depth-1 > .box .count { color: rgba(255,255,255,.85); }
  .note-flag { font-size: 11px; color: #b8800b; }

  footer {
    flex: none; padding: 8px 20px; font-size: 12px; color: #8f959e; border-top: 1px solid #e5e6eb;
  }
</style>
</head>
<body>
<header>
  <h1 id="docTitle"></h1>
  <span class="stats" id="stats"></span>
  <span class="legend" id="legend"></span>
  <span class="spacer"></span>
  <div class="btns">
    <button id="zoomOut" title="缩小">－</button>
    <button id="zoomReset" title="重置缩放">100%</button>
    <button id="zoomIn" title="放大">＋</button>
    <button id="expandAll">全部展开</button>
    <button id="collapseAll">收起细节</button>
  </div>
</header>
<div class="tabs" id="tabs" style="display:none"></div>
<div id="viewport">
  <div id="canvas">
    <svg id="wires"></svg>
    <div id="tree"></div>
  </div>
</div>
<footer>由 xmind2html 生成 · 点击节点展开 / 收起分支 · 带 ¶ 的节点有备注（悬浮查看）· 右上角可缩放</footer>

<script id="mindmap-data" type="application/json">/*__DATA__*/</script>
<script>
(function () {
  var DATA = JSON.parse(document.getElementById('mindmap-data').textContent);
  var PALETTE = ['#2f6bff', '#8b5cf6', '#22a06b', '#e5484d', '#d97706', '#0891b2', '#db2777', '#65a30d'];

  var treeEl = document.getElementById('tree');
  var wires = document.getElementById('wires');
  var canvas = document.getElementById('canvas');
  var nodeEls = [];
  var currentScale = 1;

  function countLeaves(n) {
    if (!n.children || !n.children.length) return 1;
    return n.children.reduce(function (s, c) { return s + countLeaves(c); }, 0);
  }
  function countNodes(n) {
    return 1 + (n.children || []).reduce(function (s, c) { return s + countNodes(c); }, 0);
  }

  function build(node, depth, branchIdx) {
    var hasKids = node.children && node.children.length > 0;
    var wrap = document.createElement('div');
    wrap.className = 'node depth-' + depth + (hasKids ? '' : ' leaf');
    if (depth === 1) wrap.dataset.branch = String(branchIdx % PALETTE.length);

    var box = document.createElement('div');
    box.className = 'box' + (hasKids ? ' parent' : '');
    if (depth === 1) {
      box.style.background = PALETTE[branchIdx % PALETTE.length];
      box.style.borderColor = PALETTE[branchIdx % PALETTE.length];
    }
    if (node.note) box.title = node.note;

    var t = document.createElement('span');
    t.textContent = node.title;
    box.appendChild(t);

    if (node.note) {
      var nf = document.createElement('span');
      nf.className = 'note-flag';
      nf.textContent = '¶';
      box.appendChild(nf);
    }

    var entry = { el: wrap, box: box, kidsBox: null, toggle: null, depth: depth };

    if (hasKids) {
      var cnt = document.createElement('span');
      cnt.className = 'count';
      cnt.textContent = countLeaves(node);
      box.appendChild(cnt);

      var tg = document.createElement('span');
      tg.className = 'toggle';
      tg.textContent = depth < 2 ? '−' : '+';
      box.appendChild(tg);

      var kids = document.createElement('div');
      kids.className = 'kids' + (depth < 2 ? '' : ' hidden');
      node.children.forEach(function (c, i) {
        kids.appendChild(build(c, depth + 1, depth === 0 ? i : branchIdx));
      });
      entry.kidsBox = kids;
      entry.toggle = tg;

      box.addEventListener('click', function () {
        var hidden = kids.classList.toggle('hidden');
        tg.textContent = hidden ? '+' : '−';
        requestAnimationFrame(drawWires);
      });

      wrap.appendChild(box);
      wrap.appendChild(kids);
    } else {
      wrap.appendChild(box);
    }
    nodeEls.push(entry);
    return wrap;
  }

  function branchColorOf(el) {
    var n = el;
    while (n) {
      if (n.dataset && n.dataset.branch != null) return PALETTE[Number(n.dataset.branch)];
      n = n.parentElement;
    }
    return '#1f2329';
  }

  function drawWires() {
    var cRect = canvas.getBoundingClientRect();
    wires.setAttribute('width', canvas.scrollWidth);
    wires.setAttribute('height', canvas.scrollHeight);
    wires.innerHTML = '';
    nodeEls.forEach(function (e) {
      if (!e.kidsBox || e.kidsBox.classList.contains('hidden')) return;
      var pRect = e.box.getBoundingClientRect();
      var px = (pRect.right - cRect.left) / currentScale;
      var py = (pRect.top + pRect.height / 2 - cRect.top) / currentScale;
      var color = branchColorOf(e.el);
      Array.prototype.forEach.call(e.kidsBox.children, function (childNode) {
        var cBox = childNode.querySelector(':scope > .box');
        if (!cBox) return;
        var r = cBox.getBoundingClientRect();
        var cx = (r.left - cRect.left) / currentScale;
        var cy = (r.top + r.height / 2 - cRect.top) / currentScale;
        var mid = (px + cx) / 2;
        var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', 'M ' + px + ' ' + py + ' C ' + mid + ' ' + py + ', ' + mid + ' ' + cy + ', ' + cx + ' ' + cy);
        path.setAttribute('stroke', color);
        path.setAttribute('opacity', '0.55');
        wires.appendChild(path);
      });
    });
  }

  function renderSheet(sheet) {
    nodeEls = [];
    treeEl.innerHTML = '';
    document.getElementById('docTitle').textContent = sheet.root.title;
    document.getElementById('stats').textContent =
      countNodes(sheet.root) + ' 个节点 · ' + countLeaves(sheet.root) + ' 个叶子节点';
    var legend = document.getElementById('legend');
    legend.innerHTML = '';
    (sheet.root.children || []).forEach(function (c, i) {
      var s = document.createElement('span');
      s.className = 'item';
      s.innerHTML = '<span class="dot" style="background:' + PALETTE[i % PALETTE.length] + '"></span>' +
        c.title + '（' + countLeaves(c) + '）';
      legend.appendChild(s);
    });
    treeEl.appendChild(build(sheet.root, 0, 0));
    requestAnimationFrame(drawWires);
  }

  // 多画布标签
  if (DATA.sheets.length > 1) {
    var tabs = document.getElementById('tabs');
    tabs.style.display = '';
    DATA.sheets.forEach(function (sheet, i) {
      var b = document.createElement('button');
      b.textContent = sheet.title;
      if (i === 0) b.className = 'active';
      b.addEventListener('click', function () {
        tabs.querySelectorAll('button').forEach(function (x) { x.className = ''; });
        b.className = 'active';
        renderSheet(sheet);
      });
      tabs.appendChild(b);
    });
  }

  // 缩放
  var zoomReset = document.getElementById('zoomReset');
  function setScale(s) {
    currentScale = Math.min(2, Math.max(0.3, s));
    canvas.style.transform = 'scale(' + currentScale + ')';
    zoomReset.textContent = Math.round(currentScale * 100) + '%';
    requestAnimationFrame(drawWires);
  }
  document.getElementById('zoomIn').addEventListener('click', function () { setScale(currentScale + 0.1); });
  document.getElementById('zoomOut').addEventListener('click', function () { setScale(currentScale - 0.1); });
  zoomReset.addEventListener('click', function () { setScale(1); });

  document.getElementById('expandAll').addEventListener('click', function () {
    nodeEls.forEach(function (e) {
      if (e.kidsBox) { e.kidsBox.classList.remove('hidden'); e.toggle.textContent = '−'; }
    });
    requestAnimationFrame(drawWires);
  });
  document.getElementById('collapseAll').addEventListener('click', function () {
    nodeEls.forEach(function (e) {
      if (e.kidsBox && e.depth >= 2) { e.kidsBox.classList.add('hidden'); e.toggle.textContent = '+'; }
    });
    requestAnimationFrame(drawWires);
  });

  window.addEventListener('resize', drawWires);
  window.addEventListener('load', drawWires);

  renderSheet(DATA.sheets[0]);
})();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# 生成
# ---------------------------------------------------------------------------

def render_html(data, doc_title):
    payload = json.dumps(data, ensure_ascii=False)
    # 防止数据中出现 </script> 提前闭合标签
    payload = payload.replace("</", "<\\/")
    html = HTML_TEMPLATE.replace("/*__DATA__*/", payload)
    html = html.replace("__DOC_TITLE__", _escape_html(doc_title))
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
        description="将 .xmind 思维导图转换为独立可交互的 HTML 页面")
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
