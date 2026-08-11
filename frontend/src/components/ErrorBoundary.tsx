import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** 全局错误边界：页面崩溃时给出中文提示而不是白屏 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('[Soulforge] 页面错误:', error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="error-boundary">
          <h2>页面发生了错误</h2>
          <p className="muted">您可以尝试重新加载页面；如果问题持续出现，请检查后端服务状态。</p>
          <pre>{String(this.state.error.stack ?? this.state.error.message)}</pre>
          <button className="btn btn-primary" onClick={() => window.location.reload()}>
            重新加载
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
