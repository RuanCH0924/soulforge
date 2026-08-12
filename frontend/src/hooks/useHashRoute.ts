import { useCallback, useEffect, useState } from 'react';

export type AppRoute = 'workbench' | 'tools' | 'data' | 'settings';

const VALID: AppRoute[] = ['workbench', 'tools', 'data', 'settings'];

function parse(hash: string): AppRoute {
  const seg = hash.replace(/^#\/?/, '').split('?')[0].toLowerCase();
  return (VALID.includes(seg as AppRoute) ? (seg as AppRoute) : 'workbench');
}

/** 轻量 hash 路由：不引入第三方依赖，刷新后保留页面 */
export function useHashRoute(): [AppRoute, (r: AppRoute) => void] {
  const [route, setRoute] = useState<AppRoute>(() => parse(window.location.hash));

  useEffect(() => {
    const onHash = () => setRoute(parse(window.location.hash));
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const navigate = useCallback((r: AppRoute) => {
    if (parse(window.location.hash) !== r) window.location.hash = `#/${r}`;
    setRoute(r);
  }, []);

  return [route, navigate];
}
