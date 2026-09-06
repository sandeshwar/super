export interface GateInfo {
  ok: boolean;
  missing: string[];
  checked: number;
  skipped?: boolean;
}

export interface ChatMessage {
  role: string;
  content: string;
  ts: string;
  gate?: GateInfo;
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
