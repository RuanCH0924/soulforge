import { useLayoutEffect, useRef, useState } from 'react';
import type { MutableRefObject } from 'react';

export interface IndicatorBox {
  /** 沿主轴的偏移：纵向为 top、横向为 left（px） */
  offset: number;
  /** 沿主轴的长度：纵向为 height、横向为 width（px） */
  size: number;
}

export interface SlidingIndicatorResult<E extends HTMLElement> {
  containerRef: MutableRefObject<E | null>;
  box: IndicatorBox | null;
  /** 首帧后置为 true；在此之前不给指示器加过渡，避免刷新时从起点滑到当前项 */
  ready: boolean;
}

/**
 * 量出容器内「当前选中项」的位置与主轴长度，交给滑动指示器。
 * 一级导航（纵向）与二级菜单（页签 / 分段控件，横向）共用同一套机制，保证动效成体系。
 *
 * 用 offsetTop / offsetLeft 而不是 getBoundingClientRect 差值：offset 系列按
 * 「offsetParent 的内边距边」度量，与绝对定位子元素 `top/left: 0` 的基准完全一致，
 * 所以容器带 1px 边框时也不会偏 1px（分段控件就是这样）。
 */
export function useSlidingIndicator<E extends HTMLElement = HTMLDivElement>(
  activeKey: string,
  activeSelector: string,
  axis: 'x' | 'y',
): SlidingIndicatorResult<E> {
  const containerRef = useRef<E | null>(null);
  const [box, setBox] = useState<IndicatorBox | null>(null);
  const [ready, setReady] = useState(false);

  useLayoutEffect(() => {
    const measure = () => {
      const host = containerRef.current;
      const el = host?.querySelector<HTMLElement>(activeSelector);
      if (!host || !el) return;
      setBox(
        axis === 'y'
          ? { offset: el.offsetTop, size: el.offsetHeight }
          : { offset: el.offsetLeft, size: el.offsetWidth },
      );
    };
    measure();
    // 断点 / 文案变化会改变选中项的尺寸，尺寸变化时重新量一次
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, [activeKey, activeSelector, axis]);

  useLayoutEffect(() => {
    const id = window.requestAnimationFrame(() => setReady(true));
    return () => window.cancelAnimationFrame(id);
  }, []);

  return { containerRef, box, ready };
}
