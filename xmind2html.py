#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xmind2html — 将 .xmind 思维导图转换为独立可交互的 HTML 页面

特性：
- 纯 Python 标准库实现，零第三方依赖
- 同时支持新版（content.json）与旧版（content.xml）XMind 文件格式
- 多画布（sheet）自动转为标签页切换
- 生成的 HTML 为单文件、无外部依赖：
  · XMind 风格横向脑图、分支自动配色、节点折叠、缩放
  · 深色主题默认，可切换浅色
  · 节点增删改：添加子节点 / 同级、重命名、编辑备注、删除
  · XMind 式快捷键（Tab / Enter / Delete / F2）、撤销 / 重做
  · 编辑自动保存到浏览器本地，可一键导出为新的独立 HTML
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

__version__ = "1.3.0"

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
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__DOC_TITLE__</title>
<style>
  :root {
    --c-bg: #16171b;
    --c-header: #1c1d23;
    --c-border: #30323a;
    --c-text: #e8e9ec;
    --c-sub: #9aa0aa;
    --c-box: #22242b;
    --c-box-border: #3a3d46;
    --c-hover: #2c2e36;
    --c-root-bg: #eceef3;
    --c-root-text: #1a1b1e;
    --c-sel: #5b8cff;
    --c-input-bg: #16171b;
    color-scheme: dark;
  }
  html[data-theme="light"] {
    --c-bg: #ffffff;
    --c-header: #ffffff;
    --c-border: #dee0e3;
    --c-text: #1f2329;
    --c-sub: #646a73;
    --c-box: #ffffff;
    --c-box-border: #dee0e3;
    --c-hover: #f2f3f5;
    --c-root-bg: #1f2329;
    --c-root-text: #ffffff;
    --c-sel: #2f6bff;
    --c-input-bg: #ffffff;
    color-scheme: light;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    font-family: "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
    background: var(--c-bg); color: var(--c-text);
    overflow: hidden; display: flex; flex-direction: column;
  }
  header {
    flex: none; display: flex; align-items: center; gap: 12px;
    padding: 10px 16px; border-bottom: 1px solid var(--c-border);
    background: var(--c-header); flex-wrap: wrap;
  }
  header h1 { font-size: 17px; font-weight: 600; }
  .stats { font-size: 12px; color: var(--c-sub); }
  .legend { display: flex; gap: 12px; font-size: 12px; color: var(--c-sub); flex-wrap: wrap; }
  .legend .item { display: inline-flex; align-items: center; gap: 5px; }
  .dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
  .spacer { flex: 1; }
  .btns { display: flex; gap: 6px; flex-wrap: wrap; }
  .btns button {
    font: inherit; font-size: 12px; padding: 4px 10px;
    border: 1px solid var(--c-border); border-radius: 6px;
    background: var(--c-box); color: var(--c-text); cursor: pointer;
  }
  .btns button:hover:not(:disabled) { background: var(--c-hover); }
  .btns button:disabled { opacity: .4; cursor: default; }
  .btns .sep { width: 1px; background: var(--c-border); margin: 2px 2px; }

  .tabs { flex: none; display: flex; gap: 4px; padding: 6px 16px 0; border-bottom: 1px solid var(--c-border); background: var(--c-header); }
  .tabs button {
    font: inherit; font-size: 13px; padding: 6px 14px; border: none; background: none;
    color: var(--c-sub); cursor: pointer; border-bottom: 2px solid transparent;
  }
  .tabs button.active { color: var(--c-text); font-weight: 600; border-bottom-color: var(--c-sel); }

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
    background: var(--c-box); border: 1px solid var(--c-box-border); border-radius: 8px;
    box-shadow: 0 1px 2px rgba(0,0,0,.15); cursor: pointer; user-select: none;
  }
  .box:hover { background: var(--c-hover); }
  .box.selected { outline: 2px solid var(--c-sel); outline-offset: 1px; }
  .box[draggable="true"] { cursor: grab; }
  .box.dragging { opacity: .45; }
  .box.drop-child { outline: 2px dashed var(--c-sel); outline-offset: 2px; }
  .box.drop-before { box-shadow: 0 -3px 0 0 var(--c-sel); }
  .box.drop-after { box-shadow: 0 3px 0 0 var(--c-sel); }

  .depth-0 > .box {
    background: var(--c-root-bg); border-color: var(--c-root-bg);
    color: var(--c-root-text); font-size: 17px; font-weight: 600;
    padding: 10px 20px; border-radius: 10px;
  }
  .depth-1 > .box { font-size: 14px; font-weight: 600; color: #fff; }
  .depth-2 > .box { font-weight: 500; }
  .node.leaf > .box .t { color: var(--c-sub); }
  .node.leaf > .box.selected .t { color: var(--c-text); }

  .toggle {
    flex: none; width: 16px; height: 16px; border-radius: 50%;
    display: inline-flex; align-items: center; justify-content: center;
    font-size: 12px; line-height: 1; font-weight: 600;
    background: rgba(127,127,127,.18); color: var(--c-sub);
  }
  .toggle:hover { background: rgba(127,127,127,.35); color: var(--c-text); }
  .depth-0 > .box .toggle { background: rgba(0,0,0,.12); color: var(--c-root-text); }
  .depth-1 > .box .toggle { background: rgba(255,255,255,.25); color: #fff; }
  .count { font-size: 11px; color: var(--c-sub); font-weight: 400; }
  .depth-0 > .box .count { color: var(--c-root-text); opacity: .7; }
  .depth-1 > .box .count { color: rgba(255,255,255,.85); }
  .note-flag { font-size: 11px; color: #e5a50a; }

  .rename-input {
    font: inherit; font-size: 13px; color: var(--c-text);
    background: var(--c-input-bg); border: 1px solid var(--c-sel);
    border-radius: 4px; padding: 1px 6px; outline: none; min-width: 120px;
  }

  footer {
    flex: none; padding: 7px 16px; font-size: 12px; color: var(--c-sub);
    border-top: 1px solid var(--c-border); background: var(--c-header);
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
    <button id="btnChild" title="为选中节点添加子节点（Tab）">+ 子节点</button>
    <button id="btnSibling" title="为选中节点添加同级节点（Enter）">+ 同级</button>
    <button id="btnRename" title="重命名选中节点（F2 / 双击）">重命名</button>
    <button id="btnNote" title="编辑选中节点备注">备注</button>
    <button id="btnDelete" title="删除选中节点（Delete）">删除</button>
    <span class="sep"></span>
    <button id="btnUndo" title="撤销（Ctrl+Z）">撤销</button>
    <button id="btnRedo" title="重做（Ctrl+Y）">重做</button>
    <span class="sep"></span>
    <button id="btnExport" title="把当前编辑结果导出为新的独立 HTML">导出 HTML</button>
    <button id="btnImport" title="在浏览器中直接打开另一份 .xmind 文件">导入 .xmind</button>
    <button id="btnReset" title="清除本地编辑，恢复原始内容">重置</button>
    <span class="sep"></span>
    <button id="btnTheme" title="切换深色 / 浅色主题">浅色</button>
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
<input type="file" id="fileInput" accept=".xmind" style="display:none">
<footer id="foot">由 xmind2html 生成 · 单击选中，双击重命名，拖拽移动节点 · Tab 加子节点 / Enter 加同级 / Delete 删除 · 「导入 .xmind」直接换图，「导出 HTML」保存成果</footer>

<script id="mindmap-data" type="application/json">/*__DATA__*/</script>
<script>
(function () {
  var ORIGINAL_TEXT = document.getElementById('mindmap-data').textContent;
  var DATA = JSON.parse(ORIGINAL_TEXT);
  var PALETTES = {
    dark:  ['#5b8cff', '#a78bfa', '#34d399', '#f87171', '#fbbf24', '#22d3ee', '#f472b6', '#a3e635'],
    light: ['#2f6bff', '#8b5cf6', '#22a06b', '#e5484d', '#d97706', '#0891b2', '#db2777', '#65a30d']
  };

  var treeEl = document.getElementById('tree');
  var wires = document.getElementById('wires');
  var canvas = document.getElementById('canvas');
  var foot = document.getElementById('foot');
  var FOOT_TEXT = foot.textContent;

  var currentScale = 1;
  var currentSheet = 0;
  var selectedId = null;
  var idSeq = 1;
  var nodeEls = [];
  var undoStack = [], redoStack = [];
  var collapsed = {};      // sheetIdx -> { nodeId: true=展开 / false=收起 }，覆盖默认（depth<2 展开）
  var editing = false;     // 正在重命名
  var dragId = null;       // 正在拖拽的节点 id

  // ---------- 工具 ----------
  function palette() {
    return PALETTES[document.documentElement.dataset.theme === 'light' ? 'light' : 'dark'];
  }
  function storageKey() {
    // 按页面路径区分：同一文件无论加载哪份导图都读写同一键
    return 'xmind2html:' + location.pathname;
  }
  function countLeaves(n) {
    if (!n.children || !n.children.length) return 1;
    return n.children.reduce(function (s, c) { return s + countLeaves(c); }, 0);
  }
  function countNodes(n) {
    return 1 + (n.children || []).reduce(function (s, c) { return s + countNodes(c); }, 0);
  }
  function assignIds(n) {
    n._id = idSeq++;
    (n.children || []).forEach(assignIds);
  }
  function findNode(id, n) {
    n = n || DATA.sheets[currentSheet].root;
    if (n._id === id) return n;
    var kids = n.children || [];
    for (var i = 0; i < kids.length; i++) {
      var r = findNode(id, kids[i]);
      if (r) return r;
    }
    return null;
  }
  function findParent(id, n) {
    n = n || DATA.sheets[currentSheet].root;
    var kids = n.children || [];
    for (var i = 0; i < kids.length; i++) {
      if (kids[i]._id === id) return n;
      var r = findParent(id, kids[i]);
      if (r) return r;
    }
    return null;
  }
  function isOpen(node, depth) {
    var ov = (collapsed[currentSheet] || {})[node._id];
    if (ov != null) return ov;
    return depth < 2;
  }
  function setOpen(node, open) {
    collapsed[currentSheet] = collapsed[currentSheet] || {};
    collapsed[currentSheet][node._id] = open;
  }
  function saveLocal() {
    try { localStorage.setItem(storageKey(), JSON.stringify(DATA)); } catch (e) {}
  }
  function markDirty() {
    foot.textContent = FOOT_TEXT + ' · 已修改（自动保存到本地）';
  }

  // ---------- 渲染 ----------
  function build(node, depth, branchIdx) {
    var hasKids = !!(node.children && node.children.length);
    var open = isOpen(node, depth);
    var wrap = document.createElement('div');
    wrap.className = 'node depth-' + depth + (hasKids ? '' : ' leaf');
    if (depth === 1) wrap.dataset.branch = String(branchIdx % palette().length);

    var box = document.createElement('div');
    box.className = 'box';
    if (node._id === selectedId) box.classList.add('selected');
    if (depth === 1) {
      box.style.background = palette()[branchIdx % palette().length];
      box.style.borderColor = palette()[branchIdx % palette().length];
    }
    if (node.note) box.title = node.note;

    var t = document.createElement('span');
    t.className = 't';
    t.textContent = node.title;
    box.appendChild(t);

    if (node.note) {
      var nf = document.createElement('span');
      nf.className = 'note-flag';
      nf.textContent = '¶';
      box.appendChild(nf);
    }

    var entry = { el: wrap, box: box, kidsBox: null, node: node, depth: depth };

    if (hasKids) {
      var cnt = document.createElement('span');
      cnt.className = 'count';
      cnt.textContent = countLeaves(node);
      box.appendChild(cnt);

      var tg = document.createElement('span');
      tg.className = 'toggle';
      tg.textContent = open ? '−' : '+';
      tg.title = '展开 / 收起';
      box.appendChild(tg);

      var kids = document.createElement('div');
      kids.className = 'kids' + (open ? '' : ' hidden');
      node.children.forEach(function (c, i) {
        kids.appendChild(build(c, depth + 1, depth === 0 ? i : branchIdx));
      });
      entry.kidsBox = kids;

      tg.addEventListener('click', function (ev) {
        ev.stopPropagation();
        var hidden = kids.classList.toggle('hidden');
        tg.textContent = hidden ? '+' : '−';
        setOpen(node, !hidden);
        requestAnimationFrame(drawWires);
      });
    }

    box.addEventListener('click', function () {
      if (editing) return;
      select(node._id);
    });
    box.addEventListener('dblclick', function (ev) {
      ev.stopPropagation();
      startRename(node, box);
    });

    // 拖拽移动（根节点不可拖动；拖到目标上 1/4 区域 = 前/后同级，中间 = 成为子节点）
    if (depth > 0) box.draggable = true;
    box.addEventListener('dragstart', function (ev) {
      if (editing || depth === 0) { ev.preventDefault(); return; }
      dragId = node._id;
      ev.dataTransfer.effectAllowed = 'move';
      try { ev.dataTransfer.setData('text/plain', String(node._id)); } catch (e) {}
      box.classList.add('dragging');
    });
    box.addEventListener('dragover', function (ev) {
      if (dragId == null || dragId === node._id) return;
      if (findNode(node._id, findNode(dragId))) return; // 不能拖入自己的子树
      ev.preventDefault();
      ev.dataTransfer.dropEffect = 'move';
      clearDropMarks();
      var zone = dropZone(box, ev.clientY, node);
      box.classList.add(zone === 'child' ? 'drop-child' : zone === 'before' ? 'drop-before' : 'drop-after');
    });
    box.addEventListener('dragleave', function () {
      box.classList.remove('drop-child', 'drop-before', 'drop-after');
    });
    box.addEventListener('drop', function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      var zone = dropZone(box, ev.clientY, node);
      clearDropMarks();
      if (dragId != null) moveNode(dragId, node, zone);
      dragId = null;
    });
    box.addEventListener('dragend', function () {
      dragId = null;
      clearDropMarks();
    });

    wrap.appendChild(box);
    if (kids) wrap.appendChild(kids);
    nodeEls.push(entry);
    return wrap;
  }

  function branchColorOf(el) {
    var n = el;
    while (n) {
      if (n.dataset && n.dataset.branch != null) return palette()[Number(n.dataset.branch)];
      n = n.parentElement;
    }
    return '#8b8f98';
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
        path.setAttribute('opacity', '0.6');
        wires.appendChild(path);
      });
    });
  }

  function render() {
    nodeEls = [];
    treeEl.innerHTML = '';
    var sheet = DATA.sheets[currentSheet];
    document.getElementById('docTitle').textContent = sheet.root.title;
    document.getElementById('stats').textContent =
      countNodes(sheet.root) + ' 个节点 · ' + countLeaves(sheet.root) + ' 个叶子节点';
    var legend = document.getElementById('legend');
    legend.innerHTML = '';
    (sheet.root.children || []).forEach(function (c, i) {
      var s = document.createElement('span');
      s.className = 'item';
      s.innerHTML = '<span class="dot" style="background:' + palette()[i % palette().length] + '"></span>' +
        c.title + '（' + countLeaves(c) + '）';
      legend.appendChild(s);
    });
    treeEl.appendChild(build(sheet.root, 0, 0));
    updateButtons();
    requestAnimationFrame(drawWires);
  }

  function select(id) {
    selectedId = id;
    treeEl.querySelectorAll('.box.selected').forEach(function (b) { b.classList.remove('selected'); });
    if (id != null) {
      var entry = nodeEls.find(function (e) { return e.node._id === id; });
      if (entry) entry.box.classList.add('selected');
    }
    updateButtons();
  }

  // ---------- 拖拽移动 ----------
  function clearDropMarks() {
    treeEl.querySelectorAll('.drop-child,.drop-before,.drop-after,.dragging').forEach(function (b) {
      b.classList.remove('drop-child', 'drop-before', 'drop-after', 'dragging');
    });
  }
  function dropZone(box, clientY, targetNode) {
    var parent = findParent(targetNode._id);
    if (!parent) return 'child'; // 根节点只能作为父级接收
    var rect = box.getBoundingClientRect();
    var ratio = (clientY - rect.top) / rect.height;
    if (ratio < 0.25) return 'before';
    if (ratio > 0.75) return 'after';
    return 'child';
  }
  function moveNode(srcId, targetNode, zone) {
    if (srcId === targetNode._id) return;
    var src = findNode(srcId);
    var oldParent = findParent(srcId);
    if (!src || !oldParent) return;
    if (findNode(targetNode._id, src)) return; // 目标在源子树内
    pushUndo();
    oldParent.children = oldParent.children.filter(function (c) { return c._id !== srcId; });
    var newParent = zone === 'child' ? null : findParent(targetNode._id);
    if (zone === 'child' || !newParent) {
      targetNode.children = targetNode.children || [];
      targetNode.children.push(src);
      setOpen(targetNode, true);
    } else {
      var idx = newParent.children.findIndex(function (c) { return c._id === targetNode._id; });
      newParent.children.splice(zone === 'before' ? idx : idx + 1, 0, src);
    }
    afterEdit(srcId, false);
  }

  // ---------- 编辑操作 ----------
  function pushUndo() {
    undoStack.push(JSON.stringify(DATA.sheets[currentSheet].root));
    if (undoStack.length > 100) undoStack.shift();
    redoStack = [];
    updateButtons();
  }
  function afterEdit(focusId, renameIt) {
    saveLocal();
    markDirty();
    if (focusId != null) selectedId = focusId;
    render();
    if (renameIt && focusId != null) {
      var entry = nodeEls.find(function (e) { return e.node._id === focusId; });
      if (entry) startRename(entry.node, entry.box);
    }
  }

  function addChild() {
    var sel = findNode(selectedId);
    if (!sel) return;
    pushUndo();
    sel.children = sel.children || [];
    var nn = { title: '新节点', _id: idSeq++ };
    sel.children.push(nn);
    setOpen(sel, true);
    afterEdit(nn._id, true);
  }
  function addSibling() {
    var sel = findNode(selectedId);
    if (!sel) return;
    var parent = findParent(selectedId);
    if (!parent) { addChild(); return; } // 根节点没有同级，退化为加子节点
    pushUndo();
    var idx = parent.children.findIndex(function (c) { return c._id === selectedId; });
    var nn = { title: '新节点', _id: idSeq++ };
    parent.children.splice(idx + 1, 0, nn);
    afterEdit(nn._id, true);
  }
  function deleteNode() {
    var sel = findNode(selectedId);
    if (!sel) return;
    var parent = findParent(selectedId);
    if (!parent) { alert('根节点不能删除'); return; }
    if (sel.children && sel.children.length &&
        !confirm('「' + sel.title + '」包含 ' + sel.children.length + ' 个直接子节点，确定一并删除？')) return;
    pushUndo();
    parent.children = parent.children.filter(function (c) { return c._id !== selectedId; });
    afterEdit(parent._id, false);
  }
  function startRename(node, box) {
    if (editing) return;
    editing = true;
    box.draggable = false;
    var span = box.querySelector('.t');
    var input = document.createElement('input');
    input.className = 'rename-input';
    input.value = node.title;
    box.replaceChild(input, span);
    input.focus();
    input.select();
    var done = false;
    function commit(ok) {
      if (done) return;
      done = true;
      editing = false;
      var v = input.value.trim();
      if (ok && v && v !== node.title) {
        pushUndo();
        node.title = v;
        afterEdit(node._id, false);
      } else {
        render();
      }
    }
    input.addEventListener('blur', function () { commit(true); });
    input.addEventListener('keydown', function (ev) {
      ev.stopPropagation();
      if (ev.key === 'Enter') { commit(true); }
      else if (ev.key === 'Escape') { commit(false); }
    });
    input.addEventListener('click', function (ev) { ev.stopPropagation(); });
  }
  function editNote() {
    var sel = findNode(selectedId);
    if (!sel) return;
    var v = prompt('编辑备注（留空则清除备注）：', sel.note || '');
    if (v == null) return;
    v = v.trim();
    if (v === (sel.note || '')) return;
    pushUndo();
    if (v) sel.note = v; else delete sel.note;
    afterEdit(sel._id, false);
  }
  function undo() {
    if (!undoStack.length) return;
    redoStack.push(JSON.stringify(DATA.sheets[currentSheet].root));
    DATA.sheets[currentSheet].root = JSON.parse(undoStack.pop());
    reassignAll();
    selectedId = null;
    saveLocal(); markDirty(); render();
  }
  function redo() {
    if (!redoStack.length) return;
    undoStack.push(JSON.stringify(DATA.sheets[currentSheet].root));
    DATA.sheets[currentSheet].root = JSON.parse(redoStack.pop());
    reassignAll();
    selectedId = null;
    saveLocal(); markDirty(); render();
  }
  function reassignAll() {
    idSeq = 1;
    DATA.sheets.forEach(function (s) { assignIds(s.root); });
  }

  // ---------- 导出 / 重置 ----------
  function exportHTML() {
    var json = JSON.stringify(DATA).replace(/<\//g, '<\\/');
    var html = '<!DOCTYPE html>\n' + document.documentElement.outerHTML;
    html = html.replace(
      /(<script id="mindmap-data" type="application\/json">)[\s\S]*?(<\/script>)/,
      function (_, a, b) { return a + json + b; });
    var blob = new Blob([html], { type: 'text/html;charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = (DATA.sheets[0].root.title || 'mindmap') + '.html';
    document.body.appendChild(a);
    a.click();
    setTimeout(function () {
      URL.revokeObjectURL(a.href);
      a.remove();
    }, 100);
  }
  function resetAll() {
    if (!confirm('放弃所有本地编辑，恢复为文件原始内容？')) return;
    try { localStorage.removeItem(storageKey()); } catch (e) {}
    DATA = JSON.parse(ORIGINAL_TEXT);
    reassignAll();
    collapsed = {};
    undoStack = []; redoStack = [];
    selectedId = null;
    foot.textContent = FOOT_TEXT;
    render();
  }

  // ---------- 主题 ----------
  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    document.getElementById('btnTheme').textContent = theme === 'dark' ? '浅色' : '深色';
    try { localStorage.setItem('xmind2html:theme', theme); } catch (e) {}
  }
  document.getElementById('btnTheme').addEventListener('click', function () {
    var next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    applyTheme(next);
    render();
  });

  // ---------- 工具栏 ----------
  function updateButtons() {
    var hasSel = selectedId != null && !!findNode(selectedId);
    document.getElementById('btnChild').disabled = !hasSel;
    document.getElementById('btnSibling').disabled = !hasSel;
    document.getElementById('btnRename').disabled = !hasSel;
    document.getElementById('btnNote').disabled = !hasSel;
    document.getElementById('btnDelete').disabled = !hasSel;
    document.getElementById('btnUndo').disabled = !undoStack.length;
    document.getElementById('btnRedo').disabled = !redoStack.length;
  }
  document.getElementById('btnChild').addEventListener('click', addChild);
  document.getElementById('btnSibling').addEventListener('click', addSibling);
  document.getElementById('btnDelete').addEventListener('click', deleteNode);
  document.getElementById('btnNote').addEventListener('click', editNote);
  document.getElementById('btnRename').addEventListener('click', function () {
    var sel = findNode(selectedId);
    if (!sel) return;
    var entry = nodeEls.find(function (e) { return e.node._id === selectedId; });
    if (entry) startRename(sel, entry.box);
  });
  document.getElementById('btnUndo').addEventListener('click', undo);
  document.getElementById('btnRedo').addEventListener('click', redo);
  document.getElementById('btnExport').addEventListener('click', exportHTML);
  document.getElementById('btnReset').addEventListener('click', resetAll);

  document.addEventListener('keydown', function (ev) {
    if (editing) return;
    var tag = (ev.target && ev.target.tagName) || '';
    if (tag === 'INPUT' || tag === 'TEXTAREA') return;
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'z') {
      ev.preventDefault();
      if (ev.shiftKey) redo(); else undo();
      return;
    }
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'y') {
      ev.preventDefault(); redo(); return;
    }
    if (selectedId == null) return;
    if (ev.key === 'Tab') { ev.preventDefault(); addChild(); }
    else if (ev.key === 'Enter') { ev.preventDefault(); addSibling(); }
    else if (ev.key === 'Delete' || ev.key === 'Backspace') { ev.preventDefault(); deleteNode(); }
    else if (ev.key === 'F2') { ev.preventDefault(); document.getElementById('btnRename').click(); }
  });

  // ---------- 缩放 ----------
  var zoomResetBtn = document.getElementById('zoomReset');
  function setScale(s) {
    currentScale = Math.min(2, Math.max(0.3, s));
    canvas.style.transform = 'scale(' + currentScale + ')';
    zoomResetBtn.textContent = Math.round(currentScale * 100) + '%';
    requestAnimationFrame(drawWires);
  }
  document.getElementById('zoomIn').addEventListener('click', function () { setScale(currentScale + 0.1); });
  document.getElementById('zoomOut').addEventListener('click', function () { setScale(currentScale - 0.1); });
  zoomResetBtn.addEventListener('click', function () { setScale(1); });

  document.getElementById('expandAll').addEventListener('click', function () {
    collapsed[currentSheet] = {};
    nodeEls.forEach(function (e) { setOpen(e.node, true); });
    render();
  });
  document.getElementById('collapseAll').addEventListener('click', function () {
    collapsed[currentSheet] = {};
    nodeEls.forEach(function (e) { if (e.depth >= 2) setOpen(e.node, false); });
    render();
  });

  window.addEventListener('resize', drawWires);
  window.addEventListener('load', drawWires);

  // ---------- 导入 .xmind（浏览器内解析 zip） ----------
  function firstChildNamed(el, name) {
    for (var i = 0; i < el.children.length; i++) {
      if (el.children[i].localName === name) return el.children[i];
    }
    return null;
  }
  function topicFromJson(t) {
    var node = { title: ((t.title || '') + '').trim() || '(未命名)' };
    if (t.notes && t.notes.plain && (t.notes.plain.content || '').trim()) {
      node.note = t.notes.plain.content.trim();
    }
    var kids = (t.children && t.children.attached || []).map(topicFromJson);
    if (kids.length) node.children = kids;
    return node;
  }
  function topicFromXml(el) {
    var titleEl = firstChildNamed(el, 'title');
    var node = { title: (titleEl ? titleEl.textContent.trim() : '') || '(未命名)' };
    var notesEl = firstChildNamed(el, 'notes');
    if (notesEl) {
      var plainEl = firstChildNamed(notesEl, 'plain');
      if (plainEl && plainEl.textContent.trim()) node.note = plainEl.textContent.trim();
    }
    var kids = [];
    var childrenEl = firstChildNamed(el, 'children');
    if (childrenEl) {
      Array.prototype.forEach.call(childrenEl.children, function (topicsEl) {
        if (topicsEl.localName !== 'topics') return;
        var type = topicsEl.getAttribute('type');
        if (type && type !== 'attached') return;
        Array.prototype.forEach.call(topicsEl.children, function (t) {
          if (t.localName === 'topic') kids.push(topicFromXml(t));
        });
      });
    }
    if (kids.length) node.children = kids;
    return node;
  }
  function parseZipEntries(buf) {
    var dv = new DataView(buf);
    var bytes = new Uint8Array(buf);
    var eocd = -1;
    for (var i = bytes.length - 22; i >= Math.max(0, bytes.length - 22 - 65536); i--) {
      if (dv.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
    }
    if (eocd < 0) throw new Error('不是有效的 .xmind 文件（zip 结构损坏）');
    var count = dv.getUint16(eocd + 10, true);
    var p = dv.getUint32(eocd + 16, true);
    var dec = new TextDecoder('utf-8');
    var entries = {};
    for (var n = 0; n < count; n++) {
      if (dv.getUint32(p, true) !== 0x02014b50) break;
      var fnLen = dv.getUint16(p + 28, true);
      var exLen = dv.getUint16(p + 30, true);
      var cmLen = dv.getUint16(p + 32, true);
      var name = dec.decode(bytes.subarray(p + 46, p + 46 + fnLen));
      entries[name] = {
        method: dv.getUint16(p + 10, true),
        csize: dv.getUint32(p + 20, true),
        lhOff: dv.getUint32(p + 42, true)
      };
      p += 46 + fnLen + exLen + cmLen;
    }
    return { dv: dv, bytes: bytes, entries: entries };
  }
  function readZipEntry(z, name) {
    var e = z.entries[name];
    if (!e) return Promise.resolve(null);
    var fnLen = z.dv.getUint16(e.lhOff + 26, true);
    var exLen = z.dv.getUint16(e.lhOff + 28, true);
    var start = e.lhOff + 30 + fnLen + exLen;
    var raw = z.bytes.subarray(start, start + e.csize);
    if (e.method === 0) return Promise.resolve(raw);
    if (e.method === 8) {
      if (typeof DecompressionStream === 'undefined') {
        return Promise.reject(new Error('当前浏览器不支持解压，请使用新版 Chrome / Edge'));
      }
      var ds = new DecompressionStream('deflate-raw');
      var stream = new Blob([raw]).stream().pipeThrough(ds);
      return new Response(stream).arrayBuffer().then(function (b) { return new Uint8Array(b); });
    }
    return Promise.reject(new Error('不支持的压缩方式：' + e.method));
  }
  function parseXmindBuffer(buf) {
    var z = parseZipEntries(buf);
    var dec = new TextDecoder('utf-8');
    return readZipEntry(z, 'content.json').then(function (cj) {
      if (cj) {
        var sheetsRaw = JSON.parse(dec.decode(cj));
        var sheets = sheetsRaw.map(function (s, i) {
          return {
            title: ((s.title || '') + '').trim() || ('画布 ' + (i + 1)),
            root: topicFromJson(s.rootTopic || {})
          };
        });
        if (!sheets.length) throw new Error('content.json 中没有任何画布');
        return { sheets: sheets };
      }
      return readZipEntry(z, 'content.xml').then(function (cx) {
        if (!cx) throw new Error('压缩包中未找到 content.json 或 content.xml');
        var doc = new DOMParser().parseFromString(dec.decode(cx), 'text/xml');
        var sheets = [];
        Array.prototype.forEach.call(doc.documentElement.children, function (sheetEl, i) {
          if (sheetEl.localName !== 'sheet') return;
          var titleEl = firstChildNamed(sheetEl, 'title');
          var topicEl = firstChildNamed(sheetEl, 'topic');
          if (!topicEl) return;
          sheets.push({
            title: (titleEl && titleEl.textContent.trim()) || ('画布 ' + (i + 1)),
            root: topicFromXml(topicEl)
          });
        });
        if (!sheets.length) throw new Error('content.xml 中没有任何画布');
        return { sheets: sheets };
      });
    });
  }

  var fileInput = document.getElementById('fileInput');
  document.getElementById('btnImport').addEventListener('click', function () { fileInput.click(); });
  fileInput.addEventListener('change', function () {
    var f = fileInput.files[0];
    fileInput.value = '';
    if (!f) return;
    f.arrayBuffer().then(parseXmindBuffer).then(function (data) {
      try { localStorage.removeItem(storageKey()); } catch (e) {} // 清理旧图的本地编辑
      DATA = data;
      reassignAll();
      currentSheet = 0;
      selectedId = null;
      undoStack = []; redoStack = [];
      collapsed = {};
      document.title = DATA.sheets[0].root.title;
      buildTabs();
      foot.textContent = FOOT_TEXT;
      saveLocal();
      render();
      markDirty();
    }).catch(function (e) {
      alert('导入失败：' + e.message);
    });
  });

  // ---------- 初始化 ----------
  // 主题：本地记忆 > 默认深色
  var savedTheme = null;
  try { savedTheme = localStorage.getItem('xmind2html:theme'); } catch (e) {}
  applyTheme(savedTheme === 'light' ? 'light' : 'dark');

  // 本地编辑恢复
  try {
    var saved = localStorage.getItem(storageKey());
    if (saved) {
      var parsed = JSON.parse(saved);
      if (parsed && parsed.sheets) {
        DATA = parsed;
        markDirty();
      }
    }
  } catch (e) {}

  reassignAll();

  // 多画布标签
  function buildTabs() {
    var tabs = document.getElementById('tabs');
    tabs.innerHTML = '';
    if (DATA.sheets.length <= 1) {
      tabs.style.display = 'none';
      return;
    }
    tabs.style.display = '';
    DATA.sheets.forEach(function (sheet, i) {
      var b = document.createElement('button');
      b.textContent = sheet.title;
      if (i === currentSheet) b.className = 'active';
      b.addEventListener('click', function () {
        tabs.querySelectorAll('button').forEach(function (x) { x.className = ''; });
        b.className = 'active';
        currentSheet = i;
        selectedId = null;
        undoStack = []; redoStack = [];
        render();
      });
      tabs.appendChild(b);
    });
  }
  buildTabs();

  render();
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
