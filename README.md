# xmind2html

将 `.xmind` 思维导图一键转换为**独立、可交互、可编辑的 HTML 页面** —— 单文件、零依赖、双击即可在浏览器中查看和编辑。

## 特性

- **纯标准库实现**：Python 3.6+，无需安装任何第三方依赖
- **双格式兼容**：同时支持新版 XMind（`content.json`）与旧版 XMind（`content.xml`）
- **XMind 风格横向脑图**：贝塞尔曲线连接、分支自动配色（8 色循环）
- **深色主题默认**：可一键切换浅色，主题选择本地记忆
- **节点增删改**：
  - 添加子节点 / 同级节点、双击或 F2 重命名、编辑备注、删除（含子树确认）
  - XMind 式快捷键：`Tab` 加子节点、`Enter` 加同级、`Delete` 删除、`F2` 重命名
  - 撤销 / 重做（`Ctrl+Z` / `Ctrl+Y`）
- **编辑持久化**：修改自动保存到浏览器 localStorage；「导出 HTML」把当前编辑结果保存为新的独立 HTML 文件，可直接分发
- **多画布支持**：XMind 文件含多个画布（sheet）时自动生成标签页切换
- **离线可用**：生成的 HTML 无任何外部资源引用

## 使用方法

```bash
# 输出与输入同目录同名的 .html
python xmind2html.py 导图.xmind

# 指定输出路径
python xmind2html.py 导图.xmind -o output.html

# 覆盖页面标题（默认取根节点标题）
python xmind2html.py 导图.xmind --title "我的导图"
```

## 生成页面的编辑操作

| 操作 | 方式 |
| --- | --- |
| 选中节点 | 单击节点 |
| 重命名 | 双击节点，或选中后按 `F2` / 点「重命名」 |
| 添加子节点 | 选中后按 `Tab` 或点「+ 子节点」 |
| 添加同级节点 | 选中后按 `Enter` 或点「+ 同级」 |
| 编辑备注 | 选中后点「备注」（带 ¶ 标记的节点有备注，悬浮查看） |
| 删除节点 | 选中后按 `Delete` 或点「删除」 |
| 移动节点 | 直接拖拽：拖到目标**中间**成为其子节点，拖到目标**上/下缘**插为其前/后同级（不可拖入自己的子树） |
| 展开 / 收起 | 点击节点上的 `−` / `+` |
| 撤销 / 重做 | `Ctrl+Z` / `Ctrl+Y`（或 `Ctrl+Shift+Z`） |
| 保存成果 | 点「导出 HTML」下载包含当前编辑的新文件 |
| 还原 | 点「重置」清除本地编辑，恢复原始内容 |

## 作为库调用

```python
from xmind2html import convert, parse_xmind

convert("导图.xmind", "导图.html")

data = parse_xmind("导图.xmind")   # {'sheets': [{'title': ..., 'root': {...}}]}
```

## 运行测试

```bash
python xmind2html.py examples/起名流程优化.xmind -o examples/起名流程优化.html
```

`examples/` 目录下提供了示例文件及其转换结果，可直接打开 `起名流程优化.html` 体验。

## License

MIT
