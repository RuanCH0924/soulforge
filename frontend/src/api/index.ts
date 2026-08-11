/** 全部后端 API 的封装（见 docs/API.md） */
import { downloadFile, encodePath, request } from './client';
import type {
  AgentInfo,
  AuditEntry,
  BackupEntry,
  ConfigSnapshot,
  CrossWriteItem,
  CrossWriteResult,
  DiffResult,
  FileContent,
  FileInfo,
  ImportExecuteResult,
  ImportPreviewResult,
  ImportStrategy,
  LintAgentResult,
  LintAllResult,
  LintFileResult,
  RollbackResult,
  ScanResult,
  SearchResult,
  StatsResult,
  SyncExecuteResult,
  SyncPlanResult,
  TemplateApplyResult,
  TemplateInfo,
  WriteResult,
} from '../types';

export const api = {
  // ---- M1 Agent ----
  listAgents: () => request<AgentInfo[]>('GET', '/api/agents'),
  scanAgents: () => request<ScanResult>('POST', '/api/agents/scan'),

  // ---- M2 文件 ----
  listFiles: (agentId: string) =>
    request<FileInfo[]>('GET', `/api/agents/${encodeURIComponent(agentId)}/files`),
  readFile: (agentId: string, path: string) =>
    request<FileContent>('GET', `/api/agents/${encodeURIComponent(agentId)}/files/${encodePath(path)}`),
  writeFile: (agentId: string, path: string, content: string, expectedSha256?: string) =>
    request<WriteResult>('PUT', `/api/agents/${encodeURIComponent(agentId)}/files/${encodePath(path)}`, {
      json: { content, expected_sha256: expectedSha256 ?? null },
    }),
  fileHistory: (agentId: string, path: string) =>
    request<BackupEntry[]>('GET', `/api/agents/${encodeURIComponent(agentId)}/files/${encodePath(path)}/history`),
  crossWrite: (files: CrossWriteItem[], content: string) =>
    request<CrossWriteResult>('POST', '/api/agents/files/cross-write', { json: { files, content } }),

  // ---- M3 搜索 ----
  search: (body: {
    query: string;
    agent_ids?: string[];
    file_patterns?: string[];
    regex?: boolean;
    case_sensitive?: boolean;
    context_lines?: number;
    limit?: number;
  }) => request<SearchResult>('POST', '/api/search', { json: body }),

  // ---- M4 Diff ----
  diff: (a: string, b: string, file: string) =>
    request<DiffResult>(
      'GET',
      `/api/diff?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}&file=${encodeURIComponent(file)}`,
    ),

  // ---- M5 同步 ----
  syncPlan: (srcAgent: string, dstAgent: string, files: string[]) =>
    request<SyncPlanResult>('POST', '/api/sync/plan', { json: { src_agent: srcAgent, dst_agent: dstAgent, files } }),
  syncExecute: (planId: string, files: string[]) =>
    request<SyncExecuteResult>('POST', '/api/sync/execute', { json: { plan_id: planId, files } }),

  // ---- M6 导入导出 ----
  exportAgent: (agentId: string) =>
    downloadFile(`/api/export/${encodeURIComponent(agentId)}`, `soulforge-${agentId}.tar.gz`),
  exportAll: () => downloadFile('/api/export/all', 'soulforge-all.tar.gz'),
  importPreview: (file: File, targetAgentId: string) => {
    const form = new FormData();
    form.append('file', file);
    form.append('target_agent_id', targetAgentId);
    return request<ImportPreviewResult>('POST', '/api/import/preview', { form });
  },
  importExecute: (uploadId: string, targetAgentId: string, conflicts: Record<string, ImportStrategy>) =>
    request<ImportExecuteResult>('POST', '/api/import/execute', {
      json: { upload_id: uploadId, target_agent_id: targetAgentId, conflicts },
    }),

  // ---- M7 备份回滚 ----
  rollback: (agentId: string, path: string, backupId: number) =>
    request<RollbackResult>(
      'POST',
      `/api/backups/${encodeURIComponent(agentId)}/${encodePath(path)}/rollback`,
      { json: { backup_id: backupId } },
    ),

  // ---- M8 Lint ----
  lintFile: (agentId: string, path: string) =>
    request<LintFileResult>('GET', `/api/lint/file/${encodeURIComponent(agentId)}/${encodePath(path)}`),
  lintAgent: (agentId: string) =>
    request<LintAgentResult>('GET', `/api/lint/${encodeURIComponent(agentId)}`),
  lintAll: () => request<LintAllResult>('GET', '/api/lint/all'),

  // ---- M9 模板 ----
  listTemplates: () => request<TemplateInfo[]>('GET', '/api/templates'),
  applyTemplate: (templateId: string, newAgentId: string, targetWorkspace: string) =>
    request<TemplateApplyResult>('POST', '/api/templates/apply', {
      json: { template_id: templateId, new_agent_id: newAgentId, target_workspace: targetWorkspace },
    }),

  // ---- M10 统计 / 审计 ----
  stats: () => request<StatsResult>('GET', '/api/stats'),
  audit: (limit = 100) => request<AuditEntry[]>('GET', `/api/audit?limit=${limit}`),

  // ---- 配置中心（config.toml 可视化） ----
  getConfig: () => request<ConfigSnapshot>('GET', '/api/config'),
  updateConfig: (patch: Record<string, Record<string, unknown>>) =>
    request<ConfigSnapshot>('PUT', '/api/config', { json: patch }),
};
