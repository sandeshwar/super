/**
 * API contract — SOLID: Interface Segregation & Dependency Inversion.
 * Components depend on IApiService, not concrete fetch.
 */
import type { GateInfo, Session, SessionSummary, TaskNode } from '../types';

export interface IHealthService {
  health(): Promise<{ ok: boolean; model: string; version?: string }>;
}
export interface ITaskService {
  tree(): Promise<{ tasks: TaskNode[]; tree?: unknown }>;
  ledger(): Promise<{ gates: Record<string, { pass: number; reject: number }>; open_criticals: unknown[] }>;
  report(): Promise<{ tasks: TaskNode[]; proven: number; total: number; gates: Record<string, { pass: number; reject: number }>; open_criticals: unknown[] }>;
  approve(id: string, note: string): Promise<{ ok: boolean }>;
  sendBack(id: string, note: string): Promise<{ ok: boolean }>;
  rollback(id: string): Promise<{ ok: boolean; reopened: string[] }>;
}
export interface ISessionService {
  sessions(): Promise<{ sessions: SessionSummary[] }>;
  session(id: string): Promise<Session>;
  createSession(title?: string): Promise<{ id: string }>;
}
export interface IStreamService {
  streamChat(sessionId: string | null, message: string, onDelta: (d: string) => void): Promise<{ session_id: string; gate: GateInfo }>;
}
export interface ISecurityService {
  sbom(): Promise<{ packages: { name: string; version: string }[]; count: number }>;
  sink(): Promise<{ entries: number; violations: unknown[]; clean: boolean }>;
  checklist(): Promise<{ checklist: string[] }>;
  waivers(): Promise<{ waivers: unknown[] }>;
  spec(id: string): Promise<{ task: import('./../types').TaskNode; spec: { acceptance: string[]; pinned: boolean } }>;
}
export interface IModelService {
  models(): Promise<{ models: string[]; current: string }>;
  setModel(model: string): Promise<{ ok: boolean; model: string }>;
}
export interface IWorkspaceService {
  workspace(): Promise<{ workspace: string; state_dir: string; config_path: string | null }>;
  setWorkspace(path: string): Promise<{ ok: boolean; workspace: string }>;
  reload(): Promise<{ ok: boolean; workspace: string; model: string }>;
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
export type IApiService = IHealthService & ITaskService & ISessionService & IStreamService & ISecurityService & IModelService & IWorkspaceService & IChatDeleteService & IRenameService & IChatEditService;
