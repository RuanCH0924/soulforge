/** 全部后端 API 的封装（见 docs/API.md） */
import { downloadFile, encodePath, request } from './client';
import type {
  AIJob,
  AIJobApplyResult,
  AIJobCreateResult,
  AIJobStatus,
  AIJobSummary,
  AgentInfo,
  DiffMode,
  AuditEntry,
  BackupEntry,
  ConfigSnapshot,
  CrossWriteItem,
  CrossWriteResult,
  DiffResult,
  FileContent,
  FileInfo,
  LintAgentResult,
  LintAllResult,
  LintFileResult,
  LLMProtocol,
  LLMProvider,
  LLMResponseOut,
  LLMTestResult,
  Preset,
  PresetApplyPlan,
  PresetApplyResult,
  PresetSummary,
  PresetTargetType,
  PresetVersionInfo,
  RollbackResult,
  ScanResult,
  SearchResult,
  StatsResult,
  SuperSyncConfig,
  SuperSyncLogResult,
  SuperSyncStatus,
  SyncExecuteResult,
  SyncPlanResult,
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
  /** 删除文档（后端走回收站，可恢复） */
  deleteFile: (agentId: string, path: string) =>
    request<{ agent_id: string; path: string; deleted: boolean }>(
      'DELETE',
      `/api/agents/${encodeURIComponent(agentId)}/files/${encodePath(path)}`,
    ),
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
  /** 对比两个 Agent 的同名文件；mode 为归一化口径（默认忽略格式噪声） */
  diff: (a: string, b: string, file: string, mode?: DiffMode) =>
    request<DiffResult>(
      'GET',
      `/api/diff?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}&file=${encodeURIComponent(file)}` +
        (mode ? `&mode=${encodeURIComponent(mode)}` : ''),
    ),
  /** 对比「当前文件」与指定历史备份（回滚前预览用） */
  diffHistory: (agentId: string, file: string, against: number, mode?: DiffMode) =>
    request<DiffResult>(
      'GET',
      `/api/diff/history?agent=${encodeURIComponent(agentId)}&file=${encodeURIComponent(file)}&against=${against}` +
        (mode ? `&mode=${encodeURIComponent(mode)}` : ''),
    ),

  // ---- M5 同步 ----
  syncPlan: (srcAgent: string, dstAgent: string, files: string[]) =>
    request<SyncPlanResult>('POST', '/api/sync/plan', { json: { src_agent: srcAgent, dst_agent: dstAgent, files } }),
  syncExecute: (planId: string, files: string[]) =>
    request<SyncExecuteResult>('POST', '/api/sync/execute', { json: { plan_id: planId, files } }),

  // ---- M6 导出 ----
  exportAgent: (agentId: string) =>
    downloadFile(`/api/export/${encodeURIComponent(agentId)}`, `soulforge-${agentId}.tar.gz`),
  exportAll: () => downloadFile('/api/export/all', 'soulforge-all.tar.gz'),

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

  // ---- M10 统计 / 审计 ----
  stats: () => request<StatsResult>('GET', '/api/stats'),
  audit: (limit = 100) => request<AuditEntry[]>('GET', `/api/audit?limit=${limit}`),

  // ---- 配置中心（config.toml 可视化） ----
  getConfig: () => request<ConfigSnapshot>('GET', '/api/config'),
  updateConfig: (patch: Record<string, Record<string, unknown>>) =>
    request<ConfigSnapshot>('PUT', '/api/config', { json: patch }),

  // ---- M11 文档预设（Phase 2.5） ----
  listPresets: (targetFileType?: PresetTargetType) =>
    request<PresetSummary[]>(
      'GET',
      targetFileType ? `/api/presets?target_file_type=${encodeURIComponent(targetFileType)}` : '/api/presets',
    ),
  getPreset: (id: string) => request<Preset>('GET', `/api/presets/${encodeURIComponent(id)}`),
  createPreset: (body: {
    name: string;
    target_file_type: PresetTargetType;
    description?: string;
    template_md?: string;
    sections_json?: Preset['sections_json'];
    frontmatter_json?: Preset['frontmatter_json'];
    style_rules?: string[];
  }) => request<Preset>('POST', '/api/presets', { json: body }),
  updatePreset: (id: string, body: Record<string, unknown>) =>
    request<Preset>('PUT', `/api/presets/${encodeURIComponent(id)}`, { json: body }),
  deletePreset: (id: string) =>
    request<{ id: string; deleted: boolean }>('DELETE', `/api/presets/${encodeURIComponent(id)}`),
  presetApplyPlan: (presetId: string, agentId: string, filePath: string, extraInstructions?: string) =>
    request<PresetApplyPlan>('POST', `/api/presets/${encodeURIComponent(presetId)}/apply`, {
      json: { agent_id: agentId, file_path: filePath, extra_instructions: extraInstructions ?? null },
    }),
  presetApplyExecute: (presetId: string, planId: string, agentId: string, filePath: string) =>
    request<PresetApplyResult>('POST', `/api/presets/${encodeURIComponent(presetId)}/apply/execute`, {
      json: { plan_id: planId, agent_id: agentId, file_path: filePath },
    }),
  listPresetVersions: (presetId: string) =>
    request<PresetVersionInfo[]>('GET', `/api/presets/${encodeURIComponent(presetId)}/versions`),
  restorePresetVersion: (presetId: string, versionId: number) =>
    request<Preset>('POST', `/api/presets/${encodeURIComponent(presetId)}/versions/${versionId}/restore`),

  // ---- M12 LLM Provider（Phase 2.5） ----
  listLLMProviders: () => request<LLMProvider[]>('GET', '/api/llm/providers'),
  createLLMProvider: (body: {
    id: string;
    base_url: string;
    api_key: string;
    model: string;
    protocol: LLMProtocol;
    enabled?: boolean;
    max_tokens?: number;
    temperature?: number;
    timeout_seconds?: number;
  }) => request<LLMProvider>('POST', '/api/llm/providers', { json: body }),
  updateLLMProvider: (id: string, body: Record<string, unknown>) =>
    request<LLMProvider>('PUT', `/api/llm/providers/${encodeURIComponent(id)}`, { json: body }),
  deleteLLMProvider: (id: string) =>
    request<{ id: string; deleted: boolean }>('DELETE', `/api/llm/providers/${encodeURIComponent(id)}`),
  testLLMProvider: (id: string) =>
    request<LLMTestResult>('POST', `/api/llm/providers/${encodeURIComponent(id)}/test`),
  llmChat: (providerId: string, messages: { role: string; content: string }[], maxTokens?: number, temperature?: number) =>
    request<LLMResponseOut>('POST', '/api/llm/chat', {
      json: {
        provider_id: providerId,
        messages,
        max_tokens: maxTokens ?? null,
        temperature: temperature ?? null,
      },
    }),

  // ---- M13 AI 自动整理（Phase 2.5） ----
  createAIJob: (body: {
    agent_id: string;
    file_path: string;
    preset_id: string;
    provider_id: string;
    extra_instructions?: string;
  }) => request<AIJobCreateResult>('POST', '/api/ai/jobs', { json: body }),
  getAIJob: (jobId: string) => request<AIJob>('GET', `/api/ai/jobs/${encodeURIComponent(jobId)}`),
  listAIJobs: (params?: { agent_id?: string; status?: AIJobStatus; limit?: number }) =>
    request<AIJobSummary[]>(
      'GET',
      `/api/ai/jobs?${new URLSearchParams(
        Object.fromEntries(Object.entries(params ?? {}).map(([k, v]) => [k, String(v)])) as Record<string, string>,
      )}`,
    ),
  applyAIJob: (jobId: string) =>
    request<AIJobApplyResult>('POST', `/api/ai/jobs/${encodeURIComponent(jobId)}/apply`),
  rejectAIJob: (jobId: string) =>
    request<AIJob>('POST', `/api/ai/jobs/${encodeURIComponent(jobId)}/reject`),
  regenerateAIJob: (jobId: string, extraInstructions: string) =>
    request<AIJobCreateResult>('POST', `/api/ai/jobs/${encodeURIComponent(jobId)}/regenerate`, {
      json: { extra_instructions: extraInstructions },
    }),

  // ---- 超级同步（独立守护脚本） ----
  superSyncConfig: () => request<SuperSyncConfig>('GET', '/api/super-sync/config'),
  updateSuperSyncConfig: (body: Partial<SuperSyncConfig>) =>
    request<SuperSyncConfig>('PUT', '/api/super-sync/config', { json: body }),
  superSyncStatus: () => request<SuperSyncStatus>('GET', '/api/super-sync/status'),
  startSuperSync: () => request<SuperSyncStatus>('POST', '/api/super-sync/start'),
  stopSuperSync: () => request<SuperSyncStatus>('POST', '/api/super-sync/stop'),
  superSyncLogs: (params?: {
    levels?: string;
    since?: number;
    until?: number;
    limit?: number;
    offset?: number;
  }) => {
    const q = new URLSearchParams();
    if (params?.levels) q.set('levels', params.levels);
    if (params?.since !== undefined) q.set('since', String(params.since));
    if (params?.until !== undefined) q.set('until', String(params.until));
    if (params?.limit !== undefined) q.set('limit', String(params.limit));
    if (params?.offset !== undefined) q.set('offset', String(params.offset));
    return request<SuperSyncLogResult>('GET', `/api/super-sync/logs?${q.toString()}`);
  },
  exportSuperSyncLogs: (params?: { levels?: string; since?: number; until?: number }) => {
    const q = new URLSearchParams();
    if (params?.levels) q.set('levels', params.levels);
    if (params?.since !== undefined) q.set('since', String(params.since));
    if (params?.until !== undefined) q.set('until', String(params.until));
    return downloadFile(`/api/super-sync/logs/export?${q.toString()}`, 'super-sync-logs.jsonl');
  },
};
