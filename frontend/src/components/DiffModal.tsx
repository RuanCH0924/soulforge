import { useEffect, useState } from 'react';
import { api } from '../api';
import { isRoleVisible, useSettings } from '../hooks/useSettings';
import { useToast } from '../hooks/useToast';
import { DiffView } from './DiffView';
import { Modal } from './Modal';
import type { AgentInfo, DiffMode, DiffResult, FileInfo } from '../types';
import { similarityColor, similarityPercent } from '../utils/format';

interface DiffModalProps {
  agents: AgentInfo[];
  initialAgent: string | null;
  onClose: () => void;
  /** 页面内嵌模式（P3 页面化） */
  embedded?: boolean;
}

export function DiffModal({ agents, initialAgent, onClose, embedded }: DiffModalProps) {
  const { push: toast } = useToast();
  const { settings } = useSettings();
  // 默认 A/B 必须是两个不同 Agent（此前 initialAgent 为 null 会导致 B 与 A 相同，
  // 变成「自己和自己比」，用户必须手动改一次才能开始对比）
  const defaultA = initialAgent ?? agents[0]?.id ?? '';
  const [agentA, setAgentA] = useState<string>(defaultA);
  const [agentB, setAgentB] = useState<string>(() => agents.find((a) => a.id !== defaultA)?.id ?? '');
  const [filesA, setFilesA] = useState<FileInfo[]>([]);
  const [filesB, setFilesB] = useState<FileInfo[]>([]);
  const [file, setFile] = useState('');
  const [diff, setDiff] = useState<DiffResult | null>(null);
  const [mode, setMode] = useState<DiffMode>('ignore_whitespace');
  const [loading, setLoading] = useState(false);
  const [loadingFiles, setLoadingFiles] = useState(false);

  // 当 A/B 相同（例如用户把 A 改成原来的 B）时自动纠正 B，避免自比较
  useEffect(() => {
    if (agents.length < 2) return;
    if (agentA && agentA === agentB) {
      setAgentB(agents.find((a) => a.id !== agentA)?.id ?? '');
      setDiff(null);
    }
  }, [agents, agentA, agentB]);

  useEffect(() => {
    if (!agentA) return;
    let cancelled = false;
    setLoadingFiles(true);
    api
      .listFiles(agentA)
      .then((fs) => {
        if (!cancelled) setFilesA(fs.filter((f) => isRoleVisible(f.role, settings)));
      })
      .catch((e) => {
        if (!cancelled) toast(`加载 ${agentA} 文件失败：${(e as Error).message}`, 'error');
      })
      .finally(() => {
        if (!cancelled) setLoadingFiles(false);
      });
    return () => {
      cancelled = true;
    };
  }, [agentA, settings, toast]);

  useEffect(() => {
    if (!agentB) return;
    let cancelled = false;
    setLoadingFiles(true);
    api
      .listFiles(agentB)
      .then((fs) => {
        if (!cancelled) setFilesB(fs.filter((f) => isRoleVisible(f.role, settings)));
      })
      .catch((e) => {
        if (!cancelled) toast(`加载 ${agentB} 文件失败：${(e as Error).message}`, 'error');
      })
      .finally(() => {
        if (!cancelled) setLoadingFiles(false);
      });
    return () => {
      cancelled = true;
    };
  }, [agentB, settings, toast]);

  // 共同存在的文件
  const commonFiles = filesA
    .map((f) => f.path)
    .filter((p) => filesB.some((f) => f.path === p))
    .sort((x, y) => x.localeCompare(y));

  // 切换 Agent 后自动选择第一个共同文件
  useEffect(() => {
    if (commonFiles.length > 0 && !commonFiles.includes(file)) {
      setFile(commonFiles[0]);
      setDiff(null);
    }
  }, [commonFiles, file]);

  async function runDiff(nextMode: DiffMode = mode) {
    if (!agentA || !agentB || !file) return;
    setLoading(true);
    try {
      const res = await api.diff(agentA, agentB, file, nextMode);
      setDiff(res);
    } catch (e) {
      toast(`对比失败：${(e as Error).message}`, 'error');
    } finally {
      setLoading(false);
    }
  }

  /** 切换归一化口径：若已有结果则立即按新口径重算，避免结果与开关不一致 */
  function changeMode(next: DiffMode) {
    setMode(next);
    if (diff) void runDiff(next);
  }

  const agentOptions = (excludeId: string) => agents.filter((a) => a.id !== excludeId);

  return (
    <Modal
      title="文件对比"
      onClose={onClose}
      width={860}
      embedded={embedded}
      headerless={embedded}
      footer={
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', width: '100%' }}>
          <span className="mode-toggle" role="group" aria-label="对比口径">
            <button
              type="button"
              className={mode === 'ignore_whitespace' ? 'active' : ''}
              onClick={() => changeMode('ignore_whitespace')}
              title="忽略空白、空行、缩进、BOM、零宽字符等格式噪声（默认）"
            >
              忽略格式噪声
            </button>
            <button
              type="button"
              className={mode === 'strict' ? 'active' : ''}
              onClick={() => changeMode('strict')}
              title="仅忽略 BOM / 换行符风格 / 零宽字符；空白与空行差异仍算差异"
            >
              严格
            </button>
          </span>
          <button
            className="btn btn-primary"
            onClick={() => void runDiff()}
            disabled={!agentA || !agentB || !file || loading}
            style={{ marginLeft: 'auto' }}
          >
            {loading && <span className="spinner" />}
            开始对比
          </button>
        </div>
      }
    >
      <div style={{ display: 'flex', gap: 12, marginBottom: 14, alignItems: 'flex-end' }}>
        <div className="field" style={{ flex: 1, marginBottom: 0 }}>
          <label>Agent A</label>
          <select
            className="select"
            value={agentA}
            onChange={(e) => {
              setAgentA(e.target.value);
              setDiff(null);
            }}
          >
            {agents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.display_name || a.id}
              </option>
            ))}
          </select>
        </div>
        <div className="field" style={{ flex: 1, marginBottom: 0 }}>
          <label>Agent B</label>
          <select
            className="select"
            value={agentB}
            onChange={(e) => {
              setAgentB(e.target.value);
              setDiff(null);
            }}
          >
            {agentOptions(agentA).map((a) => (
              <option key={a.id} value={a.id}>
                {a.display_name || a.id}
              </option>
            ))}
          </select>
        </div>
        <div className="field" style={{ flex: 2, marginBottom: 0 }}>
          <label>文件（两个 Agent 共有的）</label>
          <select
            className="select"
            value={file}
            onChange={(e) => {
              setFile(e.target.value);
              setDiff(null);
            }}
            disabled={loadingFiles}
          >
            {commonFiles.length === 0 ? (
              <option value="">没有共有的文件</option>
            ) : (
              commonFiles.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))
            )}
          </select>
        </div>
      </div>

      {diff && (
        <>
          <div className={`similarity-bar ${similarityColor(diff.similarity)}`}>
            <span>
              {diff.agent_a} vs {diff.agent_b}
            </span>
            <div className="similarity-track">
              <div className="similarity-fill" style={{ width: similarityPercent(diff.similarity) }} />
            </div>
            <span>{similarityPercent(diff.similarity)}</span>
          </div>
          <DiffView
            htmlDiff={diff.html_diff}
            identical={diff.identical}
            noiseKinds={diff.noise_kinds}
          />
        </>
      )}
    </Modal>
  );
}
