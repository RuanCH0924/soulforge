/**
 * 后端连通性信号（单一事实源）。
 *
 * - `request()` 一旦拿到 HTTP 响应（含 4xx / 5xx）→ 判定**在线**（服务器在，只是这次请求业务失败）；
 * - `fetch` 抛错（断网 / 后端未启动 / 后端重启中）→ 判定**离线**。
 *
 * UI 通过 `useBackendOnline()` 订阅：状态栏连接点、顶部断连横幅、自动重连探测都以此为准，
 * 从而做到「后端重启后自动恢复」，而不是只能手动刷新页面。
 */
type Listener = (online: boolean) => void;

let online = true;
const listeners = new Set<Listener>();

function emit(): void {
  listeners.forEach((l) => l(online));
}

/** 请求拿到了 HTTP 响应 → 服务器在线 */
export function reportOnline(): void {
  if (online) return;
  online = true;
  emit();
}

/** 请求未拿到响应（网络层失败）→ 服务器离线 */
export function reportOffline(): void {
  if (!online) return;
  online = false;
  emit();
}

export function isOnline(): boolean {
  return online;
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
