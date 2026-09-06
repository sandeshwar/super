import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, streamChat } from '../../../api';
import type { ChatMessage, GateInfo, SessionSummary, TaskNode } from '../../../types';
import { userMessage } from '../../../lib/errors';
import { shortId } from '../../../utils/format';

type ChatRouteOpts = {
  sessionId?: string | null;
  onSessionIdChange?: (id: string | null) => void;
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
  const [showSlash, setShowSlash] = useState(false);
  const [slashFilter, setSlashFilter] = useState('');
  const [showMention, setShowMention] = useState(false);
  const [mentionFilter, setMentionFilter] = useState('');
  const [mentionIndex, setMentionIndex] = useState(0);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState('');
  const [cost, setCost] = useState<{ prompt: number; completion: number; total: number } | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

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
    } catch {}
  }, []);

  useEffect(() => { void loadSessions(); void loadLeaf(); }, [loadSessions, loadLeaf]);
  useEffect(() => {
    const id = window.setInterval(() => { void loadLeaf(); }, 8000);
    return () => window.clearInterval(id);
  }, [loadLeaf]);

  useEffect(() => {
    if (!activeId) return;
    let cancelled = false;
    api.session(activeId)
      .then((s) => { if (!cancelled) setMessages(s.messages); })
      .catch((e) => {
        if (cancelled) return;
        const msg = userMessage(e).toLowerCase();
        if (msg.includes('no such session') || msg.includes('404')) {
          setActiveId(null);
          setMessages([]);
          void loadSessions();
          setError('Previous chat not found — started a new one. Just resend.');
        } else {
          setError(userMessage(e));
        }
      });
    return () => { cancelled = true; };
  }, [activeId, loadSessions]);

  useEffect(() => {
    if (activeId && sessions.length > 0 && !sessions.some((s) => s.id === activeId)) {
      setActiveId(null);
      setMessages([]);
    }
  }, [sessions, activeId]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, busy]);
  useEffect(() => { inputRef.current?.focus(); }, [activeId]);

  useEffect(() => {
    const h = () => void loadSessions();
    window.addEventListener('super-new-chat' as unknown as string, h as EventListener);
    return () => window.removeEventListener('super-new-chat' as unknown as string, h as EventListener);
  }, [loadSessions]);

  const filtered = useMemo(() => {
    if (!filter.trim()) return sessions;
    const q = filter.toLowerCase();
    return sessions.filter((s) => s.title.toLowerCase().includes(q) || s.id.toLowerCase().includes(q));
  }, [sessions, filter]);

  const activeMeta = useMemo(() => sessions.find((s) => s.id === activeId) ?? null, [sessions, activeId]);

  const tokenStats = useMemo(() => {
    const chars = messages.reduce((a, m) => a + m.content.length, 0) + (leafRendered?.length || 0);
    const prompt = Math.ceil(chars / 4);
    const completion = messages.filter((m) => m.role === 'assistant').reduce((a, m) => a + Math.ceil(m.content.length / 4), 0);
    const total = prompt + completion;
    const limit = 8000;
    return { prompt, completion, total, limit, pct: Math.min(100, Math.round((total / limit) * 100)) };
  }, [messages, leafRendered]);

  const send = useCallback(async (overrideText?: string) => {
    const text = (overrideText ?? input).trim();
    if (!text || busy) return;
    if (text.startsWith('/')) {
      const [cmd, ...rest] = text.split(' ');
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
        try { await fetch('/api/task', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${sessionStorage.getItem('super_token') || ''}` }, body: JSON.stringify({ title }) }); } catch {}
        setInput('');
        return;
      }
      if (cmd === '/spec-pin') {
        const [id, ...acc] = rest;
        try {
          const r = await fetch('/api/spec/pin', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${sessionStorage.getItem('super_token') || ''}` }, body: JSON.stringify({ id, acceptance: acc }) });
          const body = await r.json();
          setMessages((m) => [...m, { role: 'assistant', content: r.ok && body.ok ? `Spec pinned for ${id}: ${acc.length} check(s)` : `Spec pin failed: ${body.error || r.status}`, ts: new Date().toISOString() }]);
        } catch (e) { setMessages((m) => [...m, { role: 'assistant', content: `Spec pin failed: ${(e as Error).message}`, ts: new Date().toISOString() }]); }
        setInput('');
        return;
      }
    }
    setError(null);
    setBusy(true);
    setInput('');
    setShowSlash(false);
    setShowMention(false);
    const startChars = text.length;
    setMessages((m) => [...m, { role: 'user', content: text, ts: new Date().toISOString() }]);
    let acc = '';
    setMessages((m) => [...m, { role: 'assistant', content: '', ts: new Date().toISOString() }]);
    const ac = new AbortController();
    abortRef.current = ac;
    const attempt = async (sid: string | null): Promise<{ session_id: string; gate: GateInfo }> => {
      return streamChat(sid, text, (d) => {
        if (ac.signal.aborted) return;
        acc += d;
        setMessages((m) => { const c = [...m]; c[c.length - 1] = { ...c[c.length - 1], content: acc }; return c; });
      });
    };
    try {
      let res: { session_id: string; gate: GateInfo };
      try {
        res = await attempt(activeId);
      } catch (e) {
        const msg = (e as Error).message?.toLowerCase() ?? '';
        const isStale = msg.includes('no such session') || (e instanceof Error && (e as unknown as { status?: number }).status === 404);
        if (isStale && activeId) {
          setActiveId(null);
          acc = '';
          setMessages((m) => { const c = [...m]; c[c.length - 1] = { ...c[c.length - 1], content: '' }; return c; });
          res = await attempt(null);
        } else {
          throw e;
        }
      }
      setMessages((m) => { const c = [...m]; c[c.length - 1] = { ...c[c.length - 1], content: acc, gate: res.gate }; return c; });
      if (!activeId) setActiveId(res.session_id);
      await loadSessions();
      await loadLeaf();
      setCost({ prompt: Math.ceil((startChars + (leafRendered?.length || 0)) / 4), completion: Math.ceil(acc.length / 4), total: Math.ceil((startChars + acc.length + (leafRendered?.length || 0)) / 4) });
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        setError(userMessage(e));
        setMessages((m) => m.slice(0, -1));
      }
    } finally {
      setBusy(false);
      abortRef.current = null;
      window.setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [input, busy, activeId, loadSessions, loadLeaf, leafRendered, activeMeta, messages]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setBusy(false);
  }, []);

  const regenerate = useCallback(async (idx: number) => {
    const userIdx = idx - 1;
    if (userIdx < 0 || messages[userIdx]?.role !== 'user') return;
    const prompt = messages[userIdx].content;
    setMessages((m) => m.slice(0, userIdx + 1));
    await send(prompt);
  }, [messages, send]);

  const editAndResend = useCallback(async (idx: number) => {
    if (editingIdx !== idx) { setEditingIdx(idx); setEditDraft(messages[idx].content); return; }
    const newContent = editDraft.trim();
    if (!newContent || !activeId) { setEditingIdx(null); return; }
    try {
      await api.editMessage(activeId, idx, newContent);
      const s = await api.session(activeId);
      setMessages(s.messages);
      setEditingIdx(null);
      await send(newContent);
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
  }, [activeId, activeMeta, loadSessions]);

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
      setActiveId(id);
      setMessages([]);
      setCost(null);
    } catch (e) { setError(userMessage(e)); }
  }, [loadSessions]);

  const deleteChat = useCallback(async (id: string) => {
    try {
      setError(null);
      await api.deleteSession(id);
      if (activeId === id) {
        setActiveId(null);
        setMessages([]);
      }
      await loadSessions();
    } catch (e) { setError(userMessage(e)); }
  }, [activeId, loadSessions]);

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
      const f = v.slice(at + 1).split(' ')[0].toLowerCase();
      setMentionFilter(f);
      setShowMention(true);
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
  };

  return {
    sessions, filtered, activeId, setActiveId, messages, input, setInput, busy, error, setError, filter, setFilter,
    isRenaming, leaf, leafRendered, showSlash, slashFilter, showMention, mentionFilter, mentionIndex, setMentionIndex,
    editingIdx, setEditingIdx, editDraft, setEditDraft, cost, tokenStats, activeMeta, inputRef, bottomRef,
    loadSessions, loadLeaf, send, stop, regenerate, editAndResend, branchFrom, shareExport, newChat, deleteChat, renameChat,
    handleInputChange, handleFile, setShowSlash, setShowMention
  };
}
