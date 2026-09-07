/**
 * API contract — SOLID: Interface Segregation & Dependency Inversion.
 * Components depend on IApiService, not concrete fetch.
 */
import type { GateInfo, Session, SessionSummary, TaskNode } from '../types';

export interface IHealthService {
  health(): Promise<{ ok: boolean; model: string; version?: string; llm_reachable?: boolean; llm_detail?: string }>;
}
export interface ITaskService {
  tree(): Promise<{ tasks: TaskNode[]; tree?: unknown }>;
  ledger(): Promise<{ gates: Record<string, { pass: number; reject: number }>; open_criticals: unknown[] }>;
  report(): Promise<{ tasks: TaskNode[]; proven: number; total: number; gates: Record<string, { pass: number; reject: number }>; open_criticals: unknown[] }>;
  approve(id: string, note: string): Promise<{ ok: boolean }>;
  sendBack(id: string, note: string): Promise<{ ok: boolean }>;
  rollback(id: string): Promise<{ ok: boolean; reopened: string[] }>;
  prove(id: string, proof: string): Promise<{ ok: boolean }>;
  addTask(title: string, done?: string): Promise<{ ok: boolean; id: string; task?: unknown }>;
}
export interface ISessionService {
  sessions(): Promise<{ sessions: SessionSummary[] }>;
  session(id: string): Promise<Session>;
  createSession(title?: string): Promise<{ id: string }>;
}
export type StreamChatOpts = {
  signal?: AbortSignal;
  skipUserAppend?: boolean;
  onEvent?: (ev: Record<string, unknown>) => void;
};

export interface IStreamService {
  streamChat(
    sessionId: string | null,
    message: string,
    onDelta: (d: string) => void,
    onEventOrOpts?: ((ev: Record<string, unknown>) => void) | StreamChatOpts,
  ): Promise<{ session_id: string; gate: GateInfo }>;
}
export interface IToolsCatalogService {
  getTools(): Promise<{ tools: Record<string, unknown> }>;
}
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
export interface IAgentsService {
  listAgents(includeArchived?: boolean): Promise<{ agents: AgentSpec[] }>;
  getAgent(id: string): Promise<{ agent: AgentSpec }>;
  createAgent(body: Partial<AgentSpec> & { name: string }): Promise<{ ok: boolean; agent: AgentSpec }>;
  updateAgent(id: string, patch: Record<string, unknown>): Promise<{ ok: boolean; agent: AgentSpec }>;
  approveAgent(id: string): Promise<{ ok: boolean; agent: AgentSpec }>;
  archiveAgent(id: string): Promise<{ ok: boolean; agent: AgentSpec }>;
  runAgent(id: string, goal: string): Promise<{ ok: boolean; reply: string; span_id: string; run_id: string }>;
}
export interface ISecurityService {
  sbom(): Promise<{ packages: { name: string; version: string }[]; count: number }>;
  sink(): Promise<{ entries: number; violations: unknown[]; clean: boolean }>;
  checklist(): Promise<{ checklist: string[] }>;
  waivers(): Promise<{ waivers: unknown[] }>;
  spec(id: string): Promise<{ task: import('./../types').TaskNode; spec: { acceptance: string[]; pinned: boolean } }>;
  pinSpec(id: string, acceptance: string[]): Promise<{ ok: boolean; spec: { acceptance: string[]; pinned: boolean } }>;
  diff(opts?: { id?: string; paths?: string[] }): Promise<{ ok: boolean; diff: string; paths: string[]; empty: boolean; error?: string | null }>;
}
export interface IModelService {
  models(): Promise<{ models: string[]; current: string; context_length?: number | null }>;
  setModel(model: string): Promise<{ ok: boolean; model: string; context_length?: number | null }>;
}
export interface IWorkspaceService {
  workspace(): Promise<{ workspace: string; state_dir: string; config_path: string | null }>;
  setWorkspace(path: string): Promise<{ ok: boolean; workspace: string }>;
  pickFolder(path?: string | null): Promise<{ ok: boolean; cancelled: boolean; path: string | null }>;
  reload(): Promise<{ ok: boolean; workspace: string; model: string }>;
}
export interface IConfigService {
  getConfig(): Promise<{ config: Record<string, unknown> }>;
  updateConfig(patch: Record<string, unknown>): Promise<{ ok: boolean; config: Record<string, unknown> }>;
}
export interface IChatDeleteService {
  deleteSession(id: string): Promise<{ ok: boolean }>;
}
export interface IRenameService {
  renameSession(id: string, title?: string | null): Promise<{ ok: boolean; id: string; title: string }>;
}
export interface IChatEditService {
  branchSession(id: string, upTo: number, title?: string): Promise<{ ok: boolean; id: string }>;
  editMessage(id: string, idx: number, content: string): Promise<{ ok: boolean }>;
  leaf(): Promise<{ leaf: import('../types').TaskNode | null; rendered: string }>;
}
export type IApiService = IHealthService & ITaskService & ISessionService & IStreamService & ISecurityService & IModelService & IWorkspaceService & IConfigService & IChatDeleteService & IRenameService & IChatEditService & IToolsCatalogService & IAgentsService;
