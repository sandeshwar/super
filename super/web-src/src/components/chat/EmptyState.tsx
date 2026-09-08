import { Button } from '../ui/Button';

const SUGGESTIONS = [
  { label: 'What can you help with?', prompt: 'What kinds of things can you help me with?' },
  { label: 'Search the web', prompt: 'Search for the latest news around AI and LLMs' },
  { label: "What's in this workspace?", prompt: 'Give me a quick tour of this workspace.' },
];

export function EmptyState({ onPick }: { onPick: (s: string) => void }) {
  return (
    <div className="empty empty--chat">
      <div className="empty-icon" aria-hidden>
        <svg viewBox="0 0 16 16" fill="none">
          <path d="M2.5 3.5a1 1 0 011-1h9a1 1 0 011 1v5.5a1 1 0 01-1 1H6.2l-1.9 1.9a.5.5 0 01-.8-.4V10h-1a1 1 0 01-1-1v-5.5z" stroke="currentColor" strokeWidth="1.2" />
        </svg>
      </div>
      <h4>Ask anything</h4>
      <p>Generalist assistant with tools and specialists. Workspace claims are checked against evidence.</p>
      <div className="empty-suggestions">
        {SUGGESTIONS.map((s, i) => (
          <Button
            key={s.label}
            size="sm"
            variant="default"
            className="empty-chip"
            style={{ animationDelay: `${80 + i * 70}ms` }}
            onClick={() => onPick(s.prompt)}
          >
            {s.label}
          </Button>
        ))}
      </div>
    </div>
  );
}
