# xmind2html

把 `.xmind` 思维导图变成**可编辑的网页脑图** —— 单文件、零依赖、纯浏览器本地解析，文件不上传。

**在线试用**：https://digua0222-stack.github.io/xmind2html/

## 快速开始（无需 Python）

**双击打开 `index.html`（或直接访问上面的在线地址），把 .xmind 文件拖进去，即可查看和编辑。**

也可以点页面上的「选择 .xmind 文件」按钮。编辑完成后点「导出 HTML」，得到一个内嵌数据、可直接分发的独立页面。

## 功能

- **拖拽导入**：把 .xmind 文件拖入窗口任意位置即可打开（拖入时有全屏高亮提示）
- **XMind 风格横向脑图**：贝塞尔曲线连接、分支自动配色（8 色循环）、节点折叠、30%–200% 缩放
- **深色主题默认**：可一键切换浅色，主题选择本地记忆
- **增删改**：
  - 添加子节点 / 同级节点、双击或 `F2` 重命名、编辑备注、删除（含子树确认）
  - 快捷键：`Tab` 加子节点、`Enter` 加同级、`Delete` 删除、`F2` 重命名
  - 撤销 / 重做（`Ctrl+Z` / `Ctrl+Y`）
- **节点拖拽移动**：拖到目标中间成为其子节点，拖到上/下缘插为前/后同级（禁止拖入自己的子树）
- **持久化**：编辑自动保存到浏览器 localStorage，刷新不丢；「重置」可还原
- **导出**：把当前编辑结果保存为新的独立 HTML，自带全部编辑能力，可直接发给他人
- **双格式兼容**：同时支持新版 XMind（`content.json`）与旧版 XMind（`content.xml`），备注（notes）一并解析
- **多画布支持**：XMind 文件含多个画布（sheet）时自动生成标签页切换

## 命令行转换（可选）

CLI 的作用是**预装数据**：生成一个打开即是目标脑图的独立页面，适合批量转换或归档。

```bash
# 输出与输入同目录同名的 .html
python xmind2html.py 导图.xmind

# 指定输出路径 / 覆盖页面标题
python xmind2html.py 导图.xmind -o output.html
python xmind2html.py 导图.xmind --title "我的导图"
```

CLI 以同目录的 `index.html` 为模板注入数据，生成的页面与应用本体完全一致，两者不会走岔。

## 作为库调用

```python
from xmind2html import convert, parse_xmind

convert("导图.xmind", "导图.html")

data = parse_xmind("导图.xmind")   # {'sheets': [{'title': ..., 'root': {...}}]}
```

## 文件结构

```
index.html        # 应用本体：双击打开，拖入 .xmind 即用
xmind2html.py     # CLI：预装数据生成分发页（复用 index.html 模板）
examples/         # 示例 .xmind 及 CLI 转换结果
```

## 运行测试

```bash
python xmind2html.py examples/起名流程优化.xmind -o examples/起名流程优化.html
```

## License

MIT
