import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, streamChat } from '../../../api';
import type { ChatMessage, ChildSpan, GateInfo, LlmStats, SessionSummary, TaskNode, ToolEvent } from '../../../types';

import { AbortError, ApiError, userMessage } from '../../../lib/errors';
import { shortId } from '../../../utils/format';

type ChatRouteOpts = {
  sessionId?: string | null;
  onSessionIdChange?: (id: string | null) => void;
  contextLength?: number | null;
};

type SendOpts = {
  skipUserAppend?: boolean;
  /** When true, do not push a local user bubble (already present). */
  reuseLocalUser?: boolean;
};

export function useChat(opts: ChatRouteOpts = {}) {
  const onSessionIdChange = opts.onSessionIdChange;
  const controlled = onSessionIdChange !== undefined;
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [internalId, setInternalId] = useState<string | null>(opts.sessionId ?? null);
  const activeId = controlled ? (opts.sessionId ?? null) : internalId;
  const setActiveId = useCallback((id: string | null) => {
    if (controlled) onSessionIdChange?.(id);
    else setInternalId(id);
  }, [controlled, onSessionIdChange]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState('');
  const [isRenaming, setIsRenaming] = useState(false);
  const [leaf, setLeaf] = useState<TaskNode | null>(null);
  const [leafRendered, setLeafRendered] = useState('');
  const [mentionPaths, setMentionPaths] = useState<string[]>([]);
  const [showSlash, setShowSlash] = useState(false);
  const [slashFilter, setSlashFilter] = useState('');
  const [showMention, setShowMention] = useState(false);
  const [mentionFilter, setMentionFilter] = useState('');
  const [mentionIndex, setMentionIndex] = useState(0);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState('');
  const [cost, setCost] = useState<{ prompt: number; completion: number; total: number } | null>(null);
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [llmStats, setLlmStats] = useState<LlmStats | null>(null);
  const [agentView, setAgentView] = useState<{
    parentId: string;
    spanId: string;
    agentName: string;
    role?: string;
  } | null>(null);

  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const busyRef = useRef(false);

  const loadSessions = useCallback(async () => {
    try {
      const { sessions: list } = await api.sessions();
      setSessions(list.slice().sort((a, b) => (b.updated || '').localeCompare(a.updated || '')));
      return list;
    } catch (e) {
      setError(userMessage(e));
      return [];
    }
  }, []);

  const loadLeaf = useCallback(async () => {
    try {
      const r = await api.leaf();
      setLeaf(r.leaf);
      setLeafRendered(r.rendered);
    } catch { /* leaf optional */ }
  }, []);

  const loadMentionPaths = useCallback(async () => {
    try {
      const { tasks } = await api.tree();
      const seen = new Set<string>();
      const out: string[] = [];
      for (const t of tasks) {
        for (const f of t.files || []) {
          const p = String(f).trim();
          if (!p || seen.has(p)) continue;
          seen.add(p);
          out.push(p);
          if (out.length >= 80) break;
        }
        if (out.length >= 80) break;
      }
      setMentionPaths(out);
    } catch { /* optional */ }
  }, []);

  useEffect(() => { void loadSessions(); void loadLeaf(); void loadMentionPaths(); }, [loadSessions, loadLeaf, loadMentionPaths]);
  useEffect(() => {
    const id = window.setInterval(() => { void loadLeaf(); }, 8000);
    return () => window.clearInterval(id);
  }, [loadLeaf]);

  useEffect(() => {
    if (!activeId) {
      setMessages([]);
      setLlmStats(null);
      setAgentView(null);
      return;
    }
    let cancelled = false;
    api.session(activeId)
      .then((s) => {
        if (cancelled) return;
        setMessages(s.messages);
        const last = [...s.messages].reverse().find((m) => m.role === 'assistant');
        const stats = last?.gate?.agent?.llm_stats;
        setLlmStats(stats && typeof stats === 'object' ? stats : null);
        if (s.parent) {
          setAgentView({
            parentId: s.parent,
            spanId: s.span_id || activeId,
            agentName: s.title || 'agent',
          });
        } else {
          setAgentView(null);
        }
      })
      .catch((e) => {
        if (cancelled) return;
        const msg = userMessage(e).toLowerCase();
        if (msg.includes('no such session') || msg.includes('404') || (e instanceof ApiError && e.isNotFound)) {
          setActiveId(null);
          setAgentView(null);
          setMessages([]);
          void loadSessions();
          setError('Previous chat not found — started a new one. Just resend.');
        } else {
          setError(userMessage(e));
        }
      });
    return () => { cancelled = true; };
  }, [activeId, loadSessions, setActiveId]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, busy]);
  useEffect(() => { inputRef.current?.focus(); }, [activeId]);

  const filtered = useMemo(() => {
    if (!filter.trim()) return sessions;
    const q = filter.toLowerCase();
    return sessions.filter((s) => s.title.toLowerCase().includes(q) || s.id.toLowerCase().includes(q));
  }, [sessions, filter]);

  const activeMeta = useMemo(() => {
    if (agentView && activeId) {
      return {
        id: activeId,
        title: agentView.agentName,
        updated: '',
        n: messages.length,
        kind: 'agent',
        parent: agentView.parentId,
      } satisfies SessionSummary;
    }
    return sessions.find((s) => s.id === activeId) ?? null;
  }, [sessions, activeId, agentView, messages.length]);

  const selectSession = useCallback((id: string) => {
    setAgentView(null);
    setActiveId(id);
  }, [setActiveId]);

  const selectSpan = useCallback((parentId: string, span: ChildSpan) => {
    const childId = span.child_session_id;
    if (!childId) {
      setError('Sub-agent transcript not available for this run');
      return;
    }
    setAgentView({
      parentId,
      spanId: span.span_id,
      agentName: span.agent_name || 'agent',
      role: span.role,
    });
    setActiveId(childId);
  }, [setActiveId]);

  const backToParent = useCallback(() => {
    if (agentView?.parentId) {
      const pid = agentView.parentId;
      setAgentView(null);
      setActiveId(pid);
    }
  }, [agentView, setActiveId]);

  const tokenStats = useMemo(() => {
    const chars = messages.reduce((a, m) => a + m.content.length, 0) + (leafRendered?.length || 0);
    const prompt = Math.ceil(chars / 4);
    const completion = messages.filter((m) => m.role === 'assistant').reduce((a, m) => a + Math.ceil(m.content.length / 4), 0);
    const total = prompt + completion;
    const limit = typeof opts.contextLength === 'number' && opts.contextLength > 0 ? opts.contextLength : null;
    const pct = limit ? Math.min(100, Math.round((total / limit) * 100)) : null;
    return { prompt, completion, total, limit, pct };
  }, [messages, leafRendered, opts.contextLength]);

  const systemNote = useCallback((content: string) => {
    setMessages((m) => [...m, { role: 'assistant', content, ts: new Date().toISOString() }]);
  }, []);

  const send = useCallback(async (overrideText?: string, sendOpts: SendOpts = {}) => {
    const text = (overrideText ?? input).trim();
    if (!text || busyRef.current) return;
    if (agentView) {
      setError('Sub-agent chats are read-only — switch back to the parent chat to continue.');
      return;
    }
    if (text.startsWith('/')) {
      const [cmd, ...rest] = text.split(/\s+/);
      if (cmd === '/clear') { setMessages([]); setInput(''); return; }
      if (cmd === '/export') {
        const md = messages.map((m) => `**${m.role}**: ${m.content}`).join('\n\n');
        const blob = new Blob([`# ${activeMeta?.title || 'Chat'}\n\n${md}`], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href = url; a.download = `${activeMeta?.title || 'chat'}.md`; a.click(); URL.revokeObjectURL(url);
        setInput('');
        return;
      }
      if (cmd === '/add-task') {
        const title = rest.join(' ').replace(/--done.*/, '').trim() || 'Untitled';
        try {
          const r = await api.addTask(title);
          systemNote(`Added task #${r.id}: ${title}`);
          window.dispatchEvent(new Event('super-refresh'));
        } catch (e) {
          systemNote(`Could not add task: ${userMessage(e)}`);
        }
        setInput('');
        return;
      }
      if (cmd === '/spec-pin') {
        const [id, ...acc] = rest;
        if (!id) { systemNote('Usage: /spec-pin <task-id> <acceptance…>'); setInput(''); return; }
        try {
          await api.pinSpec(id, acc.length ? acc : ['done']);
          systemNote(`Pinned checks for ${id}: ${acc.length || 1} item(s)`);
        } catch (e) {
          systemNote(`Spec pin failed: ${userMessage(e)}`);
        }
        setInput('');
        return;
      }
      if (cmd === '/prove') {
        const [id, ...proofParts] = rest;
        const proof = proofParts.join(' ').trim();
        if (!id || !proof) { systemNote('Usage: /prove <task-id> <proof note>'); setInput(''); return; }
        try {
          await api.prove(id, proof);
          systemNote(`Proof attached to ${id}.`);
          window.dispatchEvent(new Event('super-refresh'));
        } catch (e) {
          systemNote(`Prove failed: ${userMessage(e)}`);
        }
        setInput('');
        return;
      }
    }

    setError(null);
    busyRef.current = true;
    setBusy(true);
    setInput('');
    setShowSlash(false);
    setShowMention(false);
    setLlmStats(null);
    const startChars = text.length;
    if (!sendOpts.reuseLocalUser) {
      setMessages((m) => [...m, { role: 'user', content: text, ts: new Date().toISOString() }]);
    }
    let acc = '';
    const toolEvents: ToolEvent[] = [];
    const childMap = new Map<string, ChildSpan>();
    const syncChildren = () => Array.from(childMap.values());
    const patchSessionSpans = (sid: string | null, spans: ChildSpan[]) => {
      if (!sid || !spans.length) return;
      setSessions((prev) => prev.map((s) => {
        if (s.id !== sid) return s;
        const byId = new Map((s.spans || []).map((x) => [x.span_id, x]));
        for (const sp of spans) byId.set(sp.span_id, sp);
        const merged = Array.from(byId.values());
        const running = merged.filter((x) => x.status === 'running');
        const rest = merged.filter((x) => x.status !== 'running');
        return { ...s, spans: [...running, ...rest].slice(0, 8) };
      }));
    };
    setMessages((m) => [...m, { role: 'assistant', content: '', ts: new Date().toISOString(), tools: [], children: [] }]);
    const ac = new AbortController();
    abortRef.current = ac;

    const attempt = async (sid: string | null) =>
      streamChat(sid, text, (d) => {
        if (ac.signal.aborted) return;
        acc += d;
        setMessages((m) => {
          const c = [...m];
          c[c.length - 1] = { ...c[c.length - 1], content: acc, tools: [...toolEvents], children: syncChildren() };
          return c;
        });
      }, {
        signal: ac.signal,
        skipUserAppend: sendOpts.skipUserAppend,
        onEvent: (ev) => {
          if (ac.signal.aborted) return;
          const stats = ev.llm_stats as LlmStats | undefined;
          if (stats && typeof stats === 'object') {
            setLlmStats(stats);
          }
          const call = ev.tool_call as { name?: string; arguments?: unknown } | undefined;
          const result = ev.tool_result as { name?: string; ok?: boolean; content?: string } | undefined;
          if (call?.name) {
            toolEvents.push({ kind: 'call', name: call.name, arguments: call.arguments });
            setMessages((m) => {
              const c = [...m];
              c[c.length - 1] = { ...c[c.length - 1], tools: [...toolEvents], children: syncChildren() };
              return c;
            });
          }
          if (result?.name) {
            toolEvents.push({ kind: 'result', name: result.name, ok: result.ok, content: result.content });
            setMessages((m) => {
              const c = [...m];
              c[c.length - 1] = { ...c[c.length - 1], tools: [...toolEvents], children: syncChildren() };
              return c;
            });
          }
          const child = ev.child_agent as ChildSpan | undefined;
          if (child?.span_id) {
            childMap.set(child.span_id, {
              ...childMap.get(child.span_id),
              ...child,
              summary: child.summary || childMap.get(child.span_id)?.summary || '',
            });
            const kids = syncChildren();
            setMessages((m) => {
              const c = [...m];
              c[c.length - 1] = { ...c[c.length - 1], children: kids, tools: [...toolEvents] };
              return c;
            });
            patchSessionSpans(sid || activeId, kids);
          }
        },
      });

    try {
      let res: { session_id: string; gate: GateInfo };
      try {
        res = await attempt(activeId);
      } catch (e) {
        const isStale =
          (e instanceof ApiError && e.isNotFound) ||
          userMessage(e).toLowerCase().includes('no such session');
        if (isStale && activeId && !sendOpts.skipUserAppend) {
          setActiveId(null);
          acc = '';
          setMessages((m) => {
            const c = [...m];
            c[c.length - 1] = { ...c[c.length - 1], content: '', tools: [], children: [] };
            return c;
          });
          res = await attempt(null);
        } else {
          throw e;
        }
      }
      setMessages((m) => {
        const c = [...m];
        c[c.length - 1] = {
          ...c[c.length - 1],
          content: acc,
          gate: res.gate,
          tools: [...toolEvents],
          children: syncChildren(),
        };
        return c;
      });
      const finalStats = res.gate?.agent?.llm_stats;
      if (finalStats) setLlmStats(finalStats);
      if (!activeId) setActiveId(res.session_id);
      // Unstick UI immediately — session refresh is non-critical.
      busyRef.current = false;
      setBusy(false);
      abortRef.current = null;
      void loadSessions();
      void loadLeaf();
      setCost({
        prompt: Math.ceil((startChars + (leafRendered?.length || 0)) / 4),
        completion: Math.ceil(acc.length / 4),
        total: Math.ceil((startChars + acc.length + (leafRendered?.length || 0)) / 4),
      });
    } catch (e) {
      if (e instanceof AbortError || (e as Error)?.name === 'AbortError') {
        setMessages((m) => {
          if (!m.length) return m;
          const last = m[m.length - 1];
          if (last.role === 'assistant' && !last.content.trim() && !(last.tools?.length)) {
            return m.slice(0, -1);
          }
          if (last.role === 'assistant') {
            const c = [...m];
            c[c.length - 1] = { ...last, content: last.content || '_(stopped)_' };
            return c;
          }
          return m;
        });
      } else {
        setError(userMessage(e));
        setMessages((m) => {
          if (!m.length) return m;
          // Drop empty assistant; keep user (server may already have it).
          const last = m[m.length - 1];
          if (last.role === 'assistant') return m.slice(0, -1);
          return m;
        });
      }
    } finally {
      busyRef.current = false;
      setBusy(false);
      abortRef.current = null;
      window.setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [input, activeId, agentView, loadSessions, loadLeaf, leafRendered, activeMeta, messages, setActiveId, systemNote]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const regenerate = useCallback(async (idx: number) => {
    const userIdx = idx - 1;
    if (userIdx < 0 || messages[userIdx]?.role !== 'user') return;
    const prompt = messages[userIdx].content;
    setMessages((m) => m.slice(0, userIdx + 1));
    if (activeId) {
      try {
        await api.editMessage(activeId, userIdx, prompt);
      } catch (e) {
        setError(userMessage(e));
        return;
      }
    }
    await send(prompt, { skipUserAppend: Boolean(activeId), reuseLocalUser: true });
  }, [messages, send, activeId]);

  const editAndResend = useCallback(async (idx: number) => {
    if (editingIdx !== idx) { setEditingIdx(idx); setEditDraft(messages[idx].content); return; }
    const newContent = editDraft.trim();
    if (!newContent || !activeId) { setEditingIdx(null); return; }
    try {
      await api.editMessage(activeId, idx, newContent);
      const s = await api.session(activeId);
      setMessages(s.messages);
      setEditingIdx(null);
      await send(newContent, { skipUserAppend: true, reuseLocalUser: true });
    } catch (e) { setError(userMessage(e)); }
  }, [editingIdx, editDraft, messages, activeId, send]);

  const branchFrom = useCallback(async (idx: number) => {
    if (!activeId) return;
    try {
      const r = await api.branchSession(activeId, idx, `Branch of ${activeMeta?.title || shortId(activeId, 6)}`);
      await loadSessions();
      setActiveId(r.id);
      const s = await api.session(r.id);
      setMessages(s.messages);
    } catch (e) { setError(userMessage(e)); }
  }, [activeId, activeMeta, loadSessions, setActiveId]);

  const shareExport = useCallback((fmt: 'md' | 'json') => {
    if (!messages.length) return;
    if (fmt === 'json') {
      const blob = new Blob([JSON.stringify({ title: activeMeta?.title, messages }, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = `${activeMeta?.title || 'chat'}.json`; a.click(); URL.revokeObjectURL(url);
    } else {
      const md = `# ${activeMeta?.title || 'Chat'}\n\n${messages.map((m) => `**${m.role}** (${m.ts}):\n${m.content}`).join('\n\n---\n\n')}`;
      const blob = new Blob([md], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = `${activeMeta?.title || 'chat'}.md`; a.click(); URL.revokeObjectURL(url);
    }
  }, [messages, activeMeta]);

  const newChat = useCallback(async () => {
    try {
      setError(null);
      const { id } = await api.createSession();
      await loadSessions();
      setAgentView(null);
      setActiveId(id);
      setMessages([]);
      setCost(null);
    } catch (e) { setError(userMessage(e)); }
  }, [loadSessions, setActiveId]);

  useEffect(() => {
    const h = () => { void newChat(); };
    window.addEventListener('super-new-chat' as unknown as string, h as EventListener);
    return () => window.removeEventListener('super-new-chat' as unknown as string, h as EventListener);
  }, [newChat]);

  useEffect(() => {
    const onRefresh = () => {
      void loadSessions();
      void loadLeaf();
      void loadMentionPaths();
    };
    window.addEventListener('super-refresh' as unknown as string, onRefresh as EventListener);
    return () => window.removeEventListener('super-refresh' as unknown as string, onRefresh as EventListener);
  }, [loadSessions, loadLeaf, loadMentionPaths]);

  const deleteChat = useCallback(async (id: string) => {
    try {
      setError(null);
      await api.deleteSession(id);
      setSelectedIds((prev) => {
        if (!prev.has(id)) return prev;
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
      if (activeId === id) {
        setActiveId(null);
        setMessages([]);
      }
      await loadSessions();
    } catch (e) { setError(userMessage(e)); }
  }, [activeId, loadSessions, setActiveId]);

  const toggleSelectMode = useCallback(() => {
    setSelectMode((v) => {
      if (v) setSelectedIds(new Set());
      return !v;
    });
  }, []);

  const toggleSelected = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const selectAllFiltered = useCallback(() => {
    setSelectedIds(new Set(filtered.map((s) => s.id)));
  }, [filtered]);

  const clearSelection = useCallback(() => setSelectedIds(new Set()), []);

  const deleteSelected = useCallback(async () => {
    const ids = [...selectedIds];
    if (!ids.length) return;
    try {
      setError(null);
      for (const id of ids) {
        await api.deleteSession(id);
      }
      if (activeId && selectedIds.has(activeId)) {
        setActiveId(null);
        setMessages([]);
      }
      setSelectedIds(new Set());
      setSelectMode(false);
      await loadSessions();
    } catch (e) { setError(userMessage(e)); }
  }, [selectedIds, activeId, loadSessions, setActiveId]);

  const renameChat = useCallback(async (id: string, newTitle: string | null) => {
    try {
      setIsRenaming(true);
      setError(null);
      await api.renameSession(id, newTitle);
      await loadSessions();
    } catch (e) { setError(userMessage(e)); } finally { setIsRenaming(false); }
  }, [loadSessions]);

  const handleInputChange = (v: string) => {
    setInput(v);
    if (v.startsWith('/')) {
      setShowSlash(true);
      setSlashFilter(v.slice(1).toLowerCase());
      setShowMention(false);
    } else if (v.includes('@')) {
      const at = v.lastIndexOf('@');
      const f = v.slice(at + 1).split(/\s/)[0].toLowerCase();
      setMentionFilter(f);
      setShowMention(true);
      setMentionIndex(0);
      setShowSlash(false);
    } else {
      setShowSlash(false);
      setShowMention(false);
    }
  };

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const txt = await f.text().catch(() => '');
    const snippet = txt.slice(0, 2000);
    setInput((prev) => `${prev}\n\n\`\`\`${f.name}\n${snippet}\n\`\`\``.trimStart());
    e.target.value = '';
  };

  return {
    sessions, filtered, activeId, setActiveId, messages, input, setInput, busy, error, setError, filter, setFilter,
    isRenaming, leaf, leafRendered, mentionPaths, showSlash, slashFilter, showMention, mentionFilter, mentionIndex, setMentionIndex,
    editingIdx, setEditingIdx, editDraft, setEditDraft, cost, tokenStats, activeMeta, inputRef, bottomRef,
    selectMode, selectedIds, toggleSelectMode, toggleSelected, selectAllFiltered, clearSelection, deleteSelected,
    llmStats,
    agentView,
    parentId: agentView?.parentId ?? null,
    activeSpanId: agentView?.spanId ?? null,
    selectSession, selectSpan, backToParent,
    loadSessions, loadLeaf, send, stop, regenerate, editAndResend, branchFrom, shareExport, newChat, deleteChat, renameChat,
    handleInputChange, handleFile, setShowSlash, setShowMention,
  };
}
