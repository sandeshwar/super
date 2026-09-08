import { Icons } from '../ui/Icon';

export type ChatSideToggleId = 'tools' | 'context';

type Props = {
  toolsOpen: boolean;
  toolsBusy?: boolean;
  showTools?: boolean;
  onToggleTools: () => void;
  contextOpen: boolean;
  onToggleContext: () => void;
};

/**
 * Panel toggles in the chat header (after rename actions). Tools first; context next; more later.
 */
export function ChatSideToggles({
  toolsOpen, toolsBusy, showTools = true, onToggleTools,
  contextOpen, onToggleContext,
}: Props) {
  return (
    <div className="chat-side-toggles" role="toolbar" aria-label="Chat panels">
      {showTools && (
        <button
          type="button"
          className={`chat-side-toggle${toolsOpen ? ' is-active' : ''}${toolsBusy ? ' is-busy' : ''}`}
          aria-pressed={toolsOpen}
          aria-label={toolsOpen ? 'Hide tools' : 'Show tools'}
          title={toolsOpen ? 'Hide tools' : 'Tools'}
          onClick={onToggleTools}
        >
          <Icons.tools size={14} />
        </button>
      )}
      <button
        type="button"
        className={`chat-side-toggle${contextOpen ? ' is-active' : ''}`}
        aria-pressed={contextOpen}
        aria-label={contextOpen ? 'Hide context' : 'Show context'}
        title={contextOpen ? 'Hide context' : 'Context'}
        onClick={onToggleContext}
      >
        <Icons.activity size={14} />
      </button>
    </div>
  );
}
