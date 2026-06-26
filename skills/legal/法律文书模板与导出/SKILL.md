---
name: 法律文书模板与导出
description: 统一处理法律工作中最终需要输出本地 Word（.docx）的文书、报告、清单、笔录、意见书、函件、合同和正式交付文件。由法律工作总控强制路由调用；业务 Skill 负责正文和法律判断，本 Skill 负责选择格式 profile、接收语义 HTML 或要素式填充数据、导出 DOCX、结构体检和兜底模板。
---

# 法律文书模板与导出

本 Skill 只处理最终 Word 的格式与导出，不替代业务 Skill 的事实梳理、法律分析、文书正文生成、材料读取复查、法规核验和出稿前审查。

## 法律工作总控规则（强制）

执行本 Skill 前，必须先遵循：
- skills/legal/法律工作总控/references/practice-profile.md
- skills/legal/法律工作总控/references/source-boundary-protocol.md

本 Skill 继承 `practice-profile.md` 的子 Skill 执行质量门；审查报告、来源边界或验证结果缺失时，不得标记为正式交付。

## 强制路由

- 凡最终产物是本地 `.docx` 的法律文书、报告、清单、笔录、意见书、函件、合同或正式交付文件，必须调用本 Skill。
- `法律工作总控` 负责判断是否进入本 Skill；用户直接点名业务 Skill 生成 Word 时，业务 Skill 也必须先通过 `法律文书出稿前审查`，再调用本 Skill。
- 普通线性文书正式交付接收 `法律文书出稿前审查` 生成的 `draft_checked.html`，并必须附带审查报告。
- 要素式表单文书正式交付接收经质控通过的 `complaint-data.json`、`fill-plan.json` 和模板克隆质控报告，使用 DOCX 母版克隆填充链路。
- 审查报告不是 `PASS` 或 `FIXED_PASS` 时，禁止生成正式 `.docx`。
- 未命中专用 profile 时，使用 `fallback_desktop_word`。
- 原 Skill 中保留的 `python-docx`、`Node.js docx`、Word 导出示例或旧技术方案只作为迁移评估来源/历史参考；不得作为最终 Word 导出路径执行。
- 普通线性文书走本 Skill 的语义 HTML -> `html_to_docx.py` -> DOCX 链路。
- 要素式表单文书走 DOCX 母版 -> `fill_docx_template.py` -> 清洁 DOCX 链路；不得用全局字符串替换驱动正式填充。

## 输入约定

普通线性文书：业务 Skill 应先生成语义 HTML，并经 `法律文书出稿前审查` 生成 `draft_checked.html`。使用 XHTML 兼容写法：

- `h1`：文书标题。
- `h2` / `h3`：层级标题。
- `p.meta`：申请人、当事人、案号、法院、基础信息。
- `p.body` 或普通 `p`：正文段落。
- `p.signature`：落款。
- `table`：真实表格。
- `section`：附件、事实、理由、请求、证据目录等区块。

要素式表单文书：业务 Skill 应生成结构化字段和填充计划：

- `complaint-data.json`：当事人、送达、诉请、事实、担保、证据、落款等字段数据，字段应有来源或缺口说明。
- `fill-plan.json`：每个字段的表格坐标、锚点和填充模式；重复锚点必须用表格坐标定位。
- `qc-report.json` / `qc-report.md`：模板克隆质控报告，状态必须为 `PASS`。

## Profile

内置 profile 位于 `assets/profiles/`：

- `litigation_standard`：诉讼/刑辩通用文书。
- `legal_report`：法律服务建议书、检索报告、案件提纲等。
- `judgment_style`：民事判决书、审理报告等特殊法院文书样式。
- `entrustment_authorization`：委托合同管理-授权委托书。
- `entrustment_contract`：委托合同管理-委托代理合同。
- `entrustment_risk_notice`：委托合同管理-风险义务告知书。
- `entrustment_statement_record`：委托合同管理-委托人陈述笔录/案件沟通记录。
- `entrustment_supervision_card`：委托合同管理-服务质量监督卡。
- `legal_representative_certificate`：委托合同管理-法定代表人身份证明书。
- `contract_standard`：解除协议、补充协议、终止协议、无专门排版规范的合同正式文本。
- `litigation_visualization`：诉讼可视化图表嵌入 Word。
- `fallback_desktop_word`：无专用模板时的兜底桌面 Word。

## 模板匹配与版本门禁

全局模板登记表位于 `assets/legal-template-registry.json`，只做索引和门禁，不迁移各业务 Skill 的正文模板或外部模板文件。正式合同类 Word 如存在内容模板来源，应先生成 `template-selection.json`：

```bash
python scripts/select_legal_template.py \
  --source-skill 合同起草 \
  --doc-type 解除委托协议 \
  --business-scene 撤诉解除委托 \
  --user-request "客户撤诉，费用不退，留存抵扣后续法律服务" \
  --source-template-path "模板源文件.docx" \
  --output template-selection.json
```

选择结果必须写入 `preflight-meta.json`，至少包括 `template_selection_path`、`content_template_id`、`content_template_version`、`content_template_sha256`、`profile_id`、`profile_version` 和 `format_standard`。未命中登记表、模板 sha256 不一致、多候选冲突或 profile 不兼容时，不得进入正式导出。

## 导出命令

```bash
python scripts/html_to_docx.py \
  --input draft_checked.html \
  --output output.docx \
  --profile litigation_standard \
  --preflight-report 出稿前审查报告.md
```

如未指定或未找到 profile，脚本使用 `fallback_desktop_word`。

要素式表单文书导出：

```bash
python scripts/fill_docx_template.py \
  --template 母版.docx \
  --plan fill-plan.json \
  --output output.docx \
  --log fill-execution-log.json
```

一键质控验证：

```bash
python scripts/run_template_clone_qc.py \
  --template-id civil_complaint_private_lending_v1 \
  --fixture private_lending_basic \
  --out /tmp/legal_template_clone_qc
```

全部登记起诉状母版结构/渲染回归：

```bash
python scripts/run_template_clone_qc.py \
  --all \
  --fixture structure_only \
  --out /tmp/legal_template_clone_all_qc
```

双通道回归验证（同时验证旧 HTML 链路和新模板克隆链路）：

```bash
python scripts/run_dual_docx_qc.py --out /tmp/legal_dual_docx_qc
```

## 失败与兜底

- 普通线性文书的 `draft_checked.html`、审查报告或 profile 缺失时，停止导出并退回 `法律文书出稿前审查` 或业务 Skill 补齐。
- 要素式表单文书的模板登记、母版 DOCX、`complaint-data.json`、`fill-plan.json` 或模板克隆质控报告缺失时，停止导出并退回业务 Skill 或模板克隆质控补齐。
- `html_to_docx.py` 执行失败时，报告本次命令、错误摘要和输入文件路径；不得输出未验证的 `.docx`。
- 专用 profile 不存在、JSON 解析失败或 manifest 异常时，使用 `fallback_desktop_word` 重新导出，并在交付说明中标注兜底 profile。
- `health_check.py` 未通过时，不得宣称 Word 已交付；先修复导出问题，修复失败则保留中间文件和错误摘要。

## 验证命令

```bash
python scripts/health_check.py
python scripts/health_check.py --docx output.docx --expect-title "文书标题"
python scripts/health_check.py --docx output.docx --expect-title "解除委托协议" --format-standard contract_standard
python scripts/health_check.py --docx output.docx --expect-clean-clone --template-clone-report qc-report.json
```

验证至少检查：

- profile JSON 可解析。
- manifest 可解析。
- DOCX 可解包。
- `word/document.xml` 存在。
- 标题文本存在。
- 页边距配置存在。
- 指定 `--format-standard contract_standard` 时，反查 DOCX XML 中实际字号、字体和行距；合同正式文本正文和 meta 不得小于小四，行距应为 1.5 倍或固定 24-28 磅。
- 页码字段存在。
- 表格生成真实 `w:tbl`。
- 要素式表单文书的模板克隆 manifest 可解析。
- 清洁模板填充 DOCX 不含 `w:ins`、`w:del`、`trackRevisions` 或 comments。
- 模板克隆质控报告状态为 `PASS`。

正式交付包审计：

```bash
python scripts/audit_formal_delivery.py \
  --bundle-dir 正式交付目录 \
  --docx 正式交付文件.docx
```

正式 `.docx` 不得仅凭“文件已生成”标记完成；同一交付包必须具备 `draft.html`、`preflight-meta.json`、`draft_checked.html`、`出稿前审查报告.md`、最终 `.docx` 和 `health-check-report.txt`。审查报告状态必须为 `PASS` 或 `FIXED_PASS`，健康检查记录必须包含 `health_check_ok: True` 并指向最终 `.docx`。

## 迁移边界

- 只迁移 Word 排版和导出规则，不迁移正文范式、事实分析框架、法律论证模板、提示词库、质证句式库、信息采集表和案件流程规则。
- 原 Skill 中 `python-docx`、`Node.js docx`、Word 导出方案必须先评估，再标注为 `迁移替换`、`保留引用` 或 `暂不迁移`。
- 本轮不删除现有正文模板文件。
- 标注为 `保留引用` 或 `暂不迁移` 的旧技术段不得继续驱动最终 DOCX 生成；只保留其中的业务结构、特殊字段或风险提示价值。

## 禁止事项

- 禁止绕过 `法律文书出稿前审查` 直接导出正式 Word。
- 禁止修改业务正文、法律判断、事实认定或当事人信息来适配排版。
- 禁止在审查报告为 `NEEDS_BUSINESS_REVISION`、`NEEDS_USER_CONFIRMATION` 或 `NEEDS_MATERIAL` 时生成正式 `.docx`。
- 禁止把验证失败的 `.docx` 标记为最终交付文件。
