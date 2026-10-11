import type { ReactNode } from 'react';

interface PaneToolsProps {
  /** 新建：不传 = 当前视图不支持新建（按钮置灰，原因写在 createHint） */
  onCreate?: () => void;
  /** 新建不可用时的原因（也作为可用时的说明文案） */
  createHint: string;
  /** 删除：不传 = 当前没有可删的选中项 */
  onDelete?: () => void;
  deleteHint: string;
}

/**
 * 二级栏（中栏）头部的工具槽位：＋新建 / 删除。
 *
 * 为什么抽成组件：Agent 模式（文件树）与 CORE 模式（CORE 文件 → Agent 列表）的二级栏
 * 必须**同一槽位、同一样式、同一可用性规则**，否则两个模式看起来像两套界面。
 * 差异只在语义：CORE 模式下「新建」没有落点（新建总要先确定写进哪个 Agent），故置灰并给出来由。
 *
 * 置灰用 `aria-disabled` 而不是 `disabled`：disabled 的按钮在浏览器里不会弹 title，
 * 而这里的置灰恰恰**要靠 title 解释原因**。不传 onClick 即为不可用。
 */
export function PaneTools({ onCreate, createHint, onDelete, deleteHint }: PaneToolsProps): ReactNode {
  return (
    <span className="filetree-tools">
      <button
        type="button"
        className={`tree-tool${onCreate ? '' : ' is-off'}`}
        aria-disabled={!onCreate}
        onClick={onCreate}
        title={createHint}
      >
        ＋ 新建
      </button>
      <button
        type="button"
        className={`tree-tool${onDelete ? '' : ' is-off'}`}
        aria-disabled={!onDelete}
        onClick={onDelete}
        title={deleteHint}
      >
        删除
      </button>
    </span>
  );
}
