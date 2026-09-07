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

export interface ToolEvent {
  kind: 'call' | 'result';
  name: string;
  ok?: boolean;
  arguments?: unknown;
  content?: string;
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
  ts: string;
  gate?: GateInfo;
  tools?: ToolEvent[];
  children?: ChildSpan[];
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
}

export interface SessionSummary {
  id: string;
  title: string;
  updated: string;
  n: number;
  kind?: string;
  spans?: ChildSpan[];
  parent?: string | null;
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
