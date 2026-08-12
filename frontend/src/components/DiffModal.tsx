import { useEffect, useState } from 'react';
import { api } from '../api';
import { isRoleVisible, useSettings } from '../hooks/useSettings';
import { useToast } from '../hooks/useToast';
import { Modal } from './Modal';
import type { AgentInfo, DiffResult, FileInfo } from '../types';
import { similarityColor, similarityPercent } from '../utils/format';

interface DiffModalProps {
  agents: AgentInfo[];
  initialAgent: string | null;
  onClose: () => void;
}

export function DiffModal({ agents, initialAgent, onClose }: DiffModalProps) {
  const { push: toast } = useToast();
  const { settings } = useSettings();
  const [agentA, setAgentA] = useState<string>(initialAgent ?? agents[0]?.id ?? '');
  const [agentB, setAgentB] = useState<string>(() => {
    const first = agents.find((a) => a.id !== initialAgent);
    return first?.id ?? agents[0]?.id ?? '';
  });
  const [filesA, setFilesA] = useState<FileInfo[]>([]);
  const [filesB, setFilesB] = useState<FileInfo[]>([]);
  const [file, setFile] = useState('');
  const [diff, setDiff] = useState<DiffResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingFiles, setLoadingFiles] = useState(false);

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

  async function runDiff() {
    if (!agentA || !agentB || !file) return;
    setLoading(true);
    try {
      const res = await api.diff(agentA, agentB, file);
      setDiff(res);
    } catch (e) {
      toast(`对比失败：${(e as Error).message}`, 'error');
    } finally {
      setLoading(false);
    }
  }

  const agentOptions = (excludeId: string) =>
    agents.filter((a) => a.id !== excludeId);

  return (
    <Modal
      title="文件对比"
      onClose={onClose}
      width={860}
      footer={
        <button className="btn btn-primary" onClick={runDiff} disabled={!agentA || !agentB || !file || loading}>
          {loading && <span className="spinner" />}
          开始对比
        </button>
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
          <div dangerouslySetInnerHTML={{ __html: diff.html_diff }} />
        </>
      )}
    </Modal>
  );
}
