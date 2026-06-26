---
name: 法律文书出稿前审查
description: 在法律业务 Skill 生成正文或要素式字段后、法律文书模板与导出生成本地 Word 前触发。用于审查 draft.html/preflight-meta.json 或 complaint-data.json/fill-plan.json、读取复查摘要、法规校验摘要、来源边界和用户确认记录，决定是否可以进入正式 DOCX 导出；发现问题后必须闭环推进到业务 Skill 整改、用户确认或材料读取流程。
---

# 法律文书出稿前审查

本 Skill 是正式本地 Word 输出前的强制闭环审查节点，不替代业务 Skill 的事实判断、法律分析和正文起草。

## 法律工作总控规则（强制）

执行本 Skill 前，必须先遵循：
- skills/legal/法律工作总控/references/practice-profile.md
- skills/legal/法律工作总控/references/source-boundary-protocol.md

本 Skill 继承 `practice-profile.md` 的子 Skill 执行质量门；材料读取、法规核验、用户确认和来源边界缺失时，不得进入正式导出链路。

## 触发条件

- 最终产物是本地 `.docx` 的法律文书、报告、清单、笔录、意见书、函件、合同或正式交付文件。
- 普通线性文书：业务 Skill 已生成 `draft.html` 和 `preflight-meta.json`，准备进入 `法律文书模板与导出`。
- 要素式表单文书：业务 Skill 已生成 `complaint-data.json` 和 `fill-plan.json`，准备进入 DOCX 母版克隆填充链路。
- 用户直接点名业务 Skill 输出 Word 时，也必须先经过本 Skill。

格式测试稿、非正式实验稿可以例外，但必须明确标注不是正式交付。

## 输入

普通线性文书必须提供：

- `draft.html`：语义 HTML，使用 `h1`、`h2`、`h3`、`p`、`section`、`table` 等标签。
- `preflight-meta.json`：出稿前元数据，使用“声明 + 证据路径”，不得只写布尔值。

`preflight-meta.json` 至少包含：

```json
{
  "source_skill": "诉讼文书起草",
  "doc_type": "取保候审申请书",
  "output_purpose": "正式交付",
  "profile": "litigation_standard",
  "template_selection_path": ".../template-selection.json",
  "content_template_id": "registered_template_id",
  "content_template_version": "1.0",
  "content_template_sha256": "sha256",
  "profile_id": "litigation_standard",
  "profile_version": "1.0",
  "format_standard": "litigation_standard",
  "matter_path": "...",
  "system_record_path": "...",
  "evidence": {
    "reading_review_path": "...",
    "legal_verification_path": "...",
    "source_boundary_path": "...",
    "user_confirmation_source": "..."
  },
  "required_confirmations": [],
  "known_gaps": []
}
```

要素式表单文书必须提供：

- `complaint-data.json`：结构化字段，字段应有来源或缺口说明。
- `fill-plan.json`：字段到 DOCX 母版的表格坐标和锚点映射。
- `qc-meta.json`：模板 ID、事项路径、来源记录、读取复查、法规校验和用户确认记录。

## 审查命令

```bash
python scripts/preflight_check.py \
  --html draft.html \
  --meta preflight-meta.json \
  --output-html draft_checked.html \
  --report 出稿前审查报告.md
```

## 审查规则

- 核验 `draft.html`、`preflight-meta.json` 和证据路径是否存在、可读、内容匹配。
- 核验读取复查摘要、法规校验摘要、来源边界记录、用户确认记录是否真实存在。
- 如正文引用法律、法规、司法解释、案例、裁判规则等内容，必须有法规校验摘要。
- 如 `required_confirmations` 非空，必须能在用户确认记录中找到对应确认内容。
- 检查固定身份信息：
  - 律所：广东广和（长春）律师事务所
  - 律师：潘睿
  - 地址：净月区华荣泰七栋608室
  - 电话：18686488305
  - 邮箱：418869057@qq.com
- 检查 HTML 结构至少包含标题和正文；含表格时必须保留为真实 `table`。
- 检查 `profile` 是否能匹配 `法律文书模板与导出/assets/profiles/` 中的 profile；未命中时使用 `fallback_desktop_word`。
- 如 `preflight-meta.json` 记录了 `template_selection_path` 或 `content_template_id`，必须核验模板选择记录、模板版本、模板 sha256、profile 版本和兼容 profile；未登记模板、sha256 不一致、profile 不兼容或解除委托协议误用 `entrustment_contract` 时，必须阻断。
- 要素式表单文书检查模板 ID 是否命中 `template-clone-manifest.json`。
- 检查 `fill-plan.json` 中每个字段是否有唯一表格坐标和锚点；重复锚点不得只用全局文本定位。
- 检查字段缺口、金额、日期、主体、诉请和落款是否已确认；未确认字段不得写入正式字段。

## 自动修正边界

允许自动修正：

- 固定身份信息错误或缺漏。
- 简单 HTML 类名和标签修复。
- Markdown 表格转 HTML 表格。
- 明显格式类问题。

禁止自动修正：

- 事实、金额、日期、案号、诉讼请求、罪名。
- 授权范围、收费方式、合同核心条款。
- 法律依据、裁判项、风险结论。
- 用户尚未确认的实体选择。

## 输出状态

审查报告必须包含：

- `review_status`
- `next_owner`
- `next_action`
- `return_to_skill`
- `revision_items`
- `confirmation_questions`
- `evidence_required`
- `rerun_required`

状态含义：

- `PASS`：可以进入 `法律文书模板与导出`。
- `FIXED_PASS`：已完成低风险自动修正，可以进入 `法律文书模板与导出`。
- `NEEDS_BUSINESS_REVISION`：退回业务 Skill 整改正文、结构、法律分析或元数据。
- `NEEDS_USER_CONFIRMATION`：需要集中向用户确认事实、选择项、授权、收费、诉请、金额或期限。
- `NEEDS_MATERIAL`：需要补充材料、重新读取、OCR 或补充读取复查摘要。
- `HARD_BLOCK`：存在无法继续推进的根本问题。

## 闭环推进

- 不得只拦截问题；必须给出下一步归属和动作。
- `NEEDS_BUSINESS_REVISION`：退回 `source_skill`，按 `revision_items` 整改后重新运行本 Skill。
- `NEEDS_USER_CONFIRMATION`：向用户集中确认 `confirmation_questions`，写入用户确认记录后重新运行本 Skill。
- `NEEDS_MATERIAL`：回到 `法律工作总控` 的材料读取、OCR、读取复查和法规校验流程。
- 只有 `PASS` 或 `FIXED_PASS` 可以进入 `法律文书模板与导出`。
