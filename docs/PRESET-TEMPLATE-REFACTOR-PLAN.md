# Soulforge — 预设模板文档可维护性改造方案（预设参考文档 + 结构化规则 + 修改要求）

> 配套文档：[DEVELOPMENT.md](DEVELOPMENT.md)（模块矩阵 · M11 文档预设）、[DATA-MODEL.md](DATA-MODEL.md)（预设表结构）、
> [API.md](API.md)（预设端点）、[MEMORY-DAILY-STANDARDIZER-PLAN.md](MEMORY-DAILY-STANDARDIZER-PLAN.md)（M15 规则载体）、
> [UI-SPECS.md](UI-SPECS.md)（预设编辑交互）。
> 状态：**已交付**（P0 / P1 / P2 / P3 全部落地；最新口径见 v1.2）。

### 修订记录

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-10-02 | 初版：问题定位（单文档承载三类信息）、选型对比、目标数据模型（`format_rules` + 纯骨架）、兼容迁移、前后端改动清单、测试与验收、风险回退 |
| v1.1 | 2026-10-02 | **已交付**：`presets.format_rules_json` 新列 + `parse_preset` 单一入口（`parse_template` 降为兼容别名）+ 惰性兼容读取 + API 层 `template_md` 恒为纯骨架；5 个内置骨架 + `BUILTIN_FORMAT_RULES`；`PresetTemplateEditor` 共享组件接入三处；「设为预设」改为「可选章节」口径；新增黄金等值测试 `test_preset_template_migration.py`（含非默认排版定制保留）。全量 `pytest` 372 passed / 1 skipped，`npm run build` 通过 |
| v1.2 | 2026-10-02 | **最新口径（覆盖 v1.0/v1.1 的下列设计）**：① **彻底删除「章节」配置**——不再有「章节（n）· 顺序即产出文档的章节顺序」清单面板 / 可选勾选 / 排序 / 增删 / 「章节顺序」复选框；`section_order` / `optional_sections` 字段与「必填章节 / 章节顺序」校验一并下线；`required_sections` 恒由**预设参考文档**标题派生，仅供「应用预设」机械补齐，**不再作为模型约束**。② 「章节骨架（Markdown；含示例与表格）」统一改名为「**预设参考文档**」。③ 「风格与内容规则」统一改名为「**修改要求**」。④ 大模型处理**所有文档修改类任务**时仅以「预设参考文档」+「修改要求」两项配置为核心参照依据。 |

> ⚠️ **阅读提示（v1.2 起生效）**：本文档 v1.0 / v1.1 段落中出现的
> 「章节骨架」「可选章节」「章节清单」「可选标记 / 排序 / 增删」
> 「风格与内容规则」「`section_order`」「`optional_sections`」等表述，
> 均为**改造过程的历史记录**，现已被 v1.2 取代：
> - 「章节骨架」现称「**预设参考文档**」；「风格与内容规则」现称「**修改要求**」；
> - 章节不再是独立配置（无顺序 / 无必填 / 无可选），章节结构只由预设参考文档的标题派生。
>
> 面向当前实现的权威描述以 [DEVELOPMENT.md](DEVELOPMENT.md) / [DATA-MODEL.md](DATA-MODEL.md) /
> [API.md](API.md) / [UI-SPECS.md](UI-SPECS.md) 为准。

---

## 一、背景与问题

三类文档预设（**一般文档预设**、**工作日志标准化 WORKLOG**、**日志总结 SUMMARY**）目前都把模板
存成同一个字段 `presets.template_md`，内容是 **YAML frontmatter（机器格式化规则）+ Markdown 正文骨架** 的合并文档，
见内置常量 [preset_templates.py](../backend/app/services/preset_templates.py)（如 `WLOG_DAILY_TEMPLATE`）。

两个编辑入口也都是一个裸 `textarea`：

- 设置页 / 主工作台：[PresetModal.tsx](../frontend/src/components/PresetModal.tsx) 「模板文档（YAML 格式化规则 + Markdown 章节骨架）」
- 日志标准化 / 日志总结：[DailyPresetEditor.tsx](../frontend/src/components/DailyPresetEditor.tsx) 同名字段

### 1.1 真正的问题不是「YAML 难写」，而是「三类信息挤在一起」

一个 `template_md` 同时承载了三类**受众与变更频率完全不同**的信息：

| 信息 | 谁在用 | 普通用户是否需要维护 |
|---|---|---|
| `structure.required_sections` | `FormatValidator` 机械校验 | 基本不用——它与正文 `##` 标题**完全重复**（见下） |
| `elements` / `typography`（11 个键） | `FormatValidator` 排版校验 | 几乎不用——所有内置预设取值完全一致，属"全局排版约定" |
| 正文 `##` 骨架（含示例 / 表格） | 模型 prompt | **需要**——这才是用户真正想改的 |

### 1.2 已存在的冗余与"死旋钮"（代码事实）

- **章节重复**：`parse_template()` 在没有 YAML 时会直接从正文标题派生 `required_sections`
  （[template_rules.py](../backend/app/services/template_rules.py#L110-L118)）；`preset_service.create/update`
  也总是用 `derive_sections(template_md)` 覆盖 `sections_json`（[preset_service.py](../backend/app/services/preset_service.py#L646-L651)）。
  也就是说 **YAML 里的章节清单是正文标题的手抄副本**。
- **prompt 重复**：M15/M16 组装 prompt 时既注入 `template_rule_summary(rules)`（已含章节清单），又把
  `template_md` 原文（又含一遍章节 + 整段 YAML）塞进 prompt（[daily_merge_service._rule_block](../backend/app/services/daily_merge_service.py#L304-L328)）。
- **死旋钮**：`heading_style` / `blockquote_prefix` / `allow_bold` / `allow_italic` 会被解析，
  但 `FormatValidator` **从未消费**（[format_validator.py](../backend/app/services/format_validator.py#L107-L201) 用到的
  规则键只有 `required_sections / section_heading_level / section_order / max_heading_level / forbid_emoji /
  forbid_raw_html / list_style / code_fence / heading_blank_line / paragraph_blank_line / frontmatter`）。
- **无法表达「可选章节」**：SUMMARY 的「附录：溯源对照表」刻意 **不** 进 `required_sections`
  （[preset_templates.py](../backend/app/services/preset_templates.py#L239-L245)），但它只能靠"YAML 里不写"来实现，
  用户在正文里看到这个 `##` 标题时无法知道它是可选的。

---

## 二、目标与非目标

### 2.1 目标

1. 普通用户维护预设时**不接触 YAML**：只需维护「章节骨架」与少量开关。
2. 消除信息重复（章节清单不再手抄）与死旋钮（无人消费的排版键不再出现在用户面前）。
3. 明确表达「可选章节」（附录类章节），且不污染正文标题文本。
4. 对存量安装、版本历史、M15/M16 业务链路**零行为回归**。

### 2.2 非目标（本次不做）

- 不改 `frontmatter_json`（它是"目标文档的 frontmatter 模板"，与模板规则是两回事，保持现状）。
- 不改 `presets` 的版本 / 快照 / 退役 / 播种迁移机制本身。
- 不做富文本所见即所得编辑器（骨架仍以 Markdown 文本为准，降低实现与回归风险）。
- 不把排版键外置为 `config.toml`（先收敛为代码级全局默认；确有需要再单独立项）。

---

## 三、方案选型

| 方案 | 做法 | 可维护性 | 改动面 | 结论 |
|---|---|---|---|---|
| **C · 仅 UI 表单化** | 不改数据模型，前端解析 `template_md` → 表单，保存时合成回 YAML+正文 | 中（底层仍单字段，高级编辑易丢结构） | 小 | 不采纳为终态 |
| **B · 拆分两字段 + 表单**（**推荐**） | 新增结构化规则字段；`template_md` 语义收窄为纯骨架；其余排版键收敛为全局默认 | 高 | 中（含兼容解析与迁移） | **采纳** |
| **A · 骨架 + 全局规则 + 极简预设开关** | 在 B 基础上把排版键彻底外置为全局配置 | 最高 | 大 | B 已覆盖主要收益，A 暂缓 |

**选型结论：方案 B**。拆成「**结构化规则**」+「**Markdown 章节骨架**」两个独立字段；同时**收敛旋钮**——
预设级只保留 4 个真正需要按预设区分的开关，其余排版键收敛为代码级全局默认。

---

## 四、目标数据模型

### 4.1 字段划分

| 字段 | 现状 | 改造后 |
|---|---|---|
| `presets.template_md` | YAML + 正文骨架 | **语义收窄为纯 Markdown 章节骨架**（新写入不含 `---` frontmatter；读取兼容旧值） |
| `presets.sections_json` | 由模板派生 | 保持派生、**只读**（不新增编辑入口） |
| `presets.format_rules_json`（**新增列**） | — | 结构化格式化规则（见 4.2） |
| `presets.style_rules` | 弱规则清单 | 不变（仍是注入 prompt 的弱规则） |
| `presets.frontmatter_json` | 目标文档 frontmatter 模板 | 不变（本次不动） |

### 4.2 `format_rules` 结构（预设级，schema 化）

```json
{
  "schema": "soulforge.format-rules/v1",
  "section_heading_level": 2,
  "section_order": "strict",
  "optional_sections": ["附录：溯源对照表"],
  "require_frontmatter": false
}
```

字段说明：

| 键 | 默认 | 说明 |
|---|---|---|
| `section_heading_level` | `2` | 章节标题层级（`##`） |
| `section_order` | `"strict"` | `strict` = 严格顺序；`loose` = 不强制顺序 |
| `optional_sections` | `[]` | 出现在骨架里、但**不参与强规则必填校验**的章节标题（如 SUMMARY 的附录） |
| `require_frontmatter` | `false` | 目标文档是否必须以 `---` 开头（被 `MOD-FRONTMATTER` 消费） |

### 4.3 字段归属（收敛清单）

| 规则键 | 改造前 | 改造后 | 理由 |
|---|---|---|---|
| `required_sections` | YAML 手写 | **由骨架标题派生**（减去 `optional_sections`，顺序 = 文档顺序） | 与正文完全重复 |
| `section_heading_level` | YAML | 预设级（表单） | 少数预设可能需要 |
| `section_order` | YAML | 预设级（表单） | 少数预设可能需要 |
| `optional_sections` | 无法表达 | 预设级（表单，新） | 修正"附录被误判必填"的表达缺口 |
| `frontmatter` | YAML `modules` | 预设级（表单，`require_frontmatter`） | 被 `MOD-FRONTMATTER` 实际消费 |
| `max_heading_level` | YAML | 全局默认 `3` | 全部内置预设一致 |
| `list_style` / `code_fence` | YAML | 全局默认 `-` / ```` ``` ```` | 同上 |
| `heading_blank_line` / `paragraph_blank_line` | YAML | 全局默认 `true` | 同上 |
| `forbid_emoji` / `forbid_raw_html` | YAML | 全局默认 `true` | 同上 |
| `heading_style` / `blockquote_prefix` / `allow_bold` / `allow_italic` | YAML（校验未消费） | **收敛为全局默认（不再进预设）** | 死旋钮 |

> 全局默认的唯一事实源 = `TemplateRules` 的 dataclass 默认值（[template_rules.py](../backend/app/services/template_rules.py#L26-L46)）。
> 若某存量预设**确实改过**某排版键（与全局默认不同），迁移时把它写进 `format_rules_json` 的覆盖项，避免行为变化（见第六节）。

---

## 五、解析逻辑（单一入口）

新增 `parse_preset(template_md, format_rules_json) -> TemplateRules`（替代各处直接 `parse_template`）：

```
优先级（高 → 低）：
  format_rules_json（新字段）
  > template_md 内的旧 YAML frontmatter（存量兼容）
  > 全局默认（TemplateRules 默认值）

章节：
  body = 去掉 frontmatter 后的正文
  headings = body 中 level == section_heading_level 的标题（保持文档顺序）
  required_sections = [h for h in headings if h not in optional_sections]
  （A 类内置预设无需改动；SUMMARY 的附录通过 optional_sections 表达）
```

- `TemplateRules` 数据类**不再新增字段**（结构不变，只是来源变了），`FormatValidator` 零改动。
- `template_rule_summary()` 可顺带清理：删掉死旋钮（`heading_style / blockquote_prefix / allow_bold / allow_italic`）的输出，避免误导模型。
- `derive_sections()` 语义不变（仍从骨架派生 `sections_json`）。

---

## 六、兼容与迁移

**策略：读取时惰性归一（不写库），首次经新编辑器保存时落库。**（与项目"用户改过的一律不动"的保守口径一致，避免全量导出版本扰动。）

1. **读取兼容**：`parse_preset` 检测 `template_md` 是否带 frontmatter；带则视为存量数据，
   按优先级合并进规则、正文作为骨架使用。**不修改数据库**。
2. **保存即迁移**：用户在任一编辑器保存时：
   - `template_md` 写入**纯骨架**（去掉 frontmatter）；
   - `format_rules_json` 写入结构化规则（含从旧 YAML 提取的非默认覆盖项）；
   - 走既有 `update()`：`version + 1` + 版本快照（[preset_service.py](../backend/app/services/preset_service.py#L636-L663)）。
3. **内置常量升级**：`BUILTIN_TEMPLATES` 拆成「纯骨架常量」+「`BUILTIN_FORMAT_RULES` 映射」；
   存量安装通过既有 `BUILTIN_PRESETS_REFRESHED` 迁移（内容锚点判"用户改过没有"）。
4. **回退**：`format_rules_json` 为空即退回旧逻辑（解析 `template_md` 的 YAML）→ 旧版本代码可继续运行，
   数据层只多一列（`ALTER TABLE presets ADD COLUMN format_rules_json TEXT`，沿用 [Database._migrate](../backend/app/models/db.py#L341-L353)）。

> **为什么不启动时全量迁移**：会批量 `version + 1` 并刷版本历史，且需要逐条判断"用户是否改过"，
> 风险收益比不划算。惰性方案零风险，且天然只改动用户真正编辑过的预设。

---

## 七、后端改动清单

| 位置 | 改动 |
|---|---|
| `models/db.py` | `PresetRow` 增列 `format_rules_json`；`_migrate()` 补 `presets` 的 ALTER |
| `models/schemas.py` | `Preset` / `PresetCreate` / `PresetUpdate` / `PresetVersionInfo` 增 `format_rules: dict`；`PresetFromDocument` 保留 `section_heading_level / section_order / require_frontmatter`，新增 `optional_sections` |
| `services/template_rules.py` | 新增 `parse_preset` / `GLOBAL_DEFAULTS` / `rules_to_dict`；`parse_template` 保留（存量兼容 + 单测） |
| `services/preset_service.py` | CRUD / 快照 / 恢复 / 播种接入 `format_rules_json`；`rules_for()` 改调 `parse_preset`；`_compose_template` / `_synthesize_template` / `create_from_document` 改为"骨架 + rules"两个产物（不再拼 YAML） |
| `services/preset_templates.py` | 5 个内置模板改为**纯骨架**；新增 `BUILTIN_FORMAT_RULES` |
| `services/daily_merge_service.py` | `_rule_block` 的骨架来源改为"去 frontmatter 的正文"（消除 prompt 里的 YAML 重复） |
| `api/presets.py` | 透传 `format_rules`（若现有端点用 `Preset**` 自动序列化则无需改） |

---

## 八、前端交互设计

### 8.1 统一编辑器（替换两处裸 textarea）

抽出共享组件 `PresetTemplateEditor`，`PresetModal` 与 `DailyPresetEditor` 共用，杜绝两处漂移：

1. **章节清单（结构化，默认视图）**
   - 从骨架的 `##` 标题自动列出，每行：标题（可改名）、`必填 / 可选` 切换（→ `optional_sections`）、上移 / 下移（→ 顺序）。
   - 新增章节按钮；删除章节。
   - 副标题说明："标题顺序即产出文档的章节顺序"。
2. **章节骨架（Markdown，进阶视图）**
   - 保留示例 / 表格（如「关键决策」的表格），带渲染预览开关；
   - 与章节清单**双向同步**：以骨架标题为真相，清单只负责"可选 / 顺序"标记与展示。保存时校验
     `optional_sections ⊆ 骨架标题`。
3. **高级格式规则（默认折叠）**
   - 章节层级（下拉，默认 2）、章节顺序（严格 / 不严格）、要求 YAML frontmatter（勾选）。
   - 其余排版键**不出现在 UI**（全局默认）。
4. **风格与内容规则**：保持现状（每行一条）。

### 8.2 其他入口

- 「设为预设」（`create_from_document`）：从当前文档标题生成骨架 + 默认 `format_rules`；
  弹窗增加「哪些章节可选」的勾选（对应 `optional_sections`），替代现在的"哪些必填"反向选择。
- 版本历史 / 回溯：展示 `format_rules` 摘要（如"层级 2 · 严格顺序 · 1 个可选章节"），回溯逻辑不变。

---

## 九、Prompt 影响

- M15/M16 的规则投递形态（`doc_full` / `trimmed` / `system_embedded`）**不变**；
  仅把注入的"模板文档全文"从 `template_md`（含 YAML）换成**纯骨架**，同时 `template_rule_summary` 去掉死旋钮。
- 预期收益：prompt 输入更短、噪声更少（章节清单不再出现两遍）；输出契约由 `FormatValidator` 照旧机械保证。
- 需回归验证：三形态下的强规则通过率与输出一致性（可用现有对比台
  [daily_form_bench.py](../backend/daily_form_bench.py) 抽样复测，非必选）。

---

## 十、测试方案

| 层 | 用例 | 通过标准 |
|---|---|---|
| 单元 · 解析 | `parse_preset` 的优先级（新字段 > 旧 YAML > 默认）；`optional_sections` 不进 `required_sections`；非默认排版键覆盖生效 | 100% |
| 单元 · 兼容 | **黄金等值测试**：对 5 个内置预设，断言"旧 `parse_template(template_md)` 的结果"== "新 `parse_preset(骨架, rules)` 的结果"（逐字段） | 完全一致（这条是防行为回归的核心闸门） |
| 单元 · 迁移 | 惰性读取不写库；保存后 `template_md` 无 frontmatter、`format_rules_json` 正确 | 100% |
| 集成 | 预设 CRUD / 快照 / 回溯 / `create_from_document`；M15 批次与 M16 归纳全流程（LLM mock） | 零回归 |
| 回归 | 既有 `pytest` 全量 + `npm run build` | 全绿 / 退出码 0 |

已有相关测试：`backend/tests/test_presets.py`、`test_template_rules.py`、`test_daily_*`；改造后需扩充。

---

## 十一、排期与验收

| 阶段 | 内容 | 规模 | 验收门 |
|---|---|---|---|
| **P0 · 解析地基** | 新增 `format_rules_json` 列 + `parse_preset` / 全局默认 + 惰性兼容；黄金等值测试 | S | 全部内置预设新旧解析等值；`pytest` 全绿 |
| **P1 · 后端落库** | CRUD / 快照 / 恢复 / 播种 / `create_from_document` / `_rule_block` 接入 | M | 预设接口往返正确；M15/M16 集成测试零回归 |
| **P2 · 前端编辑器** | 共享 `PresetTemplateEditor`（章节清单 + 骨架 + 高级折叠）替换两处 textarea | M | 普通用户可无 YAML 完成"增删章节 / 标可选 / 调顺序 / 改示例" |
| **P3 · 文档与清理** | 更新 DATA-MODEL / API / DEVELOPMENT / UI-SPECS；内置常量改纯骨架 | S | 文档与实现一致；`npm run build` 通过 |

**验收标准（量化）**

1. 任一预设的模板维护全程**不出现 YAML**（高级模式下也不要求用户理解 YAML）。
2. 5 个内置预设"旧解析 == 新解析"逐字段一致（黄金测试）。
3. SUMMARY 的「附录」在 UI 上明确标为**可选**，且不会被强规则拦死。
4. `template_md` 中不再需要手写章节清单（由骨架单一派生）。
5. 存量安装、版本历史、M15/M16 流程零行为回归（`pytest` 全绿 + `npm run build` 退出码 0）。

---

## 十二、风险与回退

| 风险 | 影响 | 应对 |
|---|---|---|
| 强规则行为被无意改变 | 既有批次/整理结果变化 | **黄金等值测试**卡住：内置预设逐字段断言新旧解析一致 |
| 存量用户改过排版键被收敛掉 | 个别用户的定制失效 | 迁移时把"与全局默认不同"的键写入 `format_rules_json` 覆盖项 |
| 骨架与章节清单漂移 | 校验与展示不一致 | 以骨架标题为唯一真相；`optional_sections ⊆ 骨架标题` 保存校验 |
| 两处编辑器再次漂移 | 维护成本回升 | 抽共享组件，两处只传差异（notice / titlePrefix） |
| 前端表单化引入回归 | 保存丢内容 | 保留"原文模式"查看/编辑骨架；保存前 diff 提示 |

**回退方案**：`format_rules_json` 为空即走旧 YAML 解析路径；代码层可按 P0~P3 独立 `git revert`；
数据层仅多一列（旧代码忽略该列即可运行）。

---

## 附录 · 目标示例

内置「工作日志日标准化」改造后：

- `template_md`（纯骨架，无 YAML）：

```markdown
# 工作日志日标准化模板

> 逐日归并当日全部来源，剥离元数据壳与对话腔噪音后改写成客观记录。

## 一、今日概览

- **日期**：YYYY-MM-DD
- **核心活动**：用 1~3 条概括当天最重要的事

## 二、关键事件

### 事件 1

- 事实 / 原因 / 结果

## 三、关键决策

| 决策项 | 内容 |
|--------|------|
| ... | ... |

## 四、待办事项

- [ ] ...

## 五、明日计划

- ...
```

- `format_rules_json`：

```json
{ "schema": "soulforge.format-rules/v1", "section_heading_level": 2,
  "section_order": "strict", "optional_sections": [], "require_frontmatter": false }
```

- 「日志总结 SUMMARY」则把 `optional_sections` 设为 `["附录：溯源对照表"]`，其余一致。

---

*最后更新：2026-10-02 · v1.1（P0 / P1 / P2 / P3 已交付）*
