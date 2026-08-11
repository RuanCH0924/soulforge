import { useEffect, useState } from 'react';
import { api } from '../api';
import { useSettings } from '../hooks/useSettings';
import type { ThemeMode } from '../hooks/useSettings';
import { useToast } from '../hooks/useToast';
import type { ConfigSnapshot } from '../types';
import { Modal } from './Modal';

interface SettingsModalProps {
  onClose: () => void;
}

const THEME_OPTIONS: { value: ThemeMode; label: string }[] = [
  { value: 'auto', label: '跟随系统' },
  { value: 'light', label: '浅色' },
  { value: 'dark', label: '深色' },
];

/** 设置弹窗 = 本地界面偏好（localStorage）+ 配置中心（config.toml 服务端读写） */
export function SettingsModal({ onClose }: SettingsModalProps) {
  const { settings, set } = useSettings();
  const { push } = useToast();

  const [cfg, setCfg] = useState<ConfigSnapshot | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .getConfig()
      .then((c) => {
        setCfg(c);
        setLoadError(null);
      })
      .catch((e) => setLoadError(e instanceof Error ? e.message : '读取配置失败'));
  }, []);

  const patchCfg = (section: keyof ConfigSnapshot, key: string, value: unknown) => {
    setCfg((prev) => {
      if (!prev) return prev;
      const cur = prev[section] as Record<string, unknown>;
      return { ...prev, [section]: { ...cur, [key]: value } };
    });
  };

  const save = async () => {
    if (!cfg) return;
    setSaving(true);
    try {
      // 主题 / showSkills / showMeta 本地即时生效，保存时同步到服务端 config.toml
      await api.updateConfig({
        backup: {
          retention_days: cfg.backup.retention_days,
          auto_backup_on_write: cfg.backup.auto_backup_on_write,
        },
        lint: { enabled: cfg.lint.enabled, strict_mode: cfg.lint.strict_mode },
        ui: { default_theme: settings.theme, default_view: cfg.ui.default_view },
        advanced: { show_skills: settings.showSkills, show_meta: settings.showMeta },
      });
      push('配置已保存（host/port 修改需重启服务后生效）', 'success');
      onClose();
    } catch (e) {
      push(e instanceof Error ? e.message : '保存失败', 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title="设置 · 配置中心"
      onClose={onClose}
      width={560}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onClose} disabled={saving}>
            取消
          </button>
          <button className="btn btn-primary" onClick={save} disabled={saving || !cfg}>
            {saving ? '保存中…' : '保存'}
          </button>
        </>
      }
    >
      {/* ---- 本地界面偏好 ---- */}
      <div className="section-title">界面（本地保存，仅当前浏览器）</div>
      <div style={{ display: 'flex', gap: 16 }}>
        {THEME_OPTIONS.map((o) => (
          <label key={o.value} className="checkbox-row">
            <input
              type="radio"
              name="theme"
              checked={settings.theme === o.value}
              onChange={() => set({ theme: o.value })}
            />
            {o.label}
          </label>
        ))}
      </div>
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={settings.showSkills}
          onChange={(e) => set({ showSkills: e.target.checked })}
        />
        显示 SKILL 文件
      </label>
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={settings.showMeta}
          onChange={(e) => set({ showMeta: e.target.checked })}
        />
        显示 META 文件（如 openclaw.json，修改需谨慎）
      </label>

      {/* ---- 服务端配置（config.toml） ---- */}
      <div className="section-title" style={{ marginTop: 20 }}>
        服务端配置（写入 config.toml，全端生效）
      </div>
      {loadError ? (
        <div className="hint" style={{ color: 'var(--danger, #d9534f)' }}>
          读取服务端配置失败：{loadError}
        </div>
      ) : !cfg ? (
        <div className="hint">读取中…</div>
      ) : (
        <>
          <div className="field">
            <label>备份保留天数</label>
            <input
              type="number"
              className="input"
              min={1}
              max={3650}
              value={cfg.backup.retention_days}
              onChange={(e) =>
                patchCfg('backup', 'retention_days', Number(e.target.value) || 1)
              }
            />
          </div>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={cfg.backup.auto_backup_on_write}
              onChange={(e) => patchCfg('backup', 'auto_backup_on_write', e.target.checked)}
            />
            写入前自动备份
          </label>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={cfg.lint.enabled}
              onChange={(e) => patchCfg('lint', 'enabled', e.target.checked)}
            />
            启用 Lint 检查
          </label>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={cfg.lint.strict_mode}
              onChange={(e) => patchCfg('lint', 'strict_mode', e.target.checked)}
            />
            严格模式（Lint 违规阻止保存）
          </label>
          <div className="field">
            <label>默认文件视图</label>
            <select
              className="select"
              value={cfg.ui.default_view}
              onChange={(e) => patchCfg('ui', 'default_view', e.target.value)}
            >
              <option value="tree">树形</option>
              <option value="list">列表</option>
            </select>
          </div>
          <div className="field">
            <label>OpenClaw 根目录（只读）</label>
            <input className="input" value={cfg.openclaw.dir} readOnly />
          </div>
        </>
      )}
      <div className="hint">
        提示：备份保留天数 / 自动备份 / Lint 开关保存后立即生效；host / port 等监听设置需重启服务。
      </div>
    </Modal>
  );
}
