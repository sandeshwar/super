/**
 * API contract — SOLID: Interface Segregation & Dependency Inversion.
 * Components depend on IApiService, not concrete fetch.
 */
import type { GateInfo, Session, SessionSummary } from '../types';

export interface IHealthService {
  health(): Promise<{ ok: boolean; model: string; version?: string; llm_reachable?: boolean; llm_detail?: string }>;
}
export interface ILedgerService {
  ledger(): Promise<{ gates: Record<string, { pass: number; reject: number }>; open_criticals: unknown[] }>;
}
export interface ISessionService {
  sessions(): Promise<{ sessions: SessionSummary[] }>;
  session(id: string): Promise<Session>;
  createSession(title?: string): Promise<{ id: string }>;
  cancelChat(sessionId: string): Promise<{ ok: boolean; cancelled: boolean }>;
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
export type CapabilitySpec = {
  id: string;
  name: string;
  summary?: string;
  description?: string;
  kind: string;
  risk: string;
  status: string;
  group?: string;
  parameters?: Record<string, unknown>;
  impl?: Record<string, unknown>;
  tests?: unknown[];
  created_by?: string;
  created_at?: string;
  updated_at?: string;
  test_report?: { ok?: boolean; ran?: number; passed?: number; failed?: number; detail?: unknown };
};
export type MemoryClaim = {
  id: number;
  text: string;
  source: string;
  verification: string;
  taint?: string;
  valid_from?: string;
  valid_until?: string;
  superseded_by?: string;
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
export interface IMemoryService {
  listMemory(opts?: { q?: string; includeDead?: boolean; limit?: number; offset?: number }): Promise<{ claims: MemoryClaim[]; total: number; query?: string }>;
  addMemory(text: string, opts?: { source?: string; verification?: string }): Promise<{ ok: boolean; claim: MemoryClaim }>;
  confirmMemory(id: number, verification?: string): Promise<{ ok: boolean; claim: MemoryClaim }>;
  supersedeMemory(id: number, replacement: string): Promise<{ ok: boolean; claim: MemoryClaim }>;
  retireMemory(id: number): Promise<{ ok: boolean; claim: MemoryClaim }>;
}
export type AgendaItem = {
  id: string;
  kind: string;
  priority: string;
  status: string;
  title: string;
  detail?: string;
  action?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
  result?: unknown;
};
export interface ICapabilitiesService {
  listCapabilities(includeRetired?: boolean): Promise<{ capabilities: CapabilitySpec[] }>;
  approveCapability(id: string): Promise<{ ok: boolean; capability: CapabilitySpec }>;
  rejectCapability(id: string, reason?: string): Promise<{ ok: boolean; capability: CapabilitySpec }>;
  retireCapability(id: string): Promise<{ ok: boolean; capability: CapabilitySpec }>;
}
export interface IIntelligenceService {
  getIntelligence(includeDone?: boolean): Promise<{ agenda: AgendaItem[]; stats: Record<string, unknown>; briefing: string }>;
  tickIntelligence(force?: boolean): Promise<{ ok: boolean; refresh?: unknown; auto_act?: unknown; briefing?: string }>;
  pursueAgenda(id?: string): Promise<{ ok: boolean; item?: AgendaItem; result?: unknown; needs_model?: boolean; guidance?: string }>;
  dismissAgenda(id: string, reason?: string): Promise<{ ok: boolean; item: AgendaItem }>;
}
export interface ISecurityService {
  sbom(): Promise<{ packages: { name: string; version: string }[]; count: number }>;
  sink(): Promise<{ entries: number; violations: unknown[]; clean: boolean }>;
  checklist(): Promise<{ checklist: string[] }>;
  waivers(): Promise<{ waivers: unknown[] }>;
  diff(opts?: { paths?: string[] }): Promise<{ ok: boolean; diff: string; paths: string[]; empty: boolean; error?: string | null }>;
}
export interface IModelService {
  models(): Promise<{
    models: string[];
    current: string;
    context_length?: number | null;
    think?: string;
    think_levels?: string[];
    think_supported?: boolean;
    capabilities?: string[];
  }>;
  setModel(model: string, think?: boolean | string): Promise<{
    ok: boolean;
    model: string;
    context_length?: number | null;
    think?: string;
    think_levels?: string[];
    think_supported?: boolean;
    capabilities?: string[];
  }>;
  setThink(think: boolean | string): Promise<{
    ok: boolean;
    model: string;
    context_length?: number | null;
    think?: string;
    think_levels?: string[];
    think_supported?: boolean;
    capabilities?: string[];
  }>;
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
}
export type IApiService = IHealthService & ILedgerService & ISessionService & IStreamService & ISecurityService & IModelService & IWorkspaceService & IConfigService & IChatDeleteService & IRenameService & IChatEditService & IToolsCatalogService & IAgentsService & IMemoryService & ICapabilitiesService & IIntelligenceService;
