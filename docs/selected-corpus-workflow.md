# 精选语料与画像核验

用户选定代表作后，先按原文件哈希连接既有清单，不因复制到新文件夹就重新随机分区。

```powershell
python stylelab.py select --source '代表作文件夹' --out local/reports/selection-raw.json
```

审核作者名单、作者贡献声明及文档类型，把审核副本的 `role` 写成：

- `target_learning`：原 learning 集中的目标作者署名文章；仍需标记主笔/修改/未知。
- `target_holdout`：目标作者署名文章，但保留用于开发或测试，不用于画像。
- `field_reference`：无目标作者署名的领域参考，不能作为目标文风的正向证据。
- `pending_authorship_review`：尚未审核，不能进入精选画像。

这一步不改变 `splits.json`。所有集合切换必须单独记录理由，不可由选择文件夹隐式改变。相同文件名不能证明同一文章，也不能证明作者身份。

对照 PDF 页面精选完整段落。`excerpt_id` 唯一，记录来源、PDF页码、章节、审核者、作者贡献以及排版问题。不要把下载封面、批注、引用文献列表、表格、公式碎片混入散文统计。

```powershell
python stylelab.py profile --excerpts local/curated/selected.jsonl --selection local/reports/selection-reviewed.json --out local/profiles/selected-surface.json
python stylelab.py verify-sheet --sheet local/profiles/style-sheet.json --excerpts local/curated/selected.jsonl --selection local/reports/selection-reviewed.json --out local/reports/style-sheet-check.json
```

画像 JSON 的 `rules` 中每条包含 `id`、`rule`、`status`、`support_papers` 与 `evidence`。证据项为 `excerpt_id` 和精确短引文 `quote`。`cross_paper_observation` 至少需要三篇不同论文；不足时使用 `tentative`。同一篇论文多段不重复计为多篇。

核验器只确认来源、集合、引文匹配和独立论文计数，不自动证明规则解释正确、不验证实证结论，也不证明风格属于个人。所有文章来自同一期刊时，应明确期刊文体与个人风格尚未分离。

本地 Markdown 画像与可复用写作指令应同时保留反例和适用范围。当前不训练模型，不连接付费模型 API。用户完成 GitHub 访问授权后，仅同步代码、通用文档与模板。
