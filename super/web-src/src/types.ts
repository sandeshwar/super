export interface LlmStats {
  source?: string;
  step?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  cached_tokens?: number;
  prefill_tps?: number;
  decode_tps?: number;
  prompt_ms?: number;
  eval_ms?: number;
  load_ms?: number;
  total_ms?: number;
  done_reason?: string;
}

export interface GateInfo {
  ok: boolean;
  missing: string[];
  checked: number;
  skipped?: boolean;
  agent?: {
    steps?: number;
    tools?: { name: string; ok: boolean; taint?: string }[];
    llm_stats?: LlmStats | null;
    llm_stats_steps?: LlmStats[];
  };
}

export interface MediaPart {
  kind?: 'image' | string;
  id?: string;
  /** data: URL, http(s), or /api/media/<id> */
  src: string;
  mime?: string;
  alt?: string;
  bytes?: number;
  source?: string;
  path?: string;
}

/** Agent-presented artifact for the side canvas panel. */
export interface CanvasPart {
  id: string;
  action?: 'present' | 'update' | 'close' | string;
  kind: 'url' | 'image' | 'video' | 'markdown' | 'html' | 'file' | 'doc' | string;
  title?: string;
  src?: string;
  content?: string;
  mime?: string;
  path?: string;
  alt?: string;
  bytes?: number;
  open?: boolean;
  detachable?: boolean;
  content_truncated?: boolean;
  /** False when X-Frame-Options / CSP blocks iframe embed. */
  embeddable?: boolean;
  embed_note?: string;
}

/** Chronological assistant-turn timeline (think → text → media → …). */
export type ChatBlock =
  | { kind: 'thinking'; text: string; step?: number }
  | { kind: 'text'; text: string; step?: number }
  | { kind: 'media'; media: MediaPart[]; step?: number; tool?: string }
  | { kind: 'canvas'; canvas: CanvasPart; step?: number; tool?: string };

export interface ToolEvent {
  kind: 'call' | 'result';
  name: string;
  ok?: boolean;
  arguments?: unknown;
  content?: string;
  media?: MediaPart[];
  canvas?: CanvasPart;
}

/** Human approval request attached to an assistant turn (agents/caps/memory). */
export interface ApprovalRequest {
  kind: 'agent' | 'capability' | 'memory' | string;
  id: string | number;
  title: string;
  detail?: string;
  status?: 'pending' | 'approved' | 'rejected' | 'confirmed' | string;
  meta?: Record<string, unknown>;
}

/** Child specialist span shown in parent chat + session list. */
export interface ChildSpan {
  span_id: string;
  agent_id?: string;
  agent_name?: string;
  role?: string;
  status: 'running' | 'done' | 'error' | string;
  summary: string;
  goal?: string;
  steps?: number | null;
  session_id?: string;
  child_session_id?: string | null;
  run_id?: string;
  started?: string;
  ended?: string;
  updated?: string;
  tool?: string;
  error?: string;
}

export interface ChatMessage {
  role: string;
  content: string;
  /** Model reasoning trace (Ollama thinking / &lt;think&gt;), separate from content. */
  thinking?: string;
  /** Per ReAct-step reasoning blocks (preferred over a single joined `thinking`). */
  thoughts?: string[];
  /** Stream-only: latest thought block is still receiving tokens. */
  thinkingLive?: boolean;
  /** Chronological think/text/media timeline for this turn. */
  blocks?: ChatBlock[];
  /** Normalized images (and future media) for album rendering. */
  media?: MediaPart[];
  /** Latest canvas artifacts presented during this turn. */
  canvas?: CanvasPart[];
  ts: string;
  gate?: GateInfo;
  tools?: ToolEvent[];
  children?: ChildSpan[];
  approvals?: ApprovalRequest[];
}

export interface Session {
  id: string;
  title: string;
  created: string;
  updated: string;
  messages: ChatMessage[];
  parent?: string | null;
  span_id?: string | null;
  agent_id?: string | null;
  kind?: string;
  /** True while a server-side completion is still running (survives tab close). */
  generating?: boolean;
}

export interface SessionSummary {
  id: string;
  title: string;
  updated: string;
  n: number;
  kind?: string;
  spans?: ChildSpan[];
  parent?: string | null;
  generating?: boolean;
}

export interface TaskNode {
  id: string;
  title: string;
  why: string;
  done: string;
  needs: string[];
  blocks: string[];
  files: string[];
  parent: string | null;
  proof: string;
  status: 'waiting' | 'doing' | 'proven' | 'blocked';
}
