# 从通用画像推进到句式对照

先按章节控制比较，当前工具只接收完整摘要。每篇只计一个样本，目标组和领域参考组均须核验署名并对照 PDF 页面。探索性规则发现只使用 learning；development/test 不进入此工具。若想开展独立验证，应另建冻结方案，不把探索性输出改名为测试结果。

在 local/ 下准备 JSONL，每条记录包含 paper_id、label、role（target/reference）、page、section（abstract）、text、reviewed（true）和 reviewer。沿用 manifest 和 splits，不能只改记录上的分区字段。工具检查来源身份和页内文本匹配；审核声明的真实性、作者归属和文本是否完整仍需人工负责。

```powershell
python contrast.py --excerpts local/curated/abstract-contrast.jsonl --out local/reports/abstract-contrast.json
python -m unittest discover -s tests -v
```

templates/contrast-features.json 是可审阅的词面模式列表。输出每个模式在两组命中的论文数、分母、实际匹配短语和页码。同一篇重复五次仍只计一篇。模式未命中只表示没有该精确结构，不意味着没有同义表达；部分模式依赖研究设计，不能解释成作者习惯。

后续画像必须同时记录：支持实例、未出现的论文、参考组匹配、合著/期刊/年代混杂，以及选取规则是否看过当前样本。可提供多个有条件的组织方式，不将它们合并为作者永远遵守的一套模板。参考组小或不匹配时，零命中不能证明目标组专有。

本工具不训练模型、不调用付费 API、不输出作者分类结果或复刻成功率。证据输出仅保存到本地资料目录，原文不随代码同步。
