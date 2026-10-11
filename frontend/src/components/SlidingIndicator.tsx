import type { IndicatorBox } from '../hooks/useSlidingIndicator';

interface SlidingIndicatorProps {
  /** 主轴：纵向（一级导航）/ 横向（二级菜单） */
  axis: 'x' | 'y';
  /** 外观变体：导航底色块 / 分段控件底色块 / 页签下划线 */
  variant: 'nav' | 'seg' | 'tab';
  /** 由 useSlidingIndicator 量出的位置与主轴长度 */
  box: IndicatorBox | null;
  /** false 时不加过渡（首帧），避免刷新时从起点滑到当前项 */
  ready: boolean;
}

/**
 * 滑动指示器：一块会移动到当前选中项的底衬。
 * 一级导航与二级菜单共用同一套位移/时长/曲线（见 global.css 的 .slide-indicator），
 * 只靠 variant 区分外观，避免各菜单各写一套动效。
 */
export function SlidingIndicator({ axis, variant, box, ready }: SlidingIndicatorProps) {
  if (!box) return null;
  const style =
    axis === 'y'
      ? { transform: `translateY(${box.offset}px)`, height: box.size }
      : { transform: `translateX(${box.offset}px)`, width: box.size };
  return (
    <span
      className={`slide-indicator slide-indicator-${variant}${ready ? ' is-ready' : ''}`}
      style={style}
      aria-hidden="true"
    />
  );
}
