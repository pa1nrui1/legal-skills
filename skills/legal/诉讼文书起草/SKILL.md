---
name: 诉讼文书起草
description: 基于"六来源体系"和请求权基础分析，起草起诉状、答辩状、代理词、质证意见、保全申请书等诉讼文书。整合《法律文书汇编》（郑州市律师协会2023年度优秀法律文书汇编）格式标准，按总控当前事项记录和复盘台账衔接。当用户发送客户编号并提及"起诉状"、"答辩状"、"代理词"、"质证"、"保全"等指令时触发使用。
---

## 法律工作总控规则（强制）

执行本 Skill 前，必须先遵循：
- skills/legal/法律工作总控/references/practice-profile.md
- skills/legal/法律工作总控/references/matter-workspace-protocol.md
- skills/legal/法律工作总控/references/document-reading-protocol.md
- skills/legal/法律工作总控/references/source-boundary-protocol.md
- skills/legal/法律工作总控/references/ocr-correction-protocol.md
- skills/legal/法律工作总控/references/pkulaw-mcp-legal-verification-protocol.md

本 Skill 只处理「诉讼文书起草」专业任务；案件隔离、事项路径、文件读取、OCR 复查、来源披露、缺口归档、法规/案例/Wiki 核验和复盘台账更新均按法律工作总控共享协议执行。

## 旧规则废止（强制）

- 旧文中直接写死的客户目录、阶段目录、旧式台账写入、旧本地读取协议均不作为执行规则。
- 事项路径、当前事项、系统记录、业务文件区和复盘台账统一以法律工作总控 `matter-workspace-protocol.md` 为准。
- 不得静默写入复盘台账；确需更新时，先确认属于复盘台账更新并向用户说明。

# 诉讼文书起草Skill

## 轻量入口

本文件是瘦身后的触发入口，只保留任务边界、执行顺序和按需读取索引。完整流程、模板、清单、专项规则和长示例已迁移至 `references/完整流程.md`。

## 何时使用

- 用户明确提到「诉讼文书起草」或本 Skill frontmatter 描述中的任务。
- 用户请求生成、审查、分析、计算、管理或推进与「诉讼文书起草」对应的法律工作成果。
- 法律工作总控或上游 Skill 路由到本 Skill。

## 执行顺序

1. 先按法律工作总控确认当前事项、业务文件区、系统记录区和来源边界。
2. 判断用户任务是否可以用本轻量入口完成；如只是路由、状态判断或简短提示，不默认读取完整流程。
3. 需要生成正式文书、报告、清单、计算结果、可视化、专项审查或复杂分析时，按需读取 `references/完整流程.md` 的相关章节。
4. 读取外置细节时，只读取当前任务需要的章节；不要为一个小问题整篇加载完整流程。
5. 输出前同步披露已读取材料、已核验内容、未核验/存疑内容、法规案例检索状态和需要用户判断事项。

## 要素式起诉状输出规则

模板登记中已覆盖案由的法院要素式起诉状必须使用 DOCX 母版克隆填充链路，不得退回传统段落式起诉状模板或普通 HTML 表格重制格式。答辩状和“实例”文件不适用本规则。

当前强制适用案由：

- 民间借贷纠纷
- 离婚纠纷
- 买卖合同纠纷
- 金融借款合同纠纷
- 物业服务合同纠纷
- 银行信用卡纠纷
- 机动车交通事故责任纠纷
- 劳动争议纠纷
- 融资租赁合同纠纷
- 保证保险合同纠纷
- 证券虚假陈述责任纠纷

- 业务侧输出 `complaint-data.json`，记录当事人、送达、诉请、事实、担保、证据和落款字段，并为字段标注来源或缺口。
- 导出侧输出 `fill-plan.json`，使用表格坐标和锚点定位字段；多个“姓名：”“电话：”“日期：”等重复锚点必须用表格坐标区分。
- 正式 Word 由 `法律文书模板与导出/scripts/fill_docx_template.py` 克隆母版并填充；输出必须是清洁 DOCX，不得含 `w:ins`、`w:del` 或 `trackRevisions`。
- 质控以 `法律文书模板与导出/scripts/run_template_clone_qc.py` 和 `health_check.py --expect-clean-clone` 为准；未通过时退回字段、填充计划或模板登记修正。

生成起诉状业务输入前，先运行案由分流校验；案由精确命中上表时必须输出 `complaint-data.json`、`fill-plan.json`、`qc-meta.json`，未命中时走普通 HTML 技术路线，案由相近但不精确时先确认案由。

```bash
python scripts/complaint_business_gate.py route --case-cause "民间借贷纠纷" --doc-type "民事起诉状"
python scripts/complaint_business_gate.py check-output --case-cause "民间借贷纠纷" --output-kind template_clone --complaint-data complaint-data.json
```

使用结构化案件材料包做回归或工作草稿抽取时，先运行材料抽取脚本生成业务输入和来源记录；脚本只使用材料包明示字段，缺失内容必须进入 `known_gaps`，不得自动补全。

```bash
python scripts/material_to_complaint_input.py --materials materials.json --out /tmp/complaint-input
```

使用真实文件做回归或工作草稿抽取时，必须先读取文件并生成结构化材料包；文件读取失败、图片 OCR 不可用或存在不可确认内容时，不得继续生成起诉状输入。

```bash
python scripts/files_to_material_packet.py --files 当事人信息.docx 事实证据.pdf --case-cause "民间借贷纠纷" --out /tmp/file-to-complaint
```

## 证据目录格式门禁

涉及证据目录时，必须先读取 `诉讼文书起草/templates/证据目录格式.md`。证据目录默认使用 `第一组证据`、`证明目的` 等分组文本段落结构；未经用户明确覆盖不得改成表格版。用户要求“直接用表格”时，应先作为格式偏离确认事项记录，不得跳过模板读取、材料完整读取、读取复查摘要和出稿前审查。

输出计划或门禁拦截说明中必须原样出现 `未经用户明确覆盖不得改成表格`，不得改写成“未经你确认”等泛化表述。

## 按需读取索引

- `references/完整流程.md`：瘦身前完整正文，含详细流程、模板索引、专项规则、交互规范和注意事项。
- `references/`：本 Skill 的专业规则、清单、方法论和外置参考材料。
- `templates/`：文书、报告、表格等输出模板；仅在需要生成对应成果时读取。
- `assets/`、`scripts/`、`checklists/`、`reference/`：如目录存在，仅在完整流程或当前任务明确需要时读取。

## 输出底线

- 不跳过用户提供的材料；读取失败必须说明。
- 不用模型记忆替代法律法规核验；引用法规、案例、Wiki 或网页搜索时必须标注来源和核验状态。
- 材料不足时提示缺口，不悄悄补全。
- 需要写入系统记录、复盘台账、飞书文档或飞书日历时，按总控和对应飞书 Skill 规则执行。
