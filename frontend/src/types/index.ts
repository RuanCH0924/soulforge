/** Soulforge 前端类型定义（与后端 Pydantic schema 一一对应，见 docs/API.md） */

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

export interface DiffResult {
  agent_a: string;
  agent_b: string;
  file: string;
  similarity: number;
  unified_diff: string;
  html_diff: string;
}

export interface SyncFilePlan {
  path: string;
  similarity: number;
  html_diff: string;
  size_src: number;
  size_dst: number;
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

export interface ManifestFile {
  path: string;
  size: number;
  sha256: string;
}

export interface Manifest {
  soulforge_version: string;
  export_time: string;
  agent_id: string;
  files: ManifestFile[];
}

export interface ConflictItem {
  path: string;
  exists_in_target: boolean;
  target_size?: number | null;
}

export interface ImportPreviewResult {
  upload_id: string;
  target_agent_id: string;
  manifest: Manifest;
  conflicts: ConflictItem[];
}

export type ImportStrategy = 'skip' | 'merge' | 'overwrite';

export interface ImportExecuteResult {
  manifest: Manifest;
  results: { file: string; action: string }[];
}

export interface TemplateInfo {
  id: string;
  name: string;
  description: string;
  file_count: number;
}

export interface TemplateApplyResult {
  agent_id: string;
  workspace: string;
  files_created: string[];
}

export interface StatsResult {
  agents_total: number;
  files_total: number;
  core_files: number;
  memory_files: number;
  backup_total: number;
  backup_size_bytes: number;
  lint_warnings_total: number;
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
