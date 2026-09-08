import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import { userMessage } from '../lib/errors';
import { useAppearance, type Density, type Theme } from '../hooks/useTheme';
import { getToolPrefs, setToolPrefs, useToolPrefs } from '../lib/toolPrefs';
import { Alert } from './ui/Alert';
import { Button } from './ui/Button';
import { Card, CardBody, CardHead } from './ui/Card';
import { Input, Select } from './ui/Input';
import { Switch } from './ui/Switch';

export type SettingsSection =
  | 'model'
  | 'appearance'
  | 'tools'
  | 'agents'
  | 'mcp'
  | 'workspace'
  | 'safety'
  | 'about';

const SECTIONS: { id: SettingsSection; title: string; blurb: string }[] = [
  { id: 'model', title: 'Model', blurb: 'Which model answers, and how to reach it' },
  { id: 'appearance', title: 'Appearance', blurb: 'Theme, density, motion' },
  { id: 'tools', title: 'Tools', blurb: 'Agent tools, checks, and chat helpers' },
  { id: 'agents', title: 'Agents', blurb: 'Specialized sub-agents (CRUD + inherit parent rules)' },
  { id: 'mcp', title: 'MCP servers', blurb: 'Connect external tool servers' },
  { id: 'workspace', title: 'Working dir', blurb: 'Project folder — default cwd, not a sandbox' },
  { id: 'safety', title: 'Safety', blurb: 'Secret scans and package checks' },
  { id: 'about', title: 'About', blurb: 'Version and connection status' },
];

const GATE_META: Record<string, { label: string; desc: string }> = {
  grounding: { label: 'Ground answers in code', desc: 'Reject replies that invent symbols or files' },
  docs_before_write: { label: 'Read docs before edits', desc: 'Prefer docs when changing public APIs' },
  standards: { label: 'Coding standards', desc: 'Flag style and convention slips' },
  duplication: { label: 'Duplication check', desc: 'Catch copy-paste that should be shared' },
  verification: { label: 'Verification', desc: 'Require tests or proof where expected' },
  mutation: { label: 'Mutation testing', desc: 'Check tests actually catch bugs' },
  spec: { label: 'Spec match', desc: 'Keep work tied to pinned acceptance checks' },
  drift: { label: 'Drift check', desc: 'Detect when code wanders from the plan' },
  quality: { label: 'Quality budgets', desc: 'Limit size and complexity of edits' },
  security: { label: 'Security checks', desc: 'Run security gates on changes' },
  taint: { label: 'Untrusted input labels', desc: 'Track data from the web or MCP as untrusted' },
  ambition: { label: 'Scope guard', desc: 'Stop oversized or vague work' },
};

const SECURITY_META: Record<string, { label: string; desc: string }> = {
  block_secrets: { label: 'Block secrets', desc: 'Stop commits/edits that look like keys or tokens' },
  sast: { label: 'Static analysis', desc: 'Scan for common vulnerability patterns' },
  dependency_gate: { label: 'Dependency checks', desc: 'Review new packages before they land' },
  sink_audit: { label: 'Dangerous sinks', desc: 'Watch for unsafe eval/exec/shell paths' },
};

type PublicConfig = {
  llm: { endpoint: string; model: string; timeout_s: number; retries: number; health_path: string };
  envelope: { max_microtask_lines: number; best_of_n: number; max_steps_per_task: number; early_abort_stall: number };
  gates: Record<string, boolean>;
  security: Record<string, boolean>;
  mcp: { servers: McpServer[] };
  tools?: AgentToolsConfig;
  workspace?: string;
  state_dir?: string;
  config_path?: string | null;
};

type AgentToolsConfig = {
  enabled: boolean;
  discovery: boolean;
  max_result_chars: number;
  max_activated: number;
  groups: Record<string, boolean>;
  disabled: string[];
  packs?: Record<string, boolean>;
  pack_config?: Record<string, Record<string, string | number | boolean>>;
  builtin_config?: Record<string, Record<string, string | number | boolean>>;
  runtime?: 'auto' | 'stdlib' | 'langgraph';
};

type ConfigField = {
  key: string;
  label: string;
  type: string;
  required?: boolean;
  placeholder?: string;
  desc?: string;
  env?: string;
  default?: string | number | boolean;
  value?: string | number | boolean;
  has_value?: boolean | null;
};

type ToolCatalogGroup = {
  id: string;
  title: string;
  blurb: string;
  enabled: boolean;
  tools: { name: string; summary: string; risk: string; enabled: boolean; discovery?: boolean }[];
};

type ToolPack = {
  id: string;
  title: string;
  blurb: string;
  group: string;
  risk: string;
  enabled: boolean;
  loaded: boolean;
  install_ok: boolean;
  missing: string[];
  config_fields?: ConfigField[];
  needs_config?: boolean;
};

type ToolCatalog = {
  enabled: boolean;
  discovery: boolean;
  max_result_chars: number;
  max_activated: number;
  groups: ToolCatalogGroup[];
  packs?: ToolPack[];
  integrations?: { langchain?: boolean; langgraph?: boolean; crewai?: boolean };
  builtin_configs?: Record<string, ConfigField[]>;
};

export type McpServer = {
  id?: string;
  name: string;
  transport: 'sse' | 'stdio' | 'http';
  url?: string;
  command?: string;
  args?: string[];
  enabled?: boolean;
  has_env?: boolean;
};

type Props = {
  model: string;
  models: string[];
  workspace: string;
  onModelChange: (m: string) => void;
  onWorkspaceChange: (v: string) => void;
  fetchModels: () => void;
  fetchWorkspace: () => void;
  refresh: () => void;
  onContextLength?: (n: number | null) => void;
  section?: SettingsSection | null;
  onSectionChange?: (s: SettingsSection) => void;
};

function sectionFromHash(): SettingsSection {
  const h = (window.location.hash || '').replace(/^#/, '') as SettingsSection;
  return SECTIONS.some((s) => s.id === h) ? h : 'model';
}

export default function SettingsView({
  model, models, workspace, onModelChange, onWorkspaceChange,
  fetchModels, fetchWorkspace, refresh, onContextLength, section: controlledSection, onSectionChange,
}: Props) {
  const [section, setSection] = useState<SettingsSection>(() => controlledSection || sectionFromHash());
  const [cfg, setCfg] = useState<PublicConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const [wsDraft, setWsDraft] = useState(workspace);
  const [health, setHealth] = useState<{ ok: boolean; model: string; version?: string; llm_reachable?: boolean; llm_detail?: string } | null>(null);

  const appearance = useAppearance();
  const toolPrefs = useToolPrefs();

  const go = useCallback((id: SettingsSection) => {
    setSection(id);
    onSectionChange?.(id);
    const url = new URL(window.location.href);
    url.hash = id;
    window.history.replaceState(null, '', `${url.pathname}${url.search}#${id}`);
  }, [onSectionChange]);

  useEffect(() => {
    if (controlledSection && controlledSection !== section) setSection(controlledSection);
  }, [controlledSection, section]);

  useEffect(() => { setWsDraft(workspace); }, [workspace]);

  const load = useCallback(async () => {
    try {
      const [{ config }, h] = await Promise.all([
        api.getConfig(),
        api.health().catch(() => null),
      ]);
      setCfg(config as PublicConfig);
      if (h) setHealth(h as typeof health);
      setError(null);
    } catch (e) {
      setError(userMessage(e));
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const savePatch = async (patch: Record<string, unknown>, okMsg = 'Saved') => {
    setSaving(true);
    setError(null);
    try {
      const r = await api.updateConfig(patch);
      setCfg(r.config as PublicConfig);
      if (typeof (r.config as PublicConfig)?.llm?.model === 'string') {
        onModelChange((r.config as PublicConfig).llm.model);
      }
      setFlash(okMsg);
      setTimeout(() => setFlash(null), 1600);
      void refresh();
    } catch (e) {
      setError(userMessage(e));
    } finally {
      setSaving(false);
    }
  };

  const activeMeta = useMemo(() => SECTIONS.find((s) => s.id === section)!, [section]);

  return (
    <div className="settings-layout">
      <nav className="settings-nav" aria-label="Settings sections">
        {SECTIONS.map((s) => (
          <button
            key={s.id}
            type="button"
            className={`settings-nav-item ${section === s.id ? 'active' : ''}`}
            onClick={() => go(s.id)}
            aria-current={section === s.id ? 'page' : undefined}
          >
            <span className="settings-nav-title">{s.title}</span>
            <span className="settings-nav-blurb">{s.blurb}</span>
          </button>
        ))}
      </nav>

      <div className="settings-main">
        <div className="settings-head">
          <h2>{activeMeta.title}</h2>
          <p>{activeMeta.blurb}</p>
        </div>

        {error && <Alert variant="warning" className="settings-alert">{error}</Alert>}
        {flash && <Alert variant="success" className="settings-alert">{flash}</Alert>}

        {section === 'model' && cfg && (
          <ModelSection
            cfg={cfg}
            model={model}
            models={models}
            saving={saving}
            health={health}
            onRefreshModels={() => { fetchModels(); void load(); }}
            onSaveModel={async (m) => {
              setSaving(true);
              setError(null);
              try {
                const r = await api.setModel(m);
                onModelChange(m);
                onContextLength?.(typeof r.context_length === 'number' ? r.context_length : null);
                setCfg((c) => (c ? { ...c, llm: { ...c.llm, model: m } } : c));
                setFlash('Model updated');
                setTimeout(() => setFlash(null), 1600);
              } catch (e) {
                setError(userMessage(e));
              } finally {
                setSaving(false);
              }
            }}
            onSaveLlm={(llm) => void savePatch({ llm }, 'Model settings saved')}
          />
        )}

        {section === 'appearance' && (
          <AppearanceSection appearance={appearance} />
        )}

        {section === 'tools' && cfg && (
          <ToolsSection
            gates={cfg.gates}
            envelope={cfg.envelope}
            agentTools={cfg.tools}
            toolPrefs={toolPrefs}
            saving={saving}
            onToggleGate={(key, v) => void savePatch({ gates: { ...cfg.gates, [key]: v } })}
            onSaveEnvelope={(envelope) => void savePatch({ envelope }, 'Limits saved')}
            onSaveTools={(tools) => void savePatch({ tools }, 'Agent tools saved')}
            onToolPref={(patch) => setToolPrefs(patch)}
          />
        )}

        {section === 'agents' && (
          <AgentsSection onFlash={setFlash} onError={setError} />
        )}

        {section === 'mcp' && cfg && (
          <McpSection
            servers={cfg.mcp?.servers || []}
            saving={saving}
            onSave={(servers) => void savePatch({ mcp: { servers } }, 'MCP servers saved')}
          />
        )}

        {section === 'workspace' && (
          <WorkspaceSection
            workspace={workspace}
            wsDraft={wsDraft}
            setWsDraft={setWsDraft}
            cfg={cfg}
            saving={saving}
            onApply={async () => {
              setSaving(true);
              try {
                await api.setWorkspace(wsDraft);
                onWorkspaceChange(wsDraft);
                fetchWorkspace();
                await load();
                setFlash('Folder updated');
                setTimeout(() => setFlash(null), 1600);
                void refresh();
              } catch (e) {
                setError(userMessage(e));
              } finally {
                setSaving(false);
              }
            }}
            onReload={async () => {
              setSaving(true);
              try {
                await api.reload();
                fetchModels();
                fetchWorkspace();
                await load();
                setFlash('Config reloaded');
                setTimeout(() => setFlash(null), 1600);
                void refresh();
              } catch (e) {
                setError(userMessage(e));
              } finally {
                setSaving(false);
              }
            }}
          />
        )}

        {section === 'safety' && cfg && (
          <SafetySection
            security={cfg.security}
            saving={saving}
            onToggle={(key, v) => void savePatch({ security: { ...cfg.security, [key]: v } })}
          />
        )}

        {section === 'about' && (
          <AboutSection health={health} cfg={cfg} onRefresh={() => void load()} />
        )}

        {!cfg && section !== 'appearance' && section !== 'about' && (
          <div className="muted small settings-loading">Loading settings…</div>
        )}
      </div>
    </div>
  );
}

function ModelSection({
  cfg, model, models, saving, health, onRefreshModels, onSaveModel, onSaveLlm,
}: {
  cfg: PublicConfig;
  model: string;
  models: string[];
  saving: boolean;
  health: { llm_reachable?: boolean; llm_detail?: string } | null;
  onRefreshModels: () => void;
  onSaveModel: (m: string) => void;
  onSaveLlm: (llm: PublicConfig['llm']) => void;
}) {
  const [draft, setDraft] = useState(cfg.llm);
  useEffect(() => { setDraft(cfg.llm); }, [cfg.llm]);

  return (
    <div className="settings-stack">
      <Card>
        <CardHead><h3>Active model</h3></CardHead>
        <CardBody className="stack gap">
          <div className="settings-field">
            <label htmlFor="settings-model">Model</label>
            <div className="row gap-sm">
              <Select
                id="settings-model"
                value={model}
                onChange={(e) => onSaveModel(e.target.value)}
                disabled={saving || !models.length}
                className="grow"
              >
                {!models.includes(model) && model && <option value={model}>{model}</option>}
                {models.map((m) => <option key={m} value={m}>{m}</option>)}
              </Select>
              <Button size="sm" variant="ghost" onClick={onRefreshModels}>Refresh list</Button>
            </div>
            <p className="settings-hint">
              {health?.llm_reachable === false
                ? `Server unreachable${health.llm_detail ? ` — ${health.llm_detail}` : ''}`
                : health?.llm_reachable
                  ? 'Server reachable'
                  : 'Checking connection…'}
            </p>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHead><h3>Connection</h3></CardHead>
        <CardBody className="stack gap">
          <div className="settings-field">
            <label htmlFor="llm-endpoint">Endpoint</label>
            <Input id="llm-endpoint" value={draft.endpoint} onChange={(e) => setDraft({ ...draft, endpoint: e.target.value })} placeholder="http://localhost:11434" />
          </div>
          <div className="settings-grid-2">
            <div className="settings-field">
              <label htmlFor="llm-timeout">Timeout (seconds)</label>
              <Input id="llm-timeout" type="number" min={1} max={3600} value={draft.timeout_s} onChange={(e) => setDraft({ ...draft, timeout_s: Number(e.target.value) || 120 })} />
            </div>
            <div className="settings-field">
              <label htmlFor="llm-retries">Retries</label>
              <Input id="llm-retries" type="number" min={0} max={10} value={draft.retries} onChange={(e) => setDraft({ ...draft, retries: Number(e.target.value) || 0 })} />
            </div>
          </div>
          <div className="settings-field">
            <label htmlFor="llm-health">Health path</label>
            <Input id="llm-health" value={draft.health_path} onChange={(e) => setDraft({ ...draft, health_path: e.target.value })} placeholder="/api/tags" />
          </div>
          <div className="row">
            <Button variant="primary" disabled={saving} onClick={() => onSaveLlm({ ...draft, model: model || draft.model })}>
              Save connection
            </Button>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

function AppearanceSection({ appearance }: { appearance: ReturnType<typeof useAppearance> }) {
  return (
    <div className="settings-stack">
      <Card>
        <CardHead><h3>Theme</h3></CardHead>
        <CardBody>
          <div className="settings-choice-row" role="radiogroup" aria-label="Theme">
            {([
              { id: 'dark' as Theme, label: 'Dark', desc: 'Default for long sessions' },
              { id: 'light' as Theme, label: 'Light', desc: 'Brighter surfaces' },
            ]).map((opt) => (
              <button
                key={opt.id}
                type="button"
                role="radio"
                aria-checked={appearance.theme === opt.id}
                className={`settings-choice ${appearance.theme === opt.id ? 'active' : ''}`}
                onClick={() => appearance.setTheme(opt.id)}
              >
                <strong>{opt.label}</strong>
                <span>{opt.desc}</span>
              </button>
            ))}
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHead><h3>Density</h3></CardHead>
        <CardBody>
          <div className="settings-choice-row" role="radiogroup" aria-label="Density">
            {([
              { id: 'comfortable' as Density, label: 'Comfortable', desc: 'More padding' },
              { id: 'compact' as Density, label: 'Compact', desc: 'Tighter lists and chrome' },
            ]).map((opt) => (
              <button
                key={opt.id}
                type="button"
                role="radio"
                aria-checked={appearance.density === opt.id}
                className={`settings-choice ${appearance.density === opt.id ? 'active' : ''}`}
                onClick={() => appearance.setDensity(opt.id)}
              >
                <strong>{opt.label}</strong>
                <span>{opt.desc}</span>
              </button>
            ))}
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardBody>
          <Switch
            id="reduce-motion"
            checked={appearance.reduceMotion}
            onChange={appearance.setReduceMotion}
            label="Reduce motion"
            description="Turn off non-essential animations"
          />
        </CardBody>
      </Card>
    </div>
  );
}

function AgentsSection({
  onFlash, onError,
}: {
  onFlash: (s: string | null) => void;
  onError: (s: string | null) => void;
}) {
  const [agents, setAgents] = useState<import('../api').AgentSpec[]>([]);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState('');
  const [role, setRole] = useState('worker');
  const [summary, setSummary] = useState('');
  const [groups, setGroups] = useState('files,search');
  const [addon, setAddon] = useState('');

  const reload = useCallback(async () => {
    try {
      const r = await api.listAgents(true);
      setAgents(r.agents || []);
      onError(null);
    } catch (e) {
      onError(userMessage(e));
    }
  }, [onError]);

  useEffect(() => { void reload(); }, [reload]);

  const create = async () => {
    setBusy(true);
    try {
      const g = groups.split(/[,\s]+/).map((x) => x.trim()).filter(Boolean);
      await api.createAgent({
        name,
        role,
        summary,
        system_addon: addon,
        groups: g.length ? g : null,
      });
      setName('');
      setSummary('');
      setAddon('');
      onFlash('Agent created');
      setTimeout(() => onFlash(null), 1600);
      await reload();
    } catch (e) {
      onError(userMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="settings-stack">
      <Card>
        <CardHead>New agent</CardHead>
        <CardBody>
          <p className="small muted" style={{ marginBottom: 'var(--space-3)' }}>
            Specs are CRUD resources. Children inherit parent tools/gates/budgets (can only tighten).
            Judge roles created by the main agent stay pending until you approve them here.
          </p>
          <div style={{ display: 'grid', gap: 'var(--space-2)', maxWidth: 520 }}>
            <label>
              Name
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="repo-reader" />
            </label>
            <label>
              Role
              <Select value={role} onChange={(e) => setRole(e.target.value)}>
                {['worker', 'planner', 'reviewer', 'auditor', 'evaluator', 'integrator'].map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </Select>
            </label>
            <label>
              Summary
              <Input value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="What it specializes in" />
            </label>
            <label>
              Groups (comma)
              <Input value={groups} onChange={(e) => setGroups(e.target.value)} placeholder="files,search" />
            </label>
            <label>
              System addon
              <Input value={addon} onChange={(e) => setAddon(e.target.value)} placeholder="Extra instructions" />
            </label>
            <Button disabled={busy || !name.trim()} onClick={() => void create()}>Create</Button>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHead>Registry ({agents.filter((a) => a.status !== 'archived').length} active)</CardHead>
        <CardBody>
          {agents.length === 0 && <p className="small muted">No agents yet — create one or let the main agent use create_agent.</p>}
          <div className="col-stack">
            {agents.map((a) => (
              <div
                key={a.id}
                className="agent-row"
                style={{ opacity: a.status === 'archived' ? 0.55 : 1 }}
              >
                <div className="agent-row-body">
                  <div style={{ fontWeight: 600 }}>{a.name} <span className="mono muted" style={{ fontWeight: 400 }}>{a.role}</span></div>
                  <div className="small muted mono">{a.id} · {a.status} · {a.created_by || '—'}</div>
                  {a.summary && <div className="small" style={{ marginTop: 4 }}>{a.summary}</div>}
                  {a.groups && <div className="mono small muted">groups: {(a.groups || []).join(', ') || '—'}</div>}
                </div>
                <div className="agent-row-actions">
                  {a.status === 'pending' && (
                    <Button size="sm" onClick={() => void api.approveAgent(a.id).then(reload).catch((e) => onError(userMessage(e)))}>
                      Approve
                    </Button>
                  )}
                  {a.status !== 'archived' && (
                    <Button size="sm" variant="ghost" onClick={() => void api.archiveAgent(a.id).then(reload).catch((e) => onError(userMessage(e)))}>
                      Archive
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

function ToolsSection({
  gates, envelope, agentTools, toolPrefs, saving, onToggleGate, onSaveEnvelope, onSaveTools, onToolPref,
}: {
  gates: Record<string, boolean>;
  envelope: PublicConfig['envelope'];
  agentTools?: AgentToolsConfig;
  toolPrefs: ReturnType<typeof getToolPrefs>;
  saving: boolean;
  onToggleGate: (k: string, v: boolean) => void;
  onSaveEnvelope: (e: PublicConfig['envelope']) => void;
  onSaveTools: (t: AgentToolsConfig) => void;
  onToolPref: (p: Partial<ReturnType<typeof getToolPrefs>>) => void;
}) {
  const [envDraft, setEnvDraft] = useState(envelope);
  const [catalog, setCatalog] = useState<ToolCatalog | null>(null);
  const [openGroup, setOpenGroup] = useState<string | null>('files');
  const [draft, setDraft] = useState<AgentToolsConfig>(() => agentTools || {
    enabled: true,
    discovery: true,
    max_result_chars: 8000,
    max_activated: 8,
    groups: {},
    disabled: [],
    packs: {},
    pack_config: {},
    builtin_config: {},
    runtime: 'auto',
  });
  const [toolQuery, setToolQuery] = useState('');
  const [openPack, setOpenPack] = useState<string | null>(null);

  useEffect(() => { setEnvDraft(envelope); }, [envelope]);
  useEffect(() => {
    if (agentTools) setDraft({
      enabled: agentTools.enabled !== false,
      discovery: agentTools.discovery !== false,
      max_result_chars: agentTools.max_result_chars || 8000,
      max_activated: agentTools.max_activated || 8,
      groups: { ...(agentTools.groups || {}) },
      disabled: [...(agentTools.disabled || [])],
      packs: { ...(agentTools.packs || {}) },
      pack_config: { ...(agentTools.pack_config || {}) },
      builtin_config: { ...(agentTools.builtin_config || {}) },
      runtime: agentTools.runtime || 'auto',
    });
  }, [agentTools]);

  useEffect(() => {
    let cancelled = false;
    const load = async (attempt = 0) => {
      try {
        const r = await api.getTools();
        if (cancelled) return;
        const cat = r.tools as unknown as ToolCatalog;
        setCatalog(cat);
        // Seed pack_config draft from public field values (secrets stay as placeholders)
        setDraft((d) => {
          const pc = { ...(d.pack_config || {}) };
          for (const p of cat.packs || []) {
            if (!p.config_fields?.length) continue;
            const cur = { ...(pc[p.id] || {}) };
            for (const f of p.config_fields) {
              if (cur[f.key] === undefined && f.value !== undefined && f.value !== '') {
                cur[f.key] = f.value as string | number | boolean;
              }
            }
            pc[p.id] = cur;
          }
          const bc = { ...(d.builtin_config || {}) };
          for (const [tool, fields] of Object.entries(cat.builtin_configs || {})) {
            const cur = { ...(bc[tool] || {}) };
            for (const f of fields) {
              if (cur[f.key] === undefined && f.value !== undefined && f.value !== '') {
                cur[f.key] = f.value as string | number | boolean;
              }
            }
            bc[tool] = cur;
          }
          return { ...d, pack_config: pc, builtin_config: bc };
        });
      } catch {
        if (cancelled) return;
        if (attempt < 4) {
          window.setTimeout(() => { void load(attempt + 1); }, 350 * (attempt + 1));
        } else {
          setCatalog(null);
        }
      }
    };
    void load();
    return () => { cancelled = true; };
  }, [agentTools]);

  const disabledSet = useMemo(() => new Set(draft.disabled), [draft.disabled]);

  const toggleGroup = (id: string, on: boolean) => {
    setDraft((d) => ({ ...d, groups: { ...d.groups, [id]: on } }));
  };

  const toggleTool = (name: string, on: boolean) => {
    setDraft((d) => {
      const next = new Set(d.disabled);
      if (on) next.delete(name);
      else next.add(name);
      return { ...d, disabled: [...next] };
    });
  };

  const groups = (catalog?.groups || []).filter((g) => g.id !== 'discovery' && !g.id.startsWith('lc_') && g.id !== 'crewai');
  const packs = Array.isArray(catalog?.packs) ? catalog!.packs : [];
  const integ = catalog?.integrations || {};
  const q = toolQuery.trim().toLowerCase();

  const togglePack = (id: string, on: boolean) => {
    setDraft((d) => ({ ...d, packs: { ...(d.packs || {}), [id]: on } }));
    if (on) setOpenPack(id);
  };

  const setPackField = (packId: string, key: string, value: string | number | boolean) => {
    setDraft((d) => ({
      ...d,
      pack_config: {
        ...(d.pack_config || {}),
        [packId]: { ...((d.pack_config || {})[packId] || {}), [key]: value },
      },
    }));
  };

  const setBuiltinField = (tool: string, key: string, value: string | number | boolean) => {
    setDraft((d) => ({
      ...d,
      builtin_config: {
        ...(d.builtin_config || {}),
        [tool]: { ...((d.builtin_config || {})[tool] || {}), [key]: value },
      },
    }));
  };

  const fieldValue = (packId: string, f: ConfigField): string => {
    const stored = draft.pack_config?.[packId]?.[f.key];
    if (stored !== undefined && stored !== null) return String(stored);
    if (f.type === 'secret' && f.has_value) return '••••••••';
    return f.value !== undefined && f.value !== null ? String(f.value) : '';
  };

  return (
    <div className="settings-stack">
      <Card>
        <CardHead><h3>Agent tools</h3></CardHead>
        <CardBody className="stack gap-sm">
          <p className="settings-hint" style={{ marginTop: 0 }}>
            The model discovers tools on demand (search → activate → use) so prompts stay small.
            Turn groups on/off here; individual tools can be disabled inside each group.
          </p>
          <Switch
            id="tools-enabled"
            checked={draft.enabled}
            disabled={saving}
            onChange={(v) => setDraft((d) => ({ ...d, enabled: v }))}
            label="Enable agent tools"
            description="Let the model read files, search, run commands, and more"
          />
          <Switch
            id="tools-discovery"
            checked={draft.discovery}
            disabled={saving || !draft.enabled}
            onChange={(v) => setDraft((d) => ({ ...d, discovery: v }))}
            label="Discover tools as needed"
            description="Only load search/activate helpers at first; pull full schemas when needed"
          />
          <div className="settings-grid-2">
            <div className="settings-field">
              <label htmlFor="max-activated">Max tools active per turn</label>
              <Input
                id="max-activated"
                type="number"
                min={1}
                max={40}
                disabled={!draft.enabled}
                value={draft.max_activated}
                onChange={(e) => setDraft((d) => ({ ...d, max_activated: Number(e.target.value) || 1 }))}
              />
            </div>
            <div className="settings-field">
              <label htmlFor="max-result-chars">Max tool result size</label>
              <Input
                id="max-result-chars"
                type="number"
                min={500}
                max={100000}
                disabled={!draft.enabled}
                value={draft.max_result_chars}
                onChange={(e) => setDraft((d) => ({ ...d, max_result_chars: Number(e.target.value) || 500 }))}
              />
            </div>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHead>
          <h3>Tool groups</h3>
          <span className="head-meta">{groups.length} groups</span>
        </CardHead>
        <CardBody className="stack gap">
          <Input
            value={toolQuery}
            onChange={(e) => setToolQuery(e.target.value)}
            placeholder="Search tools…"
            aria-label="Search tools"
            disabled={!draft.enabled}
          />
          {groups.map((g) => {
            const groupOn = draft.groups[g.id] ?? g.enabled;
            const tools = g.tools.filter((t) => !q || `${t.name} ${t.summary}`.toLowerCase().includes(q));
            if (q && tools.length === 0) return null;
            const open = openGroup === g.id || !!q;
            return (
              <div key={g.id} className={`tool-group ${!groupOn ? 'off' : ''}`}>
                <div className="tool-group-head">
                  <Switch
                    id={`group-${g.id}`}
                    checked={groupOn}
                    disabled={saving || !draft.enabled}
                    onChange={(v) => toggleGroup(g.id, v)}
                    label={g.title}
                    description={g.blurb}
                  />
                  <button
                    type="button"
                    className="tool-group-toggle"
                    aria-expanded={open}
                    onClick={() => setOpenGroup(open && !q ? null : g.id)}
                  >
                    {tools.length} tools
                  </button>
                </div>
                {open && (
                  <div className="tool-group-body">
                    {tools.map((t) => {
                      const on = groupOn && !disabledSet.has(t.name);
                      return (
                        <label key={t.name} className="tool-row">
                          <input
                            type="checkbox"
                            checked={on}
                            disabled={saving || !draft.enabled || !groupOn}
                            onChange={(e) => toggleTool(t.name, e.target.checked)}
                          />
                          <span className="tool-row-copy">
                            <span className="mono tool-row-name">{t.name}</span>
                            <span className="tool-row-summary">{t.summary}</span>
                          </span>
                          {t.risk !== 'low' && <span className={`tool-risk ${t.risk}`}>{t.risk}</span>}
                        </label>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
          <Button variant="primary" disabled={saving || !catalog} onClick={() => onSaveTools(draft)}>Save agent tools</Button>
        </CardBody>
      </Card>

      <Card>
        <CardHead>
          <h3>LangChain / CrewAI packs</h3>
          <span className="head-meta">
            {[integ.langchain && 'LC', integ.langgraph && 'Graph', integ.crewai && 'Crew'].filter(Boolean).join(' · ') || 'not installed'}
          </span>
        </CardHead>
        <CardBody className="stack gap">
          <p className="settings-hint" style={{ marginTop: 0 }}>
            External ecosystems plug in as packs. Enable a pack here (or let the agent call{' '}
            <code className="mono">load_tool_pack</code>) — schemas stay out of context until loaded.
            Install with <code className="mono">pip install -e &quot;.[agent]&quot;</code>
            {` `}(+ <code className="mono">.[crewai]</code> for CrewAI).
          </p>
          {packs.length === 0 && (
            <div className="empty" style={{ padding: 'var(--space-3)' }}>
              <p className="small muted">Pack catalog unavailable — restart server after updating.</p>
            </div>
          )}
          {packs.map((p) => {
            const on = draft.packs?.[p.id] ?? p.enabled;
            const fields = p.config_fields || [];
            const expanded = openPack === p.id || (on && fields.some((f) => f.required));
            return (
              <div key={p.id} className={`tool-group ${!on ? 'off' : ''}`}>
                <div className="tool-group-head">
                  <Switch
                    id={`pack-${p.id}`}
                    checked={on}
                    disabled={saving || !draft.enabled}
                    onChange={(v) => togglePack(p.id, v)}
                    label={p.title}
                    description={
                      p.install_ok
                        ? `${p.blurb}${p.loaded ? ' · loaded' : ''}${p.needs_config ? ' · needs config' : ''}`
                        : `${p.blurb} · missing: ${(p.missing || []).join(', ') || 'deps'}`
                    }
                  />
                  <div className="row gap-sm" style={{ alignItems: 'center' }}>
                    {p.risk !== 'low' && <span className={`tool-risk ${p.risk}`}>{p.risk}</span>}
                    {fields.length > 0 && (
                      <button
                        type="button"
                        className="tool-group-toggle"
                        aria-expanded={expanded}
                        onClick={() => setOpenPack(expanded ? null : p.id)}
                      >
                        Config
                      </button>
                    )}
                  </div>
                </div>
                {expanded && fields.length > 0 && (
                  <div className="tool-group-body settings-grid-2">
                    {fields.map((f) => (
                      <div key={f.key} className="settings-field" style={f.type === 'json' || f.type === 'secret' ? { gridColumn: '1 / -1' } : undefined}>
                        <label htmlFor={`pack-${p.id}-${f.key}`}>
                          {f.label}{f.required ? ' *' : ''}
                          {f.env ? <span className="mono muted" style={{ marginLeft: 6, fontSize: 'var(--text-2xs)' }}>env:{f.env}</span> : null}
                        </label>
                        {f.type === 'boolean' ? (
                          <Switch
                            id={`pack-${p.id}-${f.key}`}
                            checked={!!(draft.pack_config?.[p.id]?.[f.key] ?? f.value)}
                            onChange={(v) => setPackField(p.id, f.key, v)}
                            label={f.desc || f.label}
                          />
                        ) : (
                          <Input
                            id={`pack-${p.id}-${f.key}`}
                            type={f.type === 'number' ? 'number' : f.type === 'secret' ? 'password' : 'text'}
                            placeholder={f.placeholder || (f.type === 'secret' ? '••••••••' : '')}
                            value={fieldValue(p.id, f)}
                            onChange={(e) => setPackField(
                              p.id,
                              f.key,
                              f.type === 'number' ? Number(e.target.value) || 0 : e.target.value,
                            )}
                            onFocus={(e) => {
                              if (f.type === 'secret' && String(e.target.value).startsWith('••')) {
                                setPackField(p.id, f.key, '');
                              }
                            }}
                          />
                        )}
                        {f.desc && f.type !== 'boolean' && <span className="settings-hint">{f.desc}</span>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
          <div className="settings-field">
            <label htmlFor="tools-runtime">Agent runtime</label>
            <Select
              id="tools-runtime"
              value={draft.runtime || 'auto'}
              disabled={!draft.enabled}
              onChange={(e) => setDraft((d) => ({ ...d, runtime: e.target.value as AgentToolsConfig['runtime'] }))}
            >
              <option value="auto">Auto (LangGraph if installed)</option>
              <option value="stdlib">Built-in loop</option>
              <option value="langgraph">LangGraph ToolNode</option>
            </Select>
          </div>
          <Button variant="primary" disabled={saving || !catalog} onClick={() => onSaveTools(draft)}>Save packs & config</Button>
        </CardBody>
      </Card>

      <Card>
        <CardHead><h3>Built-in tool defaults</h3></CardHead>
        <CardBody className="stack gap">
          <p className="settings-hint" style={{ marginTop: 0 }}>
            Defaults for native tools (timeouts, limits). Per-call args still override these.
          </p>
          {Object.entries(catalog?.builtin_configs || {}).map(([tool, fields]) => (
            <div key={tool} className="tool-group">
              <div className="mono tool-row-name" style={{ marginBottom: 6 }}>{tool}</div>
              <div className="settings-grid-2">
                {fields.map((f) => (
                  <div key={f.key} className="settings-field">
                    <label htmlFor={`bi-${tool}-${f.key}`}>{f.label}</label>
                    <Input
                      id={`bi-${tool}-${f.key}`}
                      type={f.type === 'number' ? 'number' : 'text'}
                      placeholder={f.placeholder || String(f.default ?? '')}
                      value={String(draft.builtin_config?.[tool]?.[f.key] ?? f.value ?? f.default ?? '')}
                      onChange={(e) => setBuiltinField(
                        tool,
                        f.key,
                        f.type === 'number' ? Number(e.target.value) || 0 : e.target.value,
                      )}
                    />
                    {f.desc && <span className="settings-hint">{f.desc}</span>}
                  </div>
                ))}
              </div>
            </div>
          ))}
          <Button variant="primary" disabled={saving || !catalog} onClick={() => onSaveTools(draft)}>Save built-in defaults</Button>
        </CardBody>
      </Card>

      <Card>
        <CardHead><h3>Chat helpers</h3></CardHead>
        <CardBody className="stack gap-sm">
          <Switch id="pref-slash" checked={toolPrefs.slashCommands} onChange={(v) => onToolPref({ slashCommands: v })} label="Slash commands" description="Type / to insert shortcuts like /add-task" />
          <Switch id="pref-mention" checked={toolPrefs.fileMentions} onChange={(v) => onToolPref({ fileMentions: v })} label="@ file mentions" description="Type @ to attach file paths" />
          <Switch id="pref-attach" checked={toolPrefs.attachFiles} onChange={(v) => onToolPref({ attachFiles: v })} label="File attach button" description="Show the paperclip next to the composer" />
          <Switch id="pref-hints" checked={toolPrefs.showShortcuts} onChange={(v) => onToolPref({ showShortcuts: v })} label="Shortcut hints" description="Show Enter / Shift+Enter tips under the composer" />
        </CardBody>
      </Card>

      <Card>
        <CardHead><h3>Automatic checks</h3></CardHead>
        <CardBody className="stack gap-sm">
          {Object.keys(GATE_META).map((key) => (
            <Switch
              key={key}
              id={`gate-${key}`}
              checked={!!gates[key]}
              disabled={saving}
              onChange={(v) => onToggleGate(key, v)}
              label={GATE_META[key].label}
              description={GATE_META[key].desc}
            />
          ))}
        </CardBody>
      </Card>

      <Card>
        <CardHead><h3>Work limits</h3></CardHead>
        <CardBody className="stack gap">
          <div className="settings-grid-2">
            <div className="settings-field">
              <label htmlFor="best-of-n">Tries per step</label>
              <Input id="best-of-n" type="number" min={1} max={20} value={envDraft.best_of_n} onChange={(e) => setEnvDraft({ ...envDraft, best_of_n: Number(e.target.value) || 1 })} />
            </div>
            <div className="settings-field">
              <label htmlFor="max-steps">Max tool steps per turn</label>
              <Input id="max-steps" type="number" min={1} max={200} value={envDraft.max_steps_per_task} onChange={(e) => setEnvDraft({ ...envDraft, max_steps_per_task: Number(e.target.value) || 1 })} />
            </div>
            <div className="settings-field">
              <label htmlFor="max-lines">Max lines per micro-task</label>
              <Input id="max-lines" type="number" min={1} max={1000} value={envDraft.max_microtask_lines} onChange={(e) => setEnvDraft({ ...envDraft, max_microtask_lines: Number(e.target.value) || 1 })} />
            </div>
            <div className="settings-field">
              <label htmlFor="stall">Stop after stalled tries</label>
              <Input id="stall" type="number" min={1} max={50} value={envDraft.early_abort_stall} onChange={(e) => setEnvDraft({ ...envDraft, early_abort_stall: Number(e.target.value) || 1 })} />
            </div>
          </div>
          <Button variant="primary" disabled={saving} onClick={() => onSaveEnvelope(envDraft)}>Save limits</Button>
        </CardBody>
      </Card>
    </div>
  );
}

function emptyServer(): McpServer {
  return {
    id: `mcp_${Math.random().toString(36).slice(2, 10)}`,
    name: '',
    transport: 'sse',
    url: 'http://127.0.0.1:3000/sse',
    enabled: true,
  };
}

function McpSection({
  servers, saving, onSave,
}: {
  servers: McpServer[];
  saving: boolean;
  onSave: (servers: McpServer[]) => void;
}) {
  const [draft, setDraft] = useState<McpServer[]>(servers);
  useEffect(() => { setDraft(servers.map((s) => ({ ...s, id: s.id || `mcp_${Math.random().toString(36).slice(2, 10)}` }))); }, [servers]);

  const update = (idx: number, patch: Partial<McpServer>) => {
    setDraft((list) => list.map((s, i) => (i === idx ? { ...s, ...patch } : s)));
  };

  return (
    <div className="settings-stack">
      <Card>
        <CardHead>
          <h3>Servers</h3>
          <span className="head-meta">{draft.length} configured</span>
        </CardHead>
        <CardBody className="stack gap">
          <p className="settings-hint" style={{ marginTop: 0 }}>
            Add MCP servers SUPER can call for extra tools. Connection is stored in your config — the runtime uses them when available.
          </p>
          {draft.length === 0 && (
            <div className="empty" style={{ padding: 'var(--space-4)' }}>
              <p className="small muted">No MCP servers yet</p>
            </div>
          )}
          {draft.map((s, idx) => (
            <div key={s.id || idx} className="mcp-card">
              <div className="mcp-card-top">
                <Switch
                  checked={s.enabled !== false}
                  onChange={(v) => update(idx, { enabled: v })}
                  label={s.name || 'New server'}
                  description={s.transport === 'stdio' ? (s.command || 'stdio') : (s.url || 'no url')}
                />
                <Button size="sm" variant="ghost" onClick={() => setDraft((list) => list.filter((_, i) => i !== idx))}>Remove</Button>
              </div>
              <div className="settings-grid-2">
                <div className="settings-field">
                  <label>Name</label>
                  <Input value={s.name} onChange={(e) => update(idx, { name: e.target.value })} placeholder="filesystem" />
                </div>
                <div className="settings-field">
                  <label>Transport</label>
                  <Select
                    value={s.transport}
                    onChange={(e) => update(idx, { transport: e.target.value as McpServer['transport'] })}
                  >
                    <option value="sse">SSE</option>
                    <option value="http">HTTP</option>
                    <option value="stdio">stdio</option>
                  </Select>
                </div>
                {(s.transport === 'sse' || s.transport === 'http') && (
                  <div className="settings-field span-all">
                    <label>URL</label>
                    <Input value={s.url || ''} onChange={(e) => update(idx, { url: e.target.value })} placeholder="http://127.0.0.1:3000/sse" />
                  </div>
                )}
                {s.transport === 'stdio' && (
                  <>
                    <div className="settings-field">
                      <label>Command</label>
                      <Input value={s.command || ''} onChange={(e) => update(idx, { command: e.target.value })} placeholder="npx" />
                    </div>
                    <div className="settings-field">
                      <label>Args (space-separated)</label>
                      <Input
                        value={(s.args || []).join(' ')}
                        onChange={(e) => update(idx, { args: e.target.value.trim() ? e.target.value.trim().split(/\s+/) : [] })}
                        placeholder="-y @modelcontextprotocol/server-filesystem ."
                      />
                    </div>
                  </>
                )}
              </div>
            </div>
          ))}
          <div className="row gap-sm">
            <Button variant="secondary" onClick={() => setDraft((list) => [...list, emptyServer()])}>Add server</Button>
            <Button variant="primary" disabled={saving} onClick={() => onSave(draft.map(({ has_env: _h, ...rest }) => rest))}>Save servers</Button>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

function WorkspaceSection({
  workspace, wsDraft, setWsDraft, cfg, saving, onApply, onReload,
}: {
  workspace: string;
  wsDraft: string;
  setWsDraft: (v: string) => void;
  cfg: PublicConfig | null;
  saving: boolean;
  onApply: () => void;
  onReload: () => void;
}) {
  const [picking, setPicking] = useState(false);
  const [pickError, setPickError] = useState<string | null>(null);

  const browse = async () => {
    setPicking(true);
    setPickError(null);
    try {
      const res = await api.pickFolder(wsDraft || workspace || undefined);
      if (res.cancelled || !res.path) return;
      setWsDraft(res.path);
    } catch (e) {
      setPickError(userMessage(e));
    } finally {
      setPicking(false);
    }
  };

  return (
    <div className="settings-stack">
      <Card>
        <CardHead><h3>Working directory</h3></CardHead>
        <CardBody className="stack gap">
          <p className="settings-hint">
            Default cwd for tools and config. Absolute paths still reach the whole machine —
            this is not a sandbox.
          </p>
          <div className="settings-field">
            <label htmlFor="ws-path">Path</label>
            <div className="row gap-sm stretch">
              <Input
                id="ws-path"
                value={wsDraft}
                onChange={(e) => setWsDraft(e.target.value)}
                placeholder="/path/to/project"
                className="mono grow"
              />
              <Button variant="secondary" type="button" disabled={picking || saving} onClick={() => void browse()}>
                {picking ? 'Browsing…' : 'Browse…'}
              </Button>
            </div>
            <p className="settings-hint">Current: <span className="mono">{workspace || '—'}</span></p>
            {pickError && <Alert variant="warning">{pickError}</Alert>}
          </div>
          <div className="row gap-sm">
            <Button variant="primary" disabled={saving || !wsDraft.trim()} onClick={onApply}>Use this folder</Button>
            <Button variant="ghost" disabled={saving} onClick={onReload}>Reload config</Button>
          </div>
        </CardBody>
      </Card>
      <Card>
        <CardHead><h3>Files</h3></CardHead>
        <CardBody className="stack gap-sm">
          <div className="settings-kv"><span>Config</span><code>{cfg?.config_path || '— (defaults)'}</code></div>
          <div className="settings-kv"><span>State</span><code>{cfg?.state_dir || '—'}</code></div>
        </CardBody>
      </Card>
    </div>
  );
}

function SafetySection({
  security, saving, onToggle,
}: {
  security: Record<string, boolean>;
  saving: boolean;
  onToggle: (k: string, v: boolean) => void;
}) {
  return (
    <Card>
      <CardHead><h3>Safety checks</h3></CardHead>
      <CardBody className="stack gap-sm">
        {Object.keys(SECURITY_META).map((key) => (
          <Switch
            key={key}
            id={`sec-${key}`}
            checked={!!security[key]}
            disabled={saving}
            onChange={(v) => onToggle(key, v)}
            label={SECURITY_META[key].label}
            description={SECURITY_META[key].desc}
          />
        ))}
      </CardBody>
    </Card>
  );
}

function AboutSection({
  health, cfg, onRefresh,
}: {
  health: { ok?: boolean; model?: string; version?: string; llm_reachable?: boolean; llm_detail?: string } | null;
  cfg: PublicConfig | null;
  onRefresh: () => void;
}) {
  return (
    <div className="settings-stack">
      <Card>
        <CardHead><h3>SUPER</h3></CardHead>
        <CardBody className="stack gap-sm">
          <div className="settings-kv"><span>Version</span><code>{health?.version || '1.0'}</code></div>
          <div className="settings-kv"><span>Model</span><code>{health?.model || cfg?.llm?.model || '—'}</code></div>
          <div className="settings-kv">
            <span>LLM</span>
            <code style={{ color: health?.llm_reachable ? 'var(--green)' : 'var(--yellow)' }}>
              {health?.llm_reachable ? 'reachable' : health?.llm_detail || 'unknown'}
            </code>
          </div>
          <div className="settings-kv"><span>Folder</span><code>{cfg?.workspace || '—'}</code></div>
          <Button size="sm" variant="ghost" onClick={onRefresh} className="btn-self-start">Refresh status</Button>
        </CardBody>
      </Card>
    </div>
  );
}
