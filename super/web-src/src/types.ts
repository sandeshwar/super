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

export interface ChatMessage {
  role: string;
  content: string;
  ts: string;
  gate?: GateInfo;
  tools?: ToolEvent[];
}

export interface Session {
  id: string;
  title: string;
  created: string;
  updated: string;
  messages: ChatMessage[];
}

export interface SessionSummary {
  id: string;
  title: string;
  updated: string;
  n: number;
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
