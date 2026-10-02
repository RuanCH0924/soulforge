import { Modal } from './Modal';

interface ShortcutsModalProps {
  onClose: () => void;
  /** 页面内嵌模式（P2 页面化，保留） */
  embedded?: boolean;
}

interface Shortcut {
  keys: string;
  desc: string;
}

interface Group {
  title: string;
  items: Shortcut[];
}

/** 快捷键事实源与 docs/UI-SPECS.md §七 保持一致 */
const GROUPS: Group[] = [
  {
    title: '全局',
    items: [
      { keys: 'Ctrl/⌘ + K', desc: '打开命令面板（导航 / 功能 / 文件 / 最近打开）' },
      { keys: 'Ctrl/⌘ + S', desc: '保存当前编辑窗口' },
      { keys: 'Ctrl/⌘ + Shift + S', desc: '保存全部未保存窗口' },
      { keys: 'Ctrl/⌘ + Shift + E', desc: '前往「业务工具 → 跨 Agent 编辑」' },
      { keys: '?', desc: '打开本快捷键帮助（输入框 / 编辑器聚焦时不触发）' },
      { keys: 'Esc', desc: '关闭弹窗 / 命令面板 / 下拉菜单' },
    ],
  },
  {
    title: '主工作台',
    items: [
      { keys: 'Ctrl/⌘ + 1 / 2 / 3', desc: '切换到第 N 个编辑窗口' },
      { keys: 'Alt + W', desc: '关闭当前文档（有未保存修改会二次确认）' },
      { keys: 'Alt + 1', desc: '折叠 / 展开左栏（Agent 树）' },
      { keys: 'Alt + 2', desc: '折叠 / 展开中栏（文件树）' },
      { keys: '↑ / ↓', desc: '文件树聚焦时上下移动并打开文件' },
    ],
  },
  {
    title: '编辑器',
    items: [
      { keys: 'Ctrl/⌘ + B', desc: '加粗（源码编辑模式，编辑器聚焦时）' },
      { keys: 'Ctrl/⌘ + I', desc: '斜体（源码编辑模式）' },
      { keys: 'Ctrl/⌘ + Shift + O', desc: '打开 / 关闭文档大纲' },
      { keys: 'F8 / Shift + F8', desc: '跳到下一条 / 上一条 lint 警告' },
    ],
  },
];

export function ShortcutsModal({ onClose, embedded }: ShortcutsModalProps) {
  return (
    <Modal
      title="键盘快捷键"
      onClose={onClose}
      width={560}
      embedded={embedded}
      headerless={embedded}
      footer={
        <button className="btn" onClick={onClose}>
          关闭
        </button>
      }
    >
      {GROUPS.map((g) => (
        <div key={g.title}>
          <div className="section-title">{g.title}</div>
          <table className="shortcut-table">
            <tbody>
              {g.items.map((it) => (
                <tr key={it.keys}>
                  <td className="shortcut-keys">
                    <kbd>{it.keys}</kbd>
                  </td>
                  <td>{it.desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </Modal>
  );
}
