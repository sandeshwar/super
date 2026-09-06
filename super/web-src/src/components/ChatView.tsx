import { Card } from './ui/Card';
import { useChat } from './chat/hooks/useChat';
import { SessionsPanel } from './chat/SessionsPanel';
import { LeafBanner } from './chat/LeafBanner';
import { ChatHeader } from './chat/ChatHeader';
import { ContextBar } from './chat/ContextBar';
import { MessageList } from './chat/MessageList';
import { ChatDock } from './chat/ChatDock';

/**
 * ChatView — orchestrator only. All UI slices live in ./chat/*,
 * state lives in useChat(). Keeps the view thin, testable, and SOLID.
 */
export default function ChatView({
  sessionId,
  onSessionIdChange,
}: {
  sessionId: string | null;
  onSessionIdChange: (id: string | null) => void;
}) {
  const {
    sessions, filtered, activeId, setActiveId, messages, input, busy, error, setError, filter, setFilter,
    isRenaming, leaf, leafRendered, showSlash, slashFilter, showMention, mentionFilter, mentionIndex, setMentionIndex,
    editingIdx, setEditingIdx, editDraft, setEditDraft, cost, tokenStats, activeMeta, inputRef, bottomRef,
    send, stop, regenerate, editAndResend, branchFrom, shareExport, newChat, deleteChat, renameChat,
    handleInputChange, handleFile, setShowSlash, setShowMention,
  } = useChat({ sessionId, onSessionIdChange });

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '240px minmax(0,1fr)', gap: 'var(--space-3)', height: 'calc(100vh - 108px)', minHeight: 440 }}>
      <SessionsPanel
        sessions={sessions}
        filtered={filtered}
        activeId={activeId}
        filter={filter}
        onFilter={setFilter}
        onNewChat={newChat}
        onSelect={setActiveId}
        onDelete={(id) => void deleteChat(id)}
        onRename={(id, t) => void renameChat(id, t)}
      />

      <Card style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <LeafBanner leaf={leaf} leafRendered={leafRendered} />
        <ChatHeader
          activeId={activeId}
          activeMeta={activeMeta}
          messages={messages}
          isRenaming={isRenaming}
          onRename={(id, t) => void renameChat(id, t)}
          onShare={(fmt) => shareExport(fmt)}
          busy={busy}
        />
        <ContextBar tokenStats={tokenStats} leaf={leaf} messagesLen={messages.length} cost={cost} />
        <MessageList
          messages={messages}
          busy={busy}
          error={error}
          editingIdx={editingIdx}
          editDraft={editDraft}
          setEditDraft={setEditDraft}
          setEditingIdx={setEditingIdx}
          onEditAndResend={(idx) => void editAndResend(idx)}
          onCopy={(c) => navigator.clipboard.writeText(c).catch(() => setError('Clipboard blocked'))}
          onEdit={(idx) => { setEditingIdx(idx); setEditDraft(messages[idx].content); }}
          onBranch={(idx) => void branchFrom(idx)}
          onRegenerate={(idx) => void regenerate(idx)}
          onStop={stop}
          onSetInput={(v) => handleInputChange(v)}
          onClearError={() => setError(null)}
          bottomRef={bottomRef}
        />
        <ChatDock
          input={input}
          busy={busy}
          messagesLen={messages.length}
          cost={cost}
          showSlash={showSlash}
          slashFilter={slashFilter}
          showMention={showMention}
          mentionFilter={mentionFilter}
          mentionIndex={mentionIndex}
          setMentionIndex={setMentionIndex}
          onClosePopovers={() => { setShowSlash(false); setShowMention(false); }}
          onInput={handleInputChange}
          onSend={() => void send()}
          onStop={stop}
          onShare={() => shareExport('md')}
          onFile={handleFile}
          inputRef={inputRef}
        />
      </Card>
    </div>
  );
}
