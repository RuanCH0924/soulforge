/** Soulforge 前端类型定义（与后端 Pydantic schema 一一对应，见 docs/API.md） */

/** GET /api/health：后端版本号（全项目版本事实源 app/__init__.py） */
export interface HealthResult {
  status: string;
  version: string;
}

export interface AgentInfo {
  id: string;
  workspace: string;
  display_name?: string | null;
  file_count: number;
  last_scanned_at?: number | null;
  created_at?: number | null;
  updated_at?: number | null;
}

export type FileRole = 'CORE' | 'MEMORY' | 'SKILL' | 'META' | 'OTHER';

export interface FileInfo {
  path: string;
  role: FileRole;
  size_bytes: number;
  mtime: number;
  sha256: string;
  lint_warnings: number;
  last_lint_at?: number | null;
}

export interface FileContent {
  agent_id: string;
  path: string;
  role: FileRole;
  content: string;
  size_bytes: number;
  mtime: number;
  sha256: string;
}

export interface WriteResult {
  agent_id: string;
  path: string;
  size_bytes: number;
  mtime: number;
  sha256: string;
  backup_id?: number | null;
  lint_warnings: number;
}

export interface BackupEntry {
  backup_id: number;
  reason?: string | null;
  size_bytes: number;
  sha256: string;
  created_at: number;
}

export interface SearchHit {
  agent_id: string;
  file_path: string;
  line_number: number;
  line_content: string;
  context_before: string[];
  context_after: string[];
}

export interface SearchResult {
  hits: SearchHit[];
  total: number;
  duration_ms: number;
}

/** 对比归一化口径：默认忽略格式噪声，strict 仅忽略 BOM / 换行风格 / 零宽字符 */
export type DiffMode = 'ignore_whitespace' | 'strict';

export interface DiffResult {
  agent_a: string;
  agent_b: string;
  file: string;
  similarity: number;
  unified_diff: string;
  html_diff: string;
  /** 有效内容（归一化后）是否一致；为 true 时 unified_diff / html_diff 为空 */
  identical: boolean;
  /** 解释本次差异的格式噪声类型（空表示差异是真实业务差异） */
  noise_kinds: string[];
  /** 归一化口径：strict | ignore_whitespace */
  mode: string;
}

export interface SyncFilePlan {
  path: string;
  similarity: number;
  html_diff: string;
  size_src: number;
  size_dst: number;
  /** 有效内容是否一致（一致时不建议同步） */
  identical: boolean;
  noise_kinds: string[];
}

export interface SyncPlanResult {
  plan_id: string;
  src_agent: string;
  dst_agent: string;
  files: SyncFilePlan[];
}

export interface SyncResultItem {
  file: string;
  status: string;
  backup_id?: number | null;
}

export interface SyncExecuteResult {
  results: SyncResultItem[];
}

export interface LintWarning {
  rule_id: string;
  rule_name: string;
  severity: 'warning' | 'error';
  agent_id: string;
  file_path: string;
  line_number?: number | null;
  line_content?: string | null;
  suggestion: string;
}

export interface LintStats {
  files_checked: number;
  warnings: number;
  errors: number;
}

export interface LintAgentResult {
  agent_id: string;
  warnings: LintWarning[];
  stats: LintStats;
}

export interface LintAllResult {
  results: LintAgentResult[];
  agents: number;
}

export interface LintFileResult {
  agent_id: string;
  file_path: string;
  warnings: LintWarning[];
}

/** lint 规则目录项（文案事实源在后端 LintService，经 /api/lint/rules 下发） */
export interface LintRuleInfo {
  rule_id: string;
  rule_name: string;
  /** 作用域：file = 逐文件检查；agent = 需要 Agent 全貌（跨文件 / 跨 Agent） */
  scope: 'file' | 'agent';
  severity: 'warning' | 'error';
  /** 规则在检查什么 */
  description: string;
}

export interface LintRulesResult {
  rules: LintRuleInfo[];
  count: number;
}

export interface StatsResult {
  agents_total: number;
  files_total: number;
  core_files: number;
  memory_files: number;
  backup_total: number;
  backup_size_bytes: number;
  last_scan_at?: number | null;
  disk_usage_bytes: number;
}

export interface AuditEntry {
  id: number;
  timestamp: number;
  action: string;
  agent_id?: string | null;
  target_path?: string | null;
  details_json?: string | null;
  user: string;
  result: string;
}

export interface RollbackResult {
  file_path: string;
  rolled_back_to: number;
  new_backup_id: number;
  sha256: string;
}

export interface ScanResult {
  agents_scanned: number;
  files_indexed: number;
  duration_ms: number;
}

export interface CrossWriteItem {
  agent_id: string;
  path: string;
}

export interface CrossWriteResult {
  results: { agent_id: string; path: string; backup_id?: number | null }[];
  agents: number;
}

// ---- 配置中心（对应后端 /api/config，见 docs/API.md） ----
export interface ConfigSnapshot {
  server: { host: string; port: number };
  backup: { retention_days: number; auto_backup_on_write: boolean };
  lint: { enabled: boolean; strict_mode: boolean };
  ui: { default_theme: 'auto' | 'light' | 'dark'; default_view: 'tree' | 'list' };
  advanced: {
    show_skills: boolean;
    show_meta: boolean;
    show_memory: boolean;
    show_other: boolean;
  };
  openclaw: { dir: string };
}

// ---- Phase 2.5 · M11 文档预设 ----
export type PresetTargetType =
  | 'SOUL' | 'AGENTS' | 'MEMORY' | 'USER' | 'IDENTITY' | 'TOOLS' | 'WORKLOG' | 'ANY';

export interface PresetSection {
  title: string;
  required: boolean;
  order: number;
  hint?: string | null;
}

export interface FormatViolation {
  rule_id: string;
  rule_name: string;
  line?: number | null;
  message: string;
}

export interface FormatReport {
  ok: boolean;
  violations: FormatViolation[];
}

export interface PresetSummary {
  id: string;
  name: string;
  target_file_type: PresetTargetType;
  description?: string | null;
  is_system: boolean;
  /** 内置预设（随版本分发，下次升级可能被刷新）——展示「预设来源」用 */
  is_builtin: boolean;
  version: number;
  created_at: number;
  updated_at: number;
}

export interface Preset extends PresetSummary {
  template_md?: string | null;
  sections_json: PresetSection[];
  frontmatter_json: Record<string, string>;
  style_rules: string[];
}

export interface PresetApplyPlan {
  plan_id: string;
  agent_id: string;
  file_path: string;
  preset_id: string;
  current_snapshot: string;
  proposed_content: string;
  unified_diff: string;
  lint_warnings: LintWarning[];
  format_report: FormatReport;
}

export interface PresetApplyResult {
  backup_id?: number | null;
  applied_at: number;
  file_size: number;
}

export interface PresetVersionInfo {
  id: number;
  preset_id: string;
  version: number;
  created_at: number;
  user: string;
  name: string;
  target_file_type: PresetTargetType;
  description?: string | null;
  template_md?: string | null;
  sections_json: PresetSection[];
  frontmatter_json: Record<string, string>;
  style_rules: string[];
}

// ---- Phase 2.5 · M12 LLM Provider ----
export type LLMProtocol = 'openai-completions' | 'anthropic-messages';

export interface LLMProvider {
  id: string;
  base_url: string;
  api_key_masked: string;
  model: string;
  protocol: LLMProtocol;
  enabled: boolean;
  max_tokens: number;
  temperature: number;
  timeout_seconds: number;
  created_at: number;
  updated_at: number;
}

export interface LLMTestResult {
  ok: boolean;
  latency_ms: number;
  response_preview: string;
  error?: string | null;
}

export interface LLMResponseOut {
  content: string;
  usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number };
  cost_estimate_usd: number;
}

// ---- Phase 2.5 · M13 AI 自动整理 ----
export type AIJobStatus =
  | 'pending' | 'running' | 'awaiting_confirm' | 'applied' | 'rejected' | 'failed' | 'superseded';

export interface AIJobDiffPlan {
  unified_diff: string;
  lint_warnings: LintWarning[];
  format_report: FormatReport;
}

export interface AIJobSummary {
  id: string;
  agent_id: string;
  file_path: string;
  preset_id: string;
  provider_id: string;
  status: AIJobStatus;
  created_at: number;
  updated_at: number;
  finished_at?: number | null;
  superseded_by?: string | null;
}

export interface AIJob extends AIJobSummary {
  input_snapshot?: string | null;
  output_content?: string | null;
  diff_plan_json?: AIJobDiffPlan | null;
  extra_instructions?: string | null;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  total_tokens?: number | null;
  cost_estimate_usd?: number | null;
  error?: string | null;
}

export interface AIJobCreateResult {
  job_id: string;
  status: AIJobStatus;
  created_at: number;
}

export interface AIJobApplyResult {
  job_id: string;
  status: AIJobStatus;
  backup_id?: number | null;
  file_size: number;
}

// ---- Phase 2.6 · M15 工作日志标准化（批次） ----
export type DailyRunStatus =
  | 'planned'
  | 'awaiting_confirm'
  | 'applied'
  | 'partially_applied'
  | 'needs_review'
  | 'rejected'
  | 'failed'
  | 'empty';

export type DailyRunItemStatus =
  | 'pending'
  | 'planned'
  | 'failed'
  | 'blocked'
  | 'applied'
  | 'partially_applied'
  | 'skipped'
  /** 判定「本日无可归档内容」：不产出日文件，只清理 B/C 碎片（主文件不动） */
  | 'empty';

/** 来源分类：A = 当日主文件（YYYY-MM-DD.md）；B = 带时刻的会话导出；C = 主题命名碎片 */
export type DailySourceKind = 'A' | 'B' | 'C';

export interface DailySourceInfo {
  path: string;
  kind: DailySourceKind;
  raw_bytes: number;
  clean_bytes: number;
  /** 预处理阶段剥掉的低价值元数据行数 */
  removed_total: number;
  /** 是否经「分块摘要」压缩（超大来源） */
  summarized: boolean;
  chunks: number;
}

export interface DailyRunItem {
  date: string;
  /** 归并目标：恒为 memory/YYYY-MM-DD.md */
  target_path: string;
  /** 该日原本是否已有合规主文件 */
  has_standard: boolean;
  sources: DailySourceInfo[];
  /** 归并后拟删除的碎片（走系统回收站，可恢复） */
  fragments_to_delete: string[];
  output_content?: string | null;
  unified_diff?: string | null;
  html_diff?: string | null;
  format_report: FormatReport;
  lint_warnings: LintWarning[];
  notes: string[];
  /** 非空 = 模型判定「本日无可归档内容」（值为一句话理由）：不产出日文件，只清理碎片 */
  empty_reason?: string | null;
  decision: 'pending' | 'applied' | 'skipped';
  status: DailyRunItemStatus;
  error?: string | null;
  backup_id?: number | null;
  applied_at?: number | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_estimate_usd: number;
}

export interface DailyRunSummary {
  id: string;
  agent_id: string;
  date_from: string;
  date_to: string;
  preset_id: string;
  preset_version: number;
  provider_id: string;
  status: DailyRunStatus;
  days_total: number;
  token_budget: number;
  tokens_used: number;
  cost_estimate_usd: number;
  error?: string | null;
  created_at: number;
  updated_at: number;
  finished_at?: number | null;
}

export interface DailyRun extends DailyRunSummary {
  extra_instructions?: string | null;
  items: DailyRunItem[];
}

export interface DailyRunCreateResult {
  run_id: string;
  status: DailyRunStatus;
  days_total: number;
  /** 命中幂等键 → 复用既有批次，未产生新的 LLM 调用 */
  reused: boolean;
  created_at: number;
}

export interface DailyRunApplyResult {
  run_id: string;
  status: DailyRunStatus;
  applied: string[];
  /** 日文件已写、碎片删失败 */
  partial: string[];
  /** 写前验收不过，未写入 */
  blocked: string[];
  failed: string[];
  /** 判定无可归档内容：未产出日文件，仅清理碎片 */
  no_content: string[];
  skipped: string[];
}

export interface DailyRunReportItem {
  date: string;
  target_path: string;
  status: DailyRunItemStatus;
  /** 该日判定「无可归档内容」：不产出日文件，只核对碎片是否已清 */
  empty: boolean;
  /** 该日是否已交付（applied / partially_applied） */
  delivered: boolean;
  single_file: boolean;
  naming_ok: boolean;
  sections_ok: boolean;
  no_residue: boolean;
  fragments_gone: boolean;
  details: string[];
}

export interface DailyRunReport {
  run_id: string;
  agent_id: string;
  status: DailyRunStatus;
  passed: boolean;
  items: DailyRunReportItem[];
  days_delivered: number;
  days_total: number;
  tokens_used: number;
  cost_estimate_usd: number;
  generated_at: number;
}

// ---- 超级同步（独立守护脚本） ----
export type SuperSyncState = 'running' | 'stopped' | 'error';
export type SuperSyncLogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR';

export interface SuperSyncConfig {
  /** 轮询间隔（秒），越小越实时 */
  interval_seconds: number;
  /** 日志留存天数（后端保证 ≥ 30） */
  retention_days: number;
  /** 参与同步的 Agent id 列表 */
  agents: string[];
  /** 每个 Agent 纳入同步范围的文件（相对 workspace 路径） */
  files: Record<string, string[]>;
}

export interface SuperSyncStatus {
  state: SuperSyncState;
  pid?: number | null;
  pid_alive: boolean;
  source?: string | null;
  started_at?: string | null;
  last_heartbeat?: string | null;
  heartbeat_age_seconds?: number | null;
  interval_seconds: number;
  agents: string[];
  synced_total: number;
  ticks: number;
  last_sync_at?: string | null;
  last_duration_ms?: number | null;
  last_error?: string | null;
}

export interface SuperSyncLogEntry {
  ts: string;
  ts_unix: number;
  level: SuperSyncLogLevel;
  event: string;
  message?: string;
  path?: string | null;
  source_agent?: string | null;
  target_agent?: string | null;
  result?: string | null;
  size_bytes?: number | null;
  sha256?: string | null;
  diff?: string | null;
  error?: string | null;
}

export interface SuperSyncLogResult {
  items: SuperSyncLogEntry[];
  total: number;
  limit: number;
  offset: number;
  retention_days: number;
}
