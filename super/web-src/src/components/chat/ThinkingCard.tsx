import { useEffect, useRef, useState } from 'react';
import { Collapsible } from '../ui/Collapsible';

type Props = {
  thinking: string;
  /** True while this assistant turn is still streaming. */
  streaming?: boolean;
  /** True once this step's answer/tools have started — card auto-collapses. */
  hasOutput?: boolean;
  /** Label suffix when multiple thought blocks exist (1-based). */
  index?: number;
  total?: number;
};

/**
 * Model reasoning trace. Open while this step's thinking streams; collapses as
 * soon as that step's output/tools begin. User can re-expand anytime.
 */
export function ThinkingCard({ thinking, streaming, hasOutput }: Props) {
  const autoOpen = Boolean(streaming && !hasOutput);
  const [userOpen, setUserOpen] = useState<boolean | null>(null);
  const wasStreaming = useRef(Boolean(streaming));
  const wasLive = useRef(autoOpen);
  const bodyRef = useRef<HTMLDivElement>(null);

  // New live phase → clear manual override so it opens again.
  useEffect(() => {
    if (streaming && !wasStreaming.current) {
      setUserOpen(null);
    }
    if (autoOpen && !wasLive.current) {
      setUserOpen(null);
    }
    wasStreaming.current = Boolean(streaming);
    wasLive.current = autoOpen;
  }, [streaming, autoOpen]);

  const open = userOpen ?? autoOpen;
  const live = Boolean(streaming && !hasOutput);

  // Keep the live (or user-expanded) body pinned to the latest tokens.
  useEffect(() => {
    if (!open) return;
    const el = bodyRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [thinking, open, live]);

  if (!thinking && !(streaming && !hasOutput)) return null;

  const preview = thinking.trim();
  const title = live ? 'Thinking' : 'Thought';
  const meta = live
    ? 'live'
    : preview
      ? `${preview.split(/\s+/).filter(Boolean).length} words`
      : undefined;

  return (
    <div className={`thinking-card${live ? ' is-live' : ''}`}>
      <Collapsible
        className="collapsible-bare thinking-collapse"
        compact
        animated
        open={open}
        onOpenChange={(next) => setUserOpen(next)}
        title={title}
        meta={meta ? <span className="mono thinking-meta">{meta}</span> : undefined}
      >
        <div ref={bodyRef} className="thinking-body">
          {preview || (live ? '…' : '')}
        </div>
      </Collapsible>
    </div>
  );
}

/** Normalize persisted thoughts / legacy joined thinking into a list. */
export function normalizeThoughts(message: { thoughts?: string[]; thinking?: string }): string[] {
  if (Array.isArray(message.thoughts) && message.thoughts.length) {
    return message.thoughts.map((t) => String(t || '').trim()).filter(Boolean);
  }
  const joined = (message.thinking || '').trim();
  return joined ? [joined] : [];
}
