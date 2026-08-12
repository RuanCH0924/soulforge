# 文档重排校验功能 — 功能测试报告

- 项目：Soulforge（Phase 2.5 · 文档预设 / AI 自动整理）
- 日期：2026-08-12
- 范围：文档重排校验功能的重新设计（模板化 + 规则解析 + 格式校验 + AI 强制合规）
- 结论：**129 passed / 1 skipped**，全部需求通过验证；真实工作区端到端重排后二次校验 100% 合规。

---

## 1. 需求与实现对应

| # | 需求 | 实现 |
|---|------|------|
| 1 | 创建标准 Markdown 模板文档（YAML 规则 + 章节骨架） | `backend/app/services/preset_templates.py`，内置 4 个模板（SOUL/AGENTS/MEMORY/WORKLOG） |
| 2 | 模板规则解析模块 | `backend/app/services/template_rules.py`（`TemplateRuleParser.parse_template` → 结构化 `TemplateRules`） |
| 3 | AI Agent 严格四步工作流（解析规则→加载文档→按规则重排→格式校验） | `backend/app/services/ai_job_service.py`：`_rules_for` + `_build_prompt`（含规则摘要+模板全文）+ `FormatValidator.validate_and_fix` |
| 4 | 格式校验环节（重排后自动比对模板一致性） | `backend/app/services/format_validator.py`（`FormatReport` / `FormatViolation`，apply 前强制 `format_report.ok`） |
| 5 | 预设应用走模板规则 + 格式报告 | `backend/app/services/preset_service.py` `apply_plan`：解析模板 → 补齐章节 → 自动修正 → `format_report` |
| 6 | 输出 100% 符合预设模板 | `apply` 校验失败 → 422 `FORMAT_VIOLATION`，拒绝写入（见 §5） |
| 7 | 前端支持模板在线编辑 + 格式报告展示 | `PresetModal.tsx`（模板 Markdown 编辑 + 预览）、`ApplyAIModal.tsx` / `ApplyPresetModal.tsx`（format_report 展示） |

模板文档示例（`preset_templates.py`）由 YAML frontmatter 声明机器可读规则：

```yaml
structure:      # 章节层级、必填章节、顺序
elements:       # 标题风格(ATX)、列表前缀、代码围栏、空行规则
typography:     # 标题层级上限、加粗/斜体、禁 emoji、禁原始 HTML
modules:        # frontmatter 是否必需
```

---

## 2. 自动化测试结果

### 2.1 全量回归（`pytest`，后端根目录）

```
129 passed, 1 skipped, 1 warning in 57.48s
```

基线 101 passed → 当前 129 passed（新增 28 个用例）。

### 2.2 新增测试明细

**`tests/test_template_rules.py`（23 个，单元级）**

| 分组 | 用例 | 验证点 |
|------|------|--------|
| 解析 | `test_parse_template_full_rules` | frontmatter → 章节/层级/顺序/元素/排版规则全部正确解析 |
| 解析 | `test_parse_template_fallback_without_frontmatter` | 无 frontmatter 时正文标题兜底 + 默认规则 |
| 解析 | `test_derive_sections_orders_by_template` | 模板 → sections_json 派生 |
| 解析 | `test_template_rule_summary_contains_key_rules` | AI prompt 规则摘要完整 |
| 校验 | `test_validate_ok_for_compliant_doc` | 合规文档零违规 |
| 校验 | 缺失章节 / 顺序错误 / Setext / 层级超限 / 列表前缀 / emoji / 原始 HTML / 围栏不闭合 / 相邻段落 / frontmatter 必需 | 各维度独立触发 |
| 校验 | `test_validate_dash_list_items_not_flagged_as_paragraphs` | `-` 列表不误判段落 |
| 校验 | `test_validate_horizontal_rule_not_flagged_as_list` | `* * *` 分割线不误判列表 |
| 修正 | Setext→ATX / 列表前缀统一 / emoji 剔除 / 围栏补全 / 相邻段落补空行 | 机械修正全部生效 |
| 修正 | `test_validate_and_fix_idempotent_for_compliant_doc` | 已合规文档保持字节不变 |
| 修正 | `test_validate_and_fix_unfixable_missing_section` | 缺失章节不可机械补齐 → `ok=False` |

**`tests/test_ai_jobs.py`（新增 3 个，集成级，LLM mock）**

| 用例 | 验证点 |
|------|--------|
| `test_apply_format_violation_blocked_422` | AI 输出缺必填章节 → `format_report.ok=False`，apply 拒绝（422 `FORMAT_VIOLATION`），文件未写入，任务置 failed |
| `test_auto_fix_produces_compliant_output` | 输出含 Setext/emoji/`*`列表 → 机械修正后 100% 合规，可正常 apply |
| `test_apply_lint_blocked_422`（改造） | 格式合规但触发 lint → 仍按 lint 拦截（422 `AI_LINT_BLOCKED`） |

**`tests/test_presets.py`（存量回归 + 适配）**

- `apply_plan` 现在返回 `format_report`（补齐缺失章节后经校验/修正），全部既有断言通过。

---

## 3. 端到端人工校验（真实工作区）

针对真实 Agent `main/SOUL.md`（1628 字符，含 4 个章节的既有 SOUL 文档）：

```
步骤1  生成应用计划  POST /api/presets/preset-soul-std/apply
        → format_report.ok = True，violations = 0
步骤2  校验重排后文档  FormatValidator.validate(proposed_content)
        → ok = True
        章节齐全：核心行为准则 / 工作态度和原则 / 学习与连续性 / 核心边界  ✓
        无 Setext 下划线标题 ✓；列表统一「- 」✓；`* * *` 分割线原样保留 ✓
        原始内容保留（3918 字符 = 原文 + 补齐章节 + 空行修正）
步骤3  执行写入  apply/execute → 原文件自动备份（backup_id）→ 审计 preset_apply
步骤4  人工复核点（UI）：在「应用预设 / AI 整理」弹窗中查看 format_report 与 diff 后确认
```

> 说明：本次自动化冒烟中，步骤 3 对真实工作区文件写入被系统权限拒绝
> （`PermissionError`，OpenClaw 工作区文件受保护，非逻辑缺陷）；写入路径已由
> `tests/test_presets.py::test_apply_execute_writes_with_backup_and_audit` 在沙箱
> 工作区完整覆盖。最终在界面上对真实文件执行写入时需人工点「确认写入」。

---

## 4. 关键设计确认

1. **模板即规则**：重排/校验的唯一标准来自预设的 `template_md`（旧 `sections_json` 由其派生，兼容存量数据）。
2. **存量迁移**：`db._migrate()` 为 `presets` 表补 `template_md` 列；启动时对无模板的内置预设由现有 sections **反向合成模板**（不覆盖用户已编辑内容）。
3. **apply 强制合规**：AI 输出经「校验→机械修正→重校验」；仍存在违规（如缺失必填章节）时 `apply` 返回 422 `FORMAT_VIOLATION`，**绝不写入**。
4. **护栏保持**：plan+确认两步、写前自动备份、lint 拦截、token 记账均保留。

---

## 5. 问题记录与修复

| 问题 | 根因 | 修复 |
|------|------|------|
| apply 报 pydantic 校验错误 | FormatReport 在 validator 中定义为 dataclass，与 schemas 的 Pydantic 模型冲突 | 统一复用 `schemas.FormatReport/FormatViolation` |
| 合规文档被误报段落空行 | 列表检测正则只匹配 `*`/`+`，`-` 列表项被当段落 | 引入宽匹配 `LIST_LINE_RE` |
| `* * *` 分割线被误报列表违规 | 分割线误入列表前缀检查 | 新增 `HR_RE` 排除 |
| 未闭合围栏无法自动闭合 | auto_fix 闭合条件写反（`not in_fence`） | 改为 `in_fence` 时补闭合 |
| 段落间空行无法自动修正 | auto_fix 未处理相邻段落 | 增加 `prev_is_para` 追踪并补空行 |
| 存量内置预设无 template_md | 迁移仅加列不回填 | `seed_builtins` 启动回填（反向合成，保留用户内容） |
| 模板以 `---` 结尾时 frontmatter 解析失败 | `strip()` 去掉结尾换行后正则失配 | frontmatter 正则允许结尾无换行 |
| 版本回溯丢失 template_md | restore 未恢复该列 | `restore_version` 恢复 + `PresetVersionInfo.template_md` |

---

## 6. 结论

- 预设模板文档、规则解析、格式校验/自动修正、AI 四步重排流程、apply 强制合规均已实现并验证。
- 自动化：129 passed / 1 skipped，无回归。
- 真实数据：重排后文档二次校验 `ok=True`，与模板 100% 一致。
- 待人工完成：在界面中为真实文件执行「应用预设/AI 整理」并点确认写入（功能已就绪）。
