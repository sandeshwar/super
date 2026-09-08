import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, streamChat } from '../../../api';
import type { ApprovalRequest, ChatBlock, ChatMessage, ChildSpan, GateInfo, LlmStats, MediaPart, SessionSummary, ToolEvent, CanvasPart } from '../../../types';
import { mergeMedia } from '../MediaAlbum';
import { mergeCanvas } from '../CanvasPanel';

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
  const [sessionLoading, setSessionLoading] = useState(() => Boolean(opts.sessionId));
  const [filter, setFilter] = useState('');
  const [isRenaming, setIsRenaming] = useState(false);
  const [mentionPaths] = useState<string[]>([]);
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
  /** Bumps to invalidate a hung/stale in-tab stream when server already finished. */
  const sendGenRef = useRef(0);
  /** Local stream start — used so heal doesn't kill a send before `generating` flips. */
  const streamStartedAtRef = useRef(0);
  const sawGeneratingRef = useRef(false);
  const activeIdRef = useRef<string | null>(activeId);
  activeIdRef.current = activeId;
  /** After this, idle server + open local stream ⇒ take disk truth (new-chat race). */
  const HEAL_GRACE_MS = 12_000;

  /** True when an in-tab SSE should be abandoned for disk truth. */
  const shouldHealLocalStream = useCallback((generating: boolean) => {
    if (!abortRef.current) return false;
    if (generating) {
      sawGeneratingRef.current = true;
      return false;
    }
    if (sawGeneratingRef.current) return true;
    // Never observed generating (new chat before session bind, or finished <2s).
    // After grace, trust disk — otherwise Stop sticks forever on hung SSE.
    const started = streamStartedAtRef.current;
    return started > 0 && Date.now() - started >= HEAL_GRACE_MS;
  }, []);

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

  useEffect(() => { void loadSessions(); }, [loadSessions]);

  useEffect(() => {
    if (!activeId) {
      // Don't wipe optimistic bubbles mid-send (new chat / stale-session retry).
      if (!busyRef.current && !abortRef.current) {
        setMessages([]);
        setLlmStats(null);
      }
      setAgentView(null);
      if (!busyRef.current) {
        setBusy(false);
        busyRef.current = false;
      }
      setSessionLoading(false);
      return;
    }
    let cancelled = false;
    let pollTimer: number | null = null;
    setSessionLoading(true);

    const applySession = (s: Awaited<ReturnType<typeof api.session>>) => {
      const gen = Boolean(s.generating);
      const localStream = Boolean(abortRef.current);
      const heal = shouldHealLocalStream(gen);

      if (!localStream) {
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
      } else if (heal) {
        // Server finished while our SSE is hung/stale — take disk truth.
        sendGenRef.current += 1;
        const stale = abortRef.current;
        abortRef.current = null;
        setMessages(s.messages);
        const last = [...s.messages].reverse().find((m) => m.role === 'assistant');
        const stats = last?.gate?.agent?.llm_stats;
        setLlmStats(stats && typeof stats === 'object' ? stats : null);
        try { stale?.abort(); } catch { /* ignore */ }
      }
      // else: live local stream still starting or in flight — keep optimistic UI

      if (gen || (localStream && !heal)) {
        busyRef.current = true;
        setBusy(true);
      } else {
        busyRef.current = false;
        setBusy(false);
      }
      return gen;
    };

    const load = () =>
      api.session(activeId)
        .then((s) => {
          if (cancelled) return;
          const gen = applySession(s);
          setSessionLoading(false);
          if (gen && pollTimer == null) {
            pollTimer = window.setInterval(() => {
              void api.session(activeId)
                .then((next) => {
                  if (cancelled) return;
                  if (!applySession(next)) {
                    if (pollTimer != null) {
                      window.clearInterval(pollTimer);
                      pollTimer = null;
                    }
                    void loadSessions();
                  }
                })
                .catch(() => { /* keep polling */ });
            }, 1000);
          }
        })
        .catch((e) => {
          if (cancelled) return;
          setSessionLoading(false);
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

    void load();
    return () => {
      cancelled = true;
      if (pollTimer != null) window.clearInterval(pollTimer);
    };
  }, [activeId, loadSessions, setActiveId, shouldHealLocalStream]);

  // While Stop is showing, keep polling — heals hung SSE after server already finished.
  useEffect(() => {
    if (!busy) return;
    const tick = () => {
      const sid = activeIdRef.current;
      if (!sid) {
        // New chat: discover the in-flight (or just-finished) session so heal can sync.
        void api.sessions()
          .then(({ sessions: list }) => {
            const gen = list.find((s) => s.generating);
            if (gen) {
              sawGeneratingRef.current = true;
              setActiveId(gen.id);
              return;
            }
            if (!shouldHealLocalStream(false)) return;
            const newest = list[0];
            if (newest && newest.n >= 1) setActiveId(newest.id);
          })
          .catch(() => { /* ignore */ });
        return;
      }
      void api.session(sid)
        .then((s) => {
          const gen = Boolean(s.generating);
          if (gen) {
            sawGeneratingRef.current = true;
            if (!abortRef.current) setMessages(s.messages);
            return;
          }
          if (abortRef.current) {
            // Don't abort a brand-new send before the server marks generating.
            if (!shouldHealLocalStream(false)) return;
            sendGenRef.current += 1;
            const stale = abortRef.current;
            abortRef.current = null;
            try { stale.abort(); } catch { /* ignore */ }
          }
          setMessages(s.messages);
          busyRef.current = false;
          setBusy(false);
        })
        .catch(() => { /* ignore */ });
    };
    // Delay first tick so stream POST can register the run (immediate tick raced sends).
    const first = window.setTimeout(tick, 2000);
    const id = window.setInterval(tick, 1500);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(id);
    };
  }, [busy, activeId, setActiveId, shouldHealLocalStream]);

  useEffect(() => {
    const el = bottomRef.current?.closest('.message-list');
    if (!el) return;
    // Scroll the list only — scrollIntoView can thrash ancestors and restart enter animations.
    el.scrollTop = el.scrollHeight;
  }, [messages, busy]);
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
    const chars = messages.reduce((a, m) => a + m.content.length, 0);
    const prompt = Math.ceil(chars / 4);
    const completion = messages.filter((m) => m.role === 'assistant').reduce((a, m) => a + Math.ceil(m.content.length / 4), 0);
    const total = prompt + completion;
    const limit = typeof opts.contextLength === 'number' && opts.contextLength > 0 ? opts.contextLength : null;
    const pct = limit ? Math.min(100, Math.round((total / limit) * 100)) : null;
    return { prompt, completion, total, limit, pct };
  }, [messages, opts.contextLength]);

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
      const [cmd] = text.split(/\s+/);
      if (cmd === '/clear') { setMessages([]); setInput(''); return; }
      if (cmd === '/export') {
        const md = messages.map((m) => `**${m.role}**: ${m.content}`).join('\n\n');
        const blob = new Blob([`# ${activeMeta?.title || 'Chat'}\n\n${md}`], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href = url; a.download = `${activeMeta?.title || 'chat'}.md`; a.click(); URL.revokeObjectURL(url);
        setInput('');
        return;
      }
    }

    setError(null);
    busyRef.current = true;
    setBusy(true);
    streamStartedAtRef.current = Date.now();
    sawGeneratingRef.current = false;
    setInput('');
    setShowSlash(false);
    setShowMention(false);
    setLlmStats(null);
    const startChars = text.length;
    const runId = ++sendGenRef.current;
    if (!sendOpts.reuseLocalUser) {
      setMessages((m) => [...m, { role: 'user', content: text, ts: new Date().toISOString() }]);
    }
    let acc = '';
    const toolEvents: ToolEvent[] = [];
    const approvalEvents: ApprovalRequest[] = [];
    const childMap = new Map<string, ChildSpan>();
    const syncChildren = () => Array.from(childMap.values());
    const syncApprovals = () => [...approvalEvents];
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
    setMessages((m) => [...m, { role: 'assistant', content: '', thinking: '', thoughts: [], blocks: [], thinkingLive: false, media: [], canvas: [], ts: new Date().toISOString(), tools: [], children: [], approvals: [] }]);
    const ac = new AbortController();
    abortRef.current = ac;
    let thinkingAcc = '';
    let thoughtsAcc: string[] = [];
    let blocksAcc: ChatBlock[] = [];
    let thinkStep = -1;
    let textStep = -1;
    let thinkLive = false;
    let mediaAcc: MediaPart[] = [];
    let canvasAcc: CanvasPart[] = [];

    const syncTimeline = () => {
      thoughtsAcc = blocksAcc
        .filter((b): b is Extract<ChatBlock, { kind: 'thinking' }> => b.kind === 'thinking')
        .map((b) => b.text)
        .filter(Boolean);
      thinkingAcc = thoughtsAcc.join('\n\n');
      return {
        blocks: blocksAcc.map((b) => ({ ...b })),
        thoughts: [...thoughtsAcc],
        thinking: thinkingAcc,
        thinkingLive: thinkLive,
      };
    };

    const findBlock = (kind: 'thinking' | 'text', step: number) => {
      for (let i = blocksAcc.length - 1; i >= 0; i--) {
        const b = blocksAcc[i];
        if (b.kind === kind && b.step === step) return b as Extract<ChatBlock, { kind: 'thinking' | 'text' }>;
      }
      return null;
    };

    /** Prefer extending the trailing thinking card so consecutive thoughts stay one block. */
    const trailingThinking = () => {
      const last = blocksAcc[blocksAcc.length - 1];
      return last?.kind === 'thinking' ? last : null;
    };

    const appendToBlock = (kind: 'thinking' | 'text', step: number, delta: string) => {
      if (kind === 'thinking') {
        const trail = trailingThinking();
        if (trail) {
          trail.text += delta;
          trail.step = step;
          return trail;
        }
      }
      const existing = findBlock(kind, step);
      if (existing) {
        existing.text += delta;
        return existing;
      }
      const b: ChatBlock = kind === 'thinking'
        ? { kind: 'thinking', text: delta, step }
        : { kind: 'text', text: delta, step };
      blocksAcc.push(b);
      return b;
    };

    const setBlockText = (kind: 'thinking' | 'text', step: number, text: string) => {
      if (kind === 'thinking') {
        const trail = trailingThinking();
        if (trail) {
          if (trail.step === step) {
            trail.text = text;
          } else {
            const left = (trail.text || '').trimEnd();
            const right = text.trim();
            trail.text = left && right ? `${left}\n\n${right}` : (left || right);
            trail.step = step;
          }
          return trail;
        }
      }
      const existing = findBlock(kind, step);
      if (existing) {
        existing.text = text;
        return existing;
      }
      const b: ChatBlock = kind === 'thinking'
        ? { kind: 'thinking', text, step }
        : { kind: 'text', text, step };
      // Insert thinking before same-step text if text already exists
      if (kind === 'thinking') {
        const textIdx = blocksAcc.findIndex((x) => x.kind === 'text' && x.step === step);
        if (textIdx >= 0) {
          blocksAcc.splice(textIdx, 0, b);
          return b;
        }
      }
      blocksAcc.push(b);
      return b;
    };

    const patchLast = (extra: Partial<ChatMessage> = {}) => {
      setMessages((m) => {
        const c = [...m];
        c[c.length - 1] = {
          ...c[c.length - 1],
          content: acc,
          ...syncTimeline(),
          media: mediaAcc.length ? mediaAcc : c[c.length - 1].media,
          canvas: canvasAcc.length ? canvasAcc : c[c.length - 1].canvas,
          tools: [...toolEvents],
          children: syncChildren(),
          approvals: syncApprovals(),
          ...extra,
        };
        return c;
      });
    };

    const closeThought = () => {
      if (thinkLive) {
        thinkLive = false;
        patchLast({ thinkingLive: false });
      }
    };

    const attempt = async (sid: string | null) =>
      streamChat(sid, text, (_d) => {
        if (ac.signal.aborted) return;
        // Deltas are applied in onEvent (carry step). Ignore duplicate onDelta.
      }, {
        signal: ac.signal,
        skipUserAppend: sendOpts.skipUserAppend,
        onEvent: (ev) => {
          if (ac.signal.aborted) return;
          const boundSid = typeof ev.session_id === 'string' ? ev.session_id.trim() : '';
          if (boundSid && !activeIdRef.current) {
            setActiveId(boundSid);
            activeIdRef.current = boundSid;
          }
          const td = ev.thinking_delta;
          if (typeof td === 'string' && td) {
            const step = typeof ev.step === 'number' ? ev.step : Math.max(0, thinkStep);
            thinkStep = step;
            thinkLive = true;
            appendToBlock('thinking', step, td);
            patchLast(syncTimeline());
          }
          if (typeof ev.delta === 'string' && ev.delta) {
            const step = typeof ev.step === 'number' ? ev.step : Math.max(0, textStep, thinkStep, 0);
            textStep = step;
            thinkLive = false;
            acc += ev.delta;
            appendToBlock('text', step, ev.delta);
            patchLast(syncTimeline());
          }
          const tstep = ev.thinking_step as { index?: number; step?: number; content?: string } | undefined;
          if (tstep && typeof tstep.content === 'string' && tstep.content) {
            const step = typeof tstep.step === 'number' ? tstep.step : Math.max(0, thinkStep);
            thinkStep = step;
            thinkLive = false;
            setBlockText('thinking', step, tstep.content);
            patchLast(syncTimeline());
          }
          const textStepEv = ev.text_step as { step?: number; content?: string } | undefined;
          if (textStepEv && typeof textStepEv.content === 'string' && textStepEv.content) {
            const step = typeof textStepEv.step === 'number' ? textStepEv.step : Math.max(0, textStep);
            textStep = step;
            thinkLive = false;
            setBlockText('text', step, textStepEv.content);
            acc = blocksAcc
              .filter((x): x is Extract<ChatBlock, { kind: 'text' }> => x.kind === 'text')
              .map((x) => x.text)
              .join('\n\n');
            patchLast(syncTimeline());
          }
          if (Array.isArray(ev.blocks)) {
            blocksAcc = (ev.blocks as ChatBlock[]).filter((b) => b && typeof b === 'object' && b.kind);
            thinkLive = false;
            acc = blocksAcc
              .filter((x): x is Extract<ChatBlock, { kind: 'text' }> => x.kind === 'text')
              .map((x) => x.text)
              .join('\n\n');
            mediaAcc = mergeMedia(
              mediaAcc,
              ...blocksAcc
                .filter((x): x is Extract<ChatBlock, { kind: 'media' }> => x.kind === 'media')
                .map((x) => x.media),
            );
            patchLast(syncTimeline());
          } else if (Array.isArray(ev.thoughts) && blocksAcc.length === 0) {
            thoughtsAcc = (ev.thoughts as unknown[]).map((x) => String(x || '')).filter(Boolean);
            blocksAcc = thoughtsAcc.map((t, i) => ({ kind: 'thinking' as const, text: t, step: i }));
            thinkLive = false;
            patchLast(syncTimeline());
          }
          const stats = ev.llm_stats as LlmStats | undefined;
          if (stats && typeof stats === 'object') {
            setLlmStats((prev) => ({ ...(prev || {}), ...stats }));
          }
          const ap = ev.approval as ApprovalRequest | undefined;
          if (ap && ap.kind && ap.id != null) {
            if (!approvalEvents.some((x) => x.kind === ap.kind && x.id === ap.id)) {
              approvalEvents.push({ ...ap, status: ap.status || 'pending' });
              patchLast();
            }
          }
          const call = ev.tool_call as { name?: string; arguments?: unknown; step?: number } | undefined;
          const result = ev.tool_result as {
            name?: string;
            ok?: boolean;
            content?: string;
            media?: MediaPart[];
            canvas?: CanvasPart;
            step?: number;
          } | undefined;
          if (call?.name) {
            closeThought();
            toolEvents.push({ kind: 'call', name: call.name, arguments: call.arguments });
            patchLast();
          }
          if (result?.name) {
            const media = Array.isArray(result.media) ? result.media : undefined;
            const canvas = result.canvas && typeof result.canvas === 'object' ? result.canvas : undefined;
            toolEvents.push({
              kind: 'result',
              name: result.name,
              ok: result.ok,
              content: result.content,
              ...(media?.length ? { media } : {}),
              ...(canvas ? { canvas } : {}),
            });
            if (media?.length) {
              mediaAcc = mergeMedia(mediaAcc, media);
              const step = typeof result.step === 'number' ? result.step : Math.max(0, textStep, thinkStep, 0);
              blocksAcc.push({ kind: 'media', media, step, tool: result.name });
            }
            if (canvas) {
              canvasAcc = mergeCanvas(canvasAcc, canvas);
              const step = typeof result.step === 'number' ? result.step : Math.max(0, textStep, thinkStep, 0);
              blocksAcc.push({ kind: 'canvas', canvas, step, tool: result.name });
            }
            patchLast({ media: mediaAcc, canvas: canvasAcc });
          }
          const canvasEv = ev.canvas as CanvasPart | undefined;
          if (canvasEv && canvasEv.id) {
            canvasAcc = mergeCanvas(canvasAcc, canvasEv);
            patchLast({ canvas: canvasAcc });
          }
          const child = ev.child_agent as ChildSpan | undefined;
          if (child?.span_id) {
            childMap.set(child.span_id, {
              ...childMap.get(child.span_id),
              ...child,
              summary: child.summary || childMap.get(child.span_id)?.summary || '',
            });
            const kids = syncChildren();
            patchLast({ children: kids });
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
          thinkingAcc = '';
          thoughtsAcc = [];
          blocksAcc = [];
          thinkStep = -1;
          textStep = -1;
          thinkLive = false;
          mediaAcc = [];
          canvasAcc = [];
          setMessages((m) => {
            const c = [...m];
            c[c.length - 1] = { ...c[c.length - 1], content: '', thinking: '', thoughts: [], blocks: [], thinkingLive: false, media: [], canvas: [], tools: [], children: [] };
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
          ...syncTimeline(),
          thinkingLive: false,
          media: mediaAcc.length ? mediaAcc : c[c.length - 1].media,
          canvas: canvasAcc.length ? canvasAcc : c[c.length - 1].canvas,
          gate: res.gate,
          tools: [...toolEvents],
          children: syncChildren(),
          approvals: syncApprovals(),
        };
        return c;
      });
      const finalStats = res.gate?.agent?.llm_stats;
      if (finalStats) setLlmStats(finalStats);
      if (!activeId) setActiveId(res.session_id);
      if (sendGenRef.current === runId) {
        busyRef.current = false;
        setBusy(false);
        abortRef.current = null;
      }
      void loadSessions();
      setCost({
        prompt: Math.ceil(startChars / 4),
        completion: Math.ceil(acc.length / 4),
        total: Math.ceil((startChars + acc.length) / 4),
      });
    } catch (e) {
      if (sendGenRef.current !== runId) {
        // Superseded by heal/newer send — don't clobber synced messages.
      } else if (e instanceof AbortError || (e as Error)?.name === 'AbortError') {
        setMessages((m) => {
          if (!m.length) return m;
          const last = m[m.length - 1];
          if (last.role === 'assistant' && !last.content.trim() && !(last.tools?.length) && !(last.blocks?.length)) {
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
          const last = m[m.length - 1];
          if (last.role !== 'assistant') return m;
          const has =
            !!(last.content || '').trim()
            || !!(last.tools?.length)
            || !!(last.blocks?.length)
            || !!(last.thinking || '').trim()
            || !!(last.thoughts?.length);
          return has ? m : m.slice(0, -1);
        });
        const sid = activeId;
        if (sid) {
          void api.session(sid).then((s) => {
            if (sendGenRef.current !== runId) return;
            setMessages(s.messages);
            const gen = Boolean(s.generating);
            busyRef.current = gen;
            setBusy(gen);
          }).catch(() => { /* ignore */ });
        }
      }
    } finally {
      if (sendGenRef.current === runId) {
        busyRef.current = false;
        setBusy(false);
        abortRef.current = null;
      }
      window.setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [input, activeId, agentView, loadSessions, activeMeta, messages, setActiveId, systemNote]);

  const stop = useCallback(() => {
    const sid = activeId;
    sendGenRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    busyRef.current = false;
    setBusy(false);
    if (sid) {
      void api.cancelChat(sid).then(async () => {
        for (let i = 0; i < 20; i++) {
          await new Promise((r) => window.setTimeout(r, 150));
          try {
            const s = await api.session(sid);
            setMessages(s.messages);
            if (!s.generating) return;
          } catch { /* retry */ }
        }
      }).catch(() => { /* best-effort */ });
    }
  }, [activeId]);

  const patchApprovals = useCallback((idx: number, approvals: ApprovalRequest[]) => {
    setMessages((m) => {
      if (idx < 0 || idx >= m.length) return m;
      const c = [...m];
      c[idx] = { ...c[idx], approvals };
      return c;
    });
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
    };
    window.addEventListener('super-refresh' as unknown as string, onRefresh as EventListener);
    return () => window.removeEventListener('super-refresh' as unknown as string, onRefresh as EventListener);
  }, [loadSessions]);

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
    sessionLoading,
    isRenaming, mentionPaths, showSlash, slashFilter, showMention, mentionFilter, mentionIndex, setMentionIndex,
    editingIdx, setEditingIdx, editDraft, setEditDraft, cost, tokenStats, activeMeta, inputRef, bottomRef,
    selectMode, selectedIds, toggleSelectMode, toggleSelected, selectAllFiltered, clearSelection, deleteSelected,
    llmStats,
    agentView,
    parentId: agentView?.parentId ?? null,
    activeSpanId: agentView?.spanId ?? null,
    selectSession, selectSpan, backToParent,
    loadSessions, send, stop, regenerate, editAndResend, branchFrom, shareExport, newChat, deleteChat, renameChat,
    handleInputChange, handleFile, setShowSlash, setShowMention, patchApprovals,
  };
}
