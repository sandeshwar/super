import * as React from 'react';
import { userMessage } from '../lib/errors';

type Props = { children: React.ReactNode; fallback?: React.ReactNode };
type State = { hasError: boolean; message: string; resetKey: number };

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false, message: '', resetKey: 0 };
  static getDerivedStateFromError(e: unknown): Partial<State> {
    return { hasError: true, message: userMessage(e) };
  }
  componentDidCatch(error: unknown, info: unknown) {
    console.error('[SUPER] boundary', error, info);
  }
  private retry = () => {
    this.setState((s) => ({ hasError: false, message: '', resetKey: s.resetKey + 1 }));
  };
  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? (
        <div className="alert alert--error" role="alert" style={{ margin: 'var(--space-4)' }}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0, marginTop: 2 }}><circle cx="8" cy="8" r="5.5" stroke="currentColor" strokeWidth="1.2"/><path d="M8 7v3M8 5.5h.01" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600 }}>Something went wrong</div>
            <div className="small muted" style={{ marginTop: 4, color: 'inherit', opacity: .9 }}>{this.state.message}</div>
            <button className="btn btn-sm" style={{ marginTop: 10 }} onClick={this.retry}>Try again</button>
          </div>
        </div>
      );
    }
    return <React.Fragment key={this.state.resetKey}>{this.props.children}</React.Fragment>;
  }
}
