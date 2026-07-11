# Bank Investment Analysis Skill

面向中国银行股投资研究的 Codex Skill。基于银行官方财报、附注、业绩会和宏观一手数据，完成财报预测、财报点评、同业比较、宏观传导及投研写作。

## 核心能力

- 完整展示资产、贷款、负债、存款细分量价、手续费、其他非息、费用、风险加权资产与资本。
- 打通不良生成、现金清收、核销、转让、拨备计提和贷款减值准备变化。
- 在披露不足时，以明确公式、假设和可靠程度反推核销区间及新生成不良代理下限。
- 使用144项核心底稿及可选扩展记录，将追溯数据内嵌到单一Markdown报告。
- 提供统一的彩色投研图表主题、财报评分、预测情景和宏观传导框架。

## 安装

在安装了 Codex 的环境中运行：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-installer/scripts/install-skill-from-github.py" \
  --repo edward-xiao/bank-investment-analysis \
  --path skills/bank-investment-analysis
```

安装后，该Skill会出现在：

```text
${CODEX_HOME:-~/.codex}/skills/bank-investment-analysis
```

如果本地已经存在同名Skill，安装器会停止以保护原文件；请先将旧目录重命名备份，再重新安装。安装完成后，在下一轮任务中即可使用。

## 使用示例

```text
$bank-investment-analysis 点评招商银行最新财报
```

```text
$bank-investment-analysis 预测某银行下一季度营业收入、净利润、净息差和资产质量
```

```text
$bank-investment-analysis 分析降息、存款重定价和地方债置换对银行业的传导影响
```

## 仓库结构

```text
skills/bank-investment-analysis/
├── SKILL.md
├── agents/
├── assets/
├── references/
└── scripts/
```

Skill包内只保留运行所需的指令、模板、参考方法和确定性脚本，不包含原始文章语料、银行官方PDF或第三方报告全文。

## 验证

```bash
python3 -m unittest discover \
  -s skills/bank-investment-analysis/scripts \
  -p 'test_*.py'
```

## 免责声明

本项目用于学习和投资研究，不构成投资建议。使用者应独立核验财务数据、估算假设和投资结论。

## License

[MIT](LICENSE)
