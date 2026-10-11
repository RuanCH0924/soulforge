import { useEffect, useState } from 'react';

/**
 * 「先播退场、延时再卸载」：把一个布尔开关映射为「是否挂载」+「是否退场中」。
 *
 * 为什么需要它：`open && <div>` 在 `open` 变 false 的同一帧就卸载，退场过渡永远播不到。
 * 这里把卸载时刻推迟 `ms` 毫秒，期间返回 `closing = true`，由调用方挂上 `.is-closing`
 * （过渡目标值定义在 global.css 的「退场」段）。
 *
 * 退场期间若 `open` 又变回 true（用户反悔），会取消退场并原地复原。
 */
export function usePresence(open: boolean, ms: number): { mounted: boolean; closing: boolean } {
  const [mounted, setMounted] = useState(open);
  const [closing, setClosing] = useState(false);

  useEffect(() => {
    if (open) {
      setMounted(true);
      setClosing(false);
      return;
    }
    // 本来就是卸载态：没有东西可退场
    if (!mounted) return;
    setClosing(true);
    const timer = window.setTimeout(() => {
      setMounted(false);
      setClosing(false);
    }, ms);
    return () => window.clearTimeout(timer);
  }, [open, ms, mounted]);

  return { mounted, closing };
}
