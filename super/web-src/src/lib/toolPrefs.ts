/** Client chat/tool prefs not stored in server config. */
import { useSyncExternalStore } from 'react';

const KEY = 'super_tool_prefs';

export type ToolPrefs = {
  slashCommands: boolean;
  fileMentions: boolean;
  attachFiles: boolean;
  showShortcuts: boolean;
};

const DEFAULTS: ToolPrefs = {
  slashCommands: true,
  fileMentions: true,
  attachFiles: true,
  showShortcuts: true,
};

let prefs: ToolPrefs = load();
const listeners = new Set<() => void>();

function load(): ToolPrefs {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { ...DEFAULTS };
    return { ...DEFAULTS, ...JSON.parse(raw) };
  } catch {
    return { ...DEFAULTS };
  }
}

function emit() {
  listeners.forEach((l) => l());
}

export function getToolPrefs() {
  return prefs;
}

export function setToolPrefs(patch: Partial<ToolPrefs>) {
  prefs = { ...prefs, ...patch };
  try { localStorage.setItem(KEY, JSON.stringify(prefs)); } catch { /* ignore */ }
  emit();
}

export function useToolPrefs() {
  return useSyncExternalStore(
    (cb) => { listeners.add(cb); return () => { listeners.delete(cb); }; },
    getToolPrefs,
    getToolPrefs,
  );
}
