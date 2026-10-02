import { useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import { useLintScan } from '../hooks/useLintScan';
import { Modal } from './Modal';
import type { LintRuleInfo, LintWarning } from '../types';

interface GlobalLintModalProps {
  onClose: () => void;
  onOpenResult: (agentId: string, path: string, line?: number) => void;
  /** 页面内嵌模式（P2 页面化） */
  embedded?: boolean;
}

export function GlobalLintModal({ onClose, onOpenResult, embedded }: GlobalLintModalProps) {
  // 全量扫描由共享的 LintScanProvider 持有：本弹窗只触发 / 展示进度 / 取消，不自己发全量请求
  const lint = useLintScan();
  const { start: startLintScan, cancel: cancelLintScan } = lint;
  const [rules, setRules] = useState<LintRuleInfo[]>([]);
  // null = 未手动干预：无警告时自动展开（「什么都没查到」时最需要知道查了什么）
  const [rulesOpen, setRulesOpen] = useState<boolean | null>(null);

  const warnings: LintWarning[] = useMemo(
    () => lint.results.flatMap((r) => r.warnings),
    [lint.results],
  );
  const checkedFiles = lint.checkedFiles;
  const running = lint.status === 'running' || lint.status === 'idle';
  const showRules = rulesOpen ?? (warnings.length === 0);

  /** 规则文案由后端下发，前端不写死 */
  async function loadRules() {
    try {
      setRules((await api.lintRules()).rules);
    } catch {
      // 规则清单拉取失败不影响检查结果展示
      setRules([]);
    }
  }

  useEffect(() => {
    // 单飞：若已有一轮扫描在跑，直接复用其进度（不会重复全量扫描）
    void startLintScan();
    void loadRules();
  }, [startLintScan]);

  return (
    <Modal
      title="全局健康检查"
      onClose={onClose}
      width={820}
      embedded={embedded}
      headerless={embedded}
      footer={
        running ? (
          <button className="btn" onClick={cancelLintScan} disabled={lint.status !== 'running'}>
            取消检查
          </button>
        ) : (
          <button className="btn" onClick={() => void startLintScan()}>
            重新检查
          </button>
        )
      }
    >
      {rules.length > 0 && (
        <div className="lint-rules">
          <button
            type="button"
            className="lint-rules-head"
            aria-expanded={showRules}
            onClick={() => setRulesOpen(!showRules)}
          >
            <span className="lint-rules-caret">{showRules ? '▾' : '▸'}</span>
            <span>检查规则（{rules.length} 条）</span>
            <span className="muted" style={{ marginLeft: 'auto', fontWeight: 400 }}>
              {showRules ? '收起' : '展开'}
            </span>
          </button>
          {showRules && (
            <div className="lint-rules-body">
              <table>
                <thead>
                  <tr>
                    <th style={{ width: 190 }}>规则</th>
                    <th style={{ width: 56 }}>级别</th>
                    <th style={{ width: 72 }}>作用域</th>
                    <th>检查内容</th>
                  </tr>
                </thead>
                <tbody>
                  {rules.map((r) => (
                    <tr key={r.rule_id}>
                      <td>
                        <div>{r.rule_name}</div>
                        <div className="mono muted text-xs">{r.rule_id}</div>
                      </td>
                      <td style={{ color: r.severity === 'error' ? 'var(--danger)' : 'var(--warning)' }}>
                        {r.severity === 'error' ? '错误' : '警告'}
                      </td>
                      <td className="muted">{r.scope === 'agent' ? '整个 Agent' : '单个文件'}</td>
                      <td>{r.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="hint mt-8">
                默认只警告、不改动文件；打开「严格模式」（系统配置 → 常规设置）后违规会阻止保存。
              </div>
            </div>
          )}
        </div>
      )}

      {running ? (
        <div className="state-block">
          <div className="spinner-lg" />
          <div>
            正在检查所有 Agent{lint.total > 0 ? `（${lint.done}/${lint.total}）` : ''}
            {lint.currentAgent ? `，当前：${lint.currentAgent}` : ''}…
          </div>
          {lint.status === 'running' && (
            <button className="btn btn-sm mt-8" onClick={cancelLintScan}>
              取消
            </button>
          )}
        </div>
      ) : lint.status === 'error' ? (
        <div className="state-block">
          <div className="lint-empty">健康检查失败：{lint.error ?? '未知错误'}</div>
        </div>
      ) : warnings.length === 0 ? (
        <div className="state-block">
          {lint.status === 'cancelled' ? (
            <div className="lint-empty">检查已取消，已完成 {lint.done}/{lint.total} 个 Agent</div>
          ) : (
            <div className="lint-empty">✓ 检查了 {checkedFiles} 个文件，没有发现 lint 警告</div>
          )}
        </div>
      ) : (
        <>
          <div className="alert-banner warning">
            {lint.status === 'cancelled' ? '检查已取消（结果不完整）。' : ''}
            共发现 {warnings.length} 条 lint 警告（检查 {checkedFiles} 个文件）。点击警告可跳转到对应文件。
          </div>
          <div className="item-list">
            {warnings.map((w, i) => (
              <div
                key={`${w.agent_id}-${w.file_path}-${w.rule_id}-${i}`}
                className="item"
                onClick={() => onOpenResult(w.agent_id, w.file_path, w.line_number ?? undefined)}
              >
                <div className="item-title">
                  <span className="badge-warn" style={{ background: 'var(--accent)' }}>
                    {w.agent_id}
                  </span>
                  <span className="mono" title={w.file_path}>{w.file_path}</span>
                  {w.line_number != null && <span className="muted">第 {w.line_number} 行</span>}
                  <span className="muted" style={{ marginLeft: 'auto', fontWeight: 600, color: 'var(--danger)' }}>
                    {w.rule_name}
                  </span>
                </div>
                {w.line_content && (
                  <div className="item-sub" style={{ fontFamily: 'var(--font-mono)' }}>
                    {w.line_content}
                  </div>
                )}
                <div className="item-sub" style={{ color: 'var(--warning)', fontFamily: 'var(--font-main)' }}>
                  建议：{w.suggestion}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </Modal>
  );
}
