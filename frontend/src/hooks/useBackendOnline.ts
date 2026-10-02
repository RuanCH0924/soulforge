import { useEffect, useState } from 'react';
import { isOnline, subscribe } from '../api/connection';

/** 订阅后端连通性（由 api/client.ts 在每次请求时上报）。用于状态栏连接点、断连横幅与自动重连。 */
export function useBackendOnline(): boolean {
  const [online, setOnline] = useState(isOnline);
  useEffect(() => subscribe(setOnline), []);
  return online;
}
