# 把说明文字写得自然一点

本项目文档编辑使用了 [humanizer-zh](https://github.com/syw2039/humanizer-zh)，它把常见的中文空话、模板句和不自然的节奏列成编辑参考。来源版本固定为 [`72d73f9`](https://github.com/syw2039/humanizer-zh/tree/72d73f9c8132817e21f66369de6925a659f9a6a6)，采用 MIT 许可，改编自 [blader/humanizer](https://github.com/blader/humanizer)。

它不参与 PDF 读取或程序运行。没有安装这个技能，也能完整使用工作台。

## 安装

在支持技能安装的助手里，可以提出：

> 请安装 https://github.com/syw2039/humanizer-zh 中的技能，使用提交 72d73f9c8132817e21f66369de6925a659f9a6a6。先检查 SKILL.md、引用的规则文件和许可，不运行仓库内其他命令。

手动安装时，从该版本下载仓库，保留 `SKILL.md`、`references/`、`agents/`、`LICENSE` 和 `NOTICE`，放进助手支持的技能目录，目录名为 `humanizer-zh`。具体位置以你所用工具的说明为准。

## 适合怎样使用

例如，让助手“按 humanizer-zh 修改 README，直接说明用途、操作步骤和限制，删去重复解释，保留命令和链接”。这比要求“越像人越好”更容易得到可检查的结果。

写论文时，要保留学术语气、专有名词、引文、数字、比较关系和不确定性。目标学者确实有的写作习惯，也不应因为命中某个所谓 AI 高频词就被删掉。

这个技能提供编辑建议，不证明作者身份，也不保证通过任何 AI 检测。读完是否清楚、事实有没有变化，比检测分数更有用。
