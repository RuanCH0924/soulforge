import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { ErrorBoundary } from './components/ErrorBoundary';
import { SettingsProvider } from './hooks/useSettings';
import { LintScanProvider } from './hooks/useLintScan';
import { ToastProvider } from './hooks/useToast';
import './styles/global.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <SettingsProvider>
        <ToastProvider>
          <LintScanProvider>
            <App />
          </LintScanProvider>
        </ToastProvider>
      </SettingsProvider>
    </ErrorBoundary>
  </StrictMode>,
);

/**
 * 空闲时预取编辑器分包（Monaco 体积大且已懒加载，见 App.tsx 的 `lazy(() => import('./components/EditorPane'))`）。
 * 首屏渲染完成后再后台拉取，用户点开文档时即无需等待下载；本地自托管（localhost）几乎瞬时完成。
 * 用 requestIdleCallback 让出首屏；不支持时退化为 2s 后延时预取。失败静默（真打开时还会正常加载）。
 */
const prefetchEditor = () => {
  void import('./components/EditorPane').catch(() => undefined);
};
const ric = (window as { requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number })
  .requestIdleCallback;
if (typeof ric === 'function') {
  ric(prefetchEditor, { timeout: 4000 });
} else {
  window.setTimeout(prefetchEditor, 2000);
}
