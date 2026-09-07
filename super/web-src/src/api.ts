/**
 * API client — SOLID: Single responsibility (transport), Open/Closed (extend via HttpClient),
 * Dependency Inversion (depends on TokenStore abstraction, not concrete window).
 * Robust error handling via typed errors, never leaks raw stack to UI.
 */
import type { GateInfo, Session, SessionSummary, TaskNode } from './types';
import { AbortError, ApiError, NetworkError, StreamError, ValidationError } from './lib/errors';
import type { IApiService } from './services/api.types';

export type AgentSpec = {
  id: string;
  name: string;
  role: string;
  summary?: string;
  system_addon?: string;
  tools?: string[] | null;
  groups?: string[] | null;
  disabled?: string[];
  status: string;
  created_by?: string;
  policy?: { may_write?: boolean; may_spawn?: boolean; may_manage_agents?: boolean };
  created?: string;
  updated?: string;
};

// ── Token storage abstraction (DIP) ──
export interface TokenStore {
  get(): string;
  set(token: string): void;
}
class SessionTokenStore implements TokenStore {
  private key = 'super_token';
  get(): string {
    try {
      const q = new URLSearchParams(window.location.search).get('token');
      if (q) this.set(q);
      return sessionStorage.getItem(this.key) || '';
    } catch {
      return '';
    }
  }
  set(token: string): void {
    try { sessionStorage.setItem(this.key, token); } catch { /* quota or privacy */ }
  }
}
const tokenStore: TokenStore = new SessionTokenStore();

/** Persist bearer token (also picks up ?token= on first get). */
export function setAuthToken(token: string): void {
  tokenStore.set((token || '').trim());
}
export function getAuthToken(): string {
  return tokenStore.get();
}
export function hasAuthToken(): boolean {
  return Boolean(tokenStore.get());
}

export type StreamChatOpts = {
  signal?: AbortSignal;
  skipUserAppend?: boolean;
  onEvent?: (ev: Record<string, unknown>) => void;
};

// ── HTTP transport (SRP) ──
type HttpMethod = 'GET' | 'POST' | 'DELETE';
class HttpClient {
  private store: TokenStore;
  private timeoutMs: number;
  constructor(store: TokenStore, timeoutMs = 125_000) {
    this.store = store;
    this.timeoutMs = timeoutMs;
  }

  private headers(extra?: Record<string, string>): Record<string, string> {
    const h: Record<string, string> = { ...(extra || {}) };
    const t = this.store.get();
    if (t) h['Authorization'] = `Bearer ${t}`;
    return h;
  }

  private async parseError(res: Response): Promise<string> {
    try {
      const text = await res.text();
      if (!text) return `${res.status} ${res.statusText}`;
      try {
        const j = JSON.parse(text);
        return (j.error as string) || (j.message as string) || text;
      } catch {
        return text;
      }
    } catch {
      return `${res.status} ${res.statusText}`;
    }
  }

  async request<T>(path: string, method: HttpMethod = 'GET', body?: unknown, extraHeaders?: Record<string, string>): Promise<T> {
    const controller = new AbortController();
    const id = window.setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const headers = this.headers(extraHeaders);
      const init: RequestInit = { method, headers, signal: controller.signal };
      if (body !== undefined) {
        headers['Content-Type'] = 'application/json';
        init.body = JSON.stringify(body);
      }
      let res: Response;
      try {
        res = await fetch(path, init);
      } catch (e) {
        if ((e as Error).name === 'AbortError') throw new NetworkError('Request timed out', e);
        throw new NetworkError((e as Error).message || 'Network error', e);
      }
      if (!res.ok) {
        const msg = await this.parseError(res);
        throw new ApiError(msg, res.status);
      }
      // 204 has no body
      if (res.status === 204) return undefined as T;
      const ct = res.headers.get('content-type') || '';
      if (ct.includes('application/json')) return (await res.json()) as T;
      return (await res.text()) as unknown as T;
    } finally {
      window.clearTimeout(id);
    }
  }
}

const http = new HttpClient(tokenStore);

// ── Validation (SRP) ──
function requireNonEmpty(value: string, field: string): void {
  if (!value || !value.trim()) throw new ValidationError(`${field} is required`, field);
}
function requireId(id: string): void {
  if (!id || !id.trim()) throw new ValidationError('id is required', 'id');
}

// ── Concrete service (ISP: split, DIP: depends on HttpClient abstraction) ──
class ApiService implements IApiService {
  health() {
    return http.request<{ ok: boolean; model: string }>('/api/health', 'GET');
  }
  tree() {
    return http.request<{ tasks: TaskNode[] }>('/api/tree', 'GET');
  }
  ledger() {
    return http.request<{ gates: Record<string, { pass: number; reject: number }>; open_criticals: unknown[] }>('/api/ledger', 'GET');
  }
  report() {
    return http.request<{ tasks: TaskNode[]; proven: number; total: number; gates: Record<string, { pass: number; reject: number }>; open_criticals: unknown[] }>('/api/report', 'GET');
  }
  sessions() {
    return http.request<{ sessions: SessionSummary[] }>('/api/sessions', 'GET');
  }
  session(id: string) {
    requireId(id);
    return http.request<Session>(`/api/session?id=${encodeURIComponent(id)}`, 'GET');
  }
  createSession(title = 'New chat') {
    if (title.length > 120) title = title.slice(0, 120);
    return http.request<{ id: string }>('/api/sessions', 'POST', { title });
  }
  prove(id: string, proof: string) {
    requireId(id);
    requireNonEmpty(proof, 'proof');
    return http.request<{ ok: boolean }>('/api/prove', 'POST', { id, proof });
  }
  addTask(title: string, done = '') {
    requireNonEmpty(title, 'title');
    return http.request<{ ok: boolean; id: string; task?: unknown }>('/api/task', 'POST', { title, done });
  }
  approve(id: string, note: string) {
    requireId(id);
    return http.request<{ ok: boolean }>('/api/approve', 'POST', { id, note: note || 'approved' });
  }
  sendBack(id: string, note: string) {
    requireId(id);
    return http.request<{ ok: boolean }>('/api/send-back', 'POST', { id, note: note || 'needs work' });
  }
  async streamChat(
    sessionId: string | null,
    message: string,
    onDelta: (d: string) => void,
    onEventOrOpts?: ((ev: Record<string, unknown>) => void) | StreamChatOpts,
  ) {
    requireNonEmpty(message, 'message');
    const opts: StreamChatOpts =
      typeof onEventOrOpts === 'function' ? { onEvent: onEventOrOpts } : (onEventOrOpts || {});
    return streamChatImpl(sessionId, message, onDelta, tokenStore, opts);
  }
  getTools() { return http.request<{ tools: Record<string, unknown> }>('/api/tools', 'GET'); }
  listAgents(includeArchived = false) {
    const q = includeArchived ? '?include_archived=1' : '';
    return http.request<{ agents: AgentSpec[] }>(`/api/agents${q}`, 'GET');
  }
  getAgent(id: string) {
    requireId(id);
    return http.request<{ agent: AgentSpec }>(`/api/agent?id=${encodeURIComponent(id)}`, 'GET');
  }
  createAgent(body: Partial<AgentSpec> & { name: string }) {
    requireNonEmpty(body.name, 'name');
    return http.request<{ ok: boolean; agent: AgentSpec }>('/api/agents', 'POST', body);
  }
  updateAgent(id: string, patch: Record<string, unknown>) {
    requireId(id);
    return http.request<{ ok: boolean; agent: AgentSpec }>('/api/agent', 'POST', { id, action: 'update', ...patch });
  }
  approveAgent(id: string) {
    requireId(id);
    return http.request<{ ok: boolean; agent: AgentSpec }>('/api/agent', 'POST', { id, action: 'approve' });
  }
  archiveAgent(id: string) {
    requireId(id);
    return http.request<{ ok: boolean; agent: AgentSpec }>(`/api/agent?id=${encodeURIComponent(id)}`, 'DELETE');
  }
  runAgent(id: string, goal: string) {
    requireId(id);
    requireNonEmpty(goal, 'goal');
    return http.request<{ ok: boolean; reply: string; span_id: string; run_id: string }>('/api/agent', 'POST', { id, action: 'run', goal });
  }
  sbom() { return http.request<{ packages: { name: string; version: string }[]; count: number }>('/api/sbom', 'GET'); }
  sink() { return http.request<{ entries: number; violations: unknown[]; clean: boolean }>('/api/sink', 'GET'); }
  checklist() { return http.request<{ checklist: string[] }>('/api/checklist', 'GET'); }
  waivers() { return http.request<{ waivers: unknown[] }>('/api/waivers', 'GET'); }
  diff(opts: { id?: string; paths?: string[] } = {}) {
    const qs = new URLSearchParams();
    if (opts.id) qs.set('id', opts.id);
    for (const p of opts.paths || []) qs.append('path', p);
    const q = qs.toString();
    return http.request<{ ok: boolean; diff: string; paths: string[]; empty: boolean; error?: string | null }>(
      `/api/diff${q ? `?${q}` : ''}`,
      'GET',
    );
  }
  spec(id: string) { requireId(id); return http.request<{ task: import('./types').TaskNode; spec: { acceptance: string[]; pinned: boolean } }>(`/api/spec?id=${encodeURIComponent(id)}`, 'GET'); }
  pinSpec(id: string, acceptance: string[]) {
    requireId(id);
    if (!acceptance.length) throw new Error('acceptance criteria required');
    return http.request<{ ok: boolean; spec: { acceptance: string[]; pinned: boolean } }>('/api/spec/pin', 'POST', { id, acceptance });
  }
  models() { return http.request<{ models: string[]; current: string; context_length?: number | null }>('/api/models', 'GET'); }
  setModel(model: string) { requireNonEmpty(model, 'model'); return http.request<{ ok: boolean; model: string; context_length?: number | null }>('/api/model', 'POST', { model }); }
  workspace() { return http.request<{ workspace: string; state_dir: string; config_path: string | null }>('/api/workspace', 'GET'); }
  setWorkspace(path: string) { requireNonEmpty(path, 'path'); return http.request<{ ok: boolean; workspace: string }>('/api/workspace', 'POST', { path }); }
  pickFolder(path?: string | null) {
    return http.request<{ ok: boolean; cancelled: boolean; path: string | null }>(
      '/api/fs/pick',
      'POST',
      path ? { path } : {},
    );
  }
  reload() { return http.request<{ ok: boolean; workspace: string; model: string }>('/api/reload', 'POST', {}); }
  getConfig() { return http.request<{ config: Record<string, unknown> }>('/api/config', 'GET'); }
  updateConfig(patch: Record<string, unknown>) {
    return http.request<{ ok: boolean; config: Record<string, unknown> }>('/api/config', 'POST', patch);
  }
  deleteSession(id: string) { requireId(id); return http.request<{ ok: boolean }>(`/api/session?id=${encodeURIComponent(id)}`, 'DELETE'); }
  renameSession(id: string, title?: string | null) {
    requireId(id);
    const body: Record<string, unknown> = { id };
    if (title !== undefined) body.title = title;
    return http.request<{ ok: boolean; id: string; title: string }>('/api/session/rename', 'POST', body);
  }
  branchSession(id: string, upTo: number, title?: string) {
    requireId(id);
    return http.request<{ ok: boolean; id: string }>('/api/session/branch', 'POST', { id, up_to: upTo, title });
  }
  editMessage(id: string, idx: number, content: string) {
    requireId(id);
    requireNonEmpty(content, 'content');
    return http.request<{ ok: boolean }>('/api/session/edit', 'POST', { id, idx, content });
  }
  rollback(id: string) { requireId(id); return http.request<{ ok: boolean; reopened: string[] }>('/api/rollback', 'POST', { id }); }
  leaf() { return http.request<{ leaf: import('./types').TaskNode | null; rendered: string }>('/api/leaf', 'GET'); }
}

export const api: IApiService = new ApiService();

// ── Streaming (SRP, robust) ──
async function streamChatImpl(
  sessionId: string | null,
  message: string,
  onDelta: (d: string) => void,
  store: TokenStore,
  opts: StreamChatOpts = {},
): Promise<{ session_id: string; gate: GateInfo }> {
  if (!onDelta || typeof onDelta !== 'function') throw new ValidationError('onDelta callback required');
  const t = store.get();
  const controller = new AbortController();
  const external = opts.signal;
  const onExternalAbort = () => controller.abort();
  if (external) {
    if (external.aborted) controller.abort();
    else external.addEventListener('abort', onExternalAbort, { once: true });
  }
  const timeout = window.setTimeout(() => controller.abort(), 300_000);

  let res: Response;
  try {
    res = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(t ? { Authorization: `Bearer ${t}` } : {}) },
      body: JSON.stringify({
        session_id: sessionId,
        message,
        ...(opts.skipUserAppend ? { skip_user_append: true } : {}),
      }),
      signal: controller.signal,
    });
  } catch (e) {
    window.clearTimeout(timeout);
    if (external) external.removeEventListener('abort', onExternalAbort);
    if ((e as Error).name === 'AbortError') {
      if (external?.aborted) throw new AbortError('Stream stopped', e);
      throw new NetworkError('Stream timed out', e);
    }
    throw new NetworkError((e as Error).message, e);
  }

  if (!res.ok || !res.body) {
    window.clearTimeout(timeout);
    if (external) external.removeEventListener('abort', onExternalAbort);
    const msg = await res.text().catch(() => `${res.status} ${res.statusText}`);
    let parsed = msg;
    try { const j = JSON.parse(msg); parsed = j.error || j.message || msg; } catch { /* keep raw */ }
    throw new ApiError(parsed, res.status);
  }

  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  let done: { session_id: string; gate: GateInfo } | null = null;

  try {
    outer: for (;;) {
      const { value, done: eof } = await reader.read();
      if (value) buf += dec.decode(value, { stream: !eof });
      let idx: number;
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const frame = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        for (const line of frame.split('\n')) {
          if (!line.startsWith('data:')) continue;
          const raw = line.slice(5).trim();
          if (!raw) continue;
          let evt: unknown;
          try {
            evt = JSON.parse(raw);
          } catch (e) {
            throw new StreamError('Invalid stream frame', e);
          }
          const o = evt as {
            delta?: string;
            done?: boolean;
            session_id?: string;
            gate?: GateInfo;
            tool_call?: unknown;
            tool_result?: unknown;
            llm_stats?: unknown;
            error?: string;
          };
          if (o.error) throw new StreamError(o.error);
          opts.onEvent?.(o as Record<string, unknown>);
          if (typeof o.delta === 'string' && o.delta) onDelta(o.delta);
          if (o.done) {
            if (!o.session_id || !o.gate) throw new StreamError('Malformed done frame');
            done = { session_id: o.session_id, gate: o.gate };
            break outer; // don't wait for connection close / keep-alive
          }
        }
      }
      if (eof) break;
    }
  } catch (e) {
    if ((e as Error).name === 'AbortError') {
      if (external?.aborted) throw new AbortError('Stream stopped', e);
      throw new NetworkError('Stream timed out', e);
    }
    if (e instanceof StreamError || e instanceof ApiError || e instanceof AbortError) throw e;
    throw new StreamError((e as Error).message || 'Stream failed', e);
  } finally {
    window.clearTimeout(timeout);
    if (external) external.removeEventListener('abort', onExternalAbort);
    try { await reader.cancel(); } catch { /* ignore */ }
    try { reader.releaseLock(); } catch { /* ignore */ }
  }

  if (!done) throw new StreamError('Stream ended without done frame');
  return done;
}

// Backward-compatible named export
export async function streamChat(
  sessionId: string | null,
  message: string,
  onDelta: (d: string) => void,
  onEventOrOpts?: ((ev: Record<string, unknown>) => void) | StreamChatOpts,
): Promise<{ session_id: string; gate: GateInfo }> {
  const opts: StreamChatOpts =
    typeof onEventOrOpts === 'function' ? { onEvent: onEventOrOpts } : (onEventOrOpts || {});
  return streamChatImpl(sessionId, message, onDelta, tokenStore, opts);
}
