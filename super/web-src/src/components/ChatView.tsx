import { useState } from 'react';
import { Card } from './ui/Card';
import { Button } from './ui/Button';
import { useChat } from './chat/hooks/useChat';
import { SessionsPanel } from './chat/SessionsPanel';
import { LeafBanner } from './chat/LeafBanner';
import { ChatHeader } from './chat/ChatHeader';
import { ContextBar } from './chat/ContextBar';
import { MessageList } from './chat/MessageList';
import { ChatDock } from './chat/ChatDock';
import { ToolRail } from './chat/ToolRail';
import { CanvasPanel, useCanvasController } from './chat/CanvasPanel';

/**
 * ChatView — orchestrator only. All UI slices live in ./chat/*,
 * state lives in useChat(). Keeps the view thin, testable, and SOLID.
 *
 * Layout: [sessions | chat card | canvas] — canvas is a sibling of the chat
 * panel (not nested inside it) and follows the active session's artifacts.
 */
export default function ChatView({
  sessionId,
  onSessionIdChange,
  contextLength,
}: {
  sessionId: string | null;
  onSessionIdChange: (id: string | null) => void;
  contextLength?: number | null;
}) {
  const {
    sessions, filtered, activeId, messages, input, busy, error, setError, filter, setFilter,
    isRenaming, leaf, leafRendered, mentionPaths, showSlash, slashFilter, showMention, mentionFilter, mentionIndex, setMentionIndex,
    editingIdx, setEditingIdx, editDraft, setEditDraft, cost, tokenStats, activeMeta, inputRef, bottomRef,
    selectMode, selectedIds, toggleSelectMode, toggleSelected, selectAllFiltered, clearSelection, deleteSelected,
    llmStats,
    agentView, parentId, activeSpanId, selectSession, selectSpan, backToParent,
    send, stop, regenerate, editAndResend, branchFrom, shareExport, newChat, deleteChat, renameChat,
    handleInputChange, handleFile, setShowSlash, setShowMention, patchApprovals,
  } = useChat({ sessionId, onSessionIdChange, contextLength });

  const [sessionsOpen, setSessionsOpen] = useState(false);
  const canvas = useCanvasController(messages, activeId);
  const showCanvasCol = canvas.hasArtifacts || canvas.detached;

  return (
    <div
      className={[
        'cols-chat',
        sessionsOpen ? 'sessions-open' : '',
        showCanvasCol ? 'has-canvas' : '',
        showCanvasCol && !canvas.open && !canvas.detached ? 'canvas-collapsed' : '',
        canvas.detached ? 'canvas-detached' : '',
      ].filter(Boolean).join(' ')}
    >
      <div className="chat-sessions-toggle-row">
        <Button size="sm" variant="ghost" onClick={() => setSessionsOpen((v) => !v)} aria-expanded={sessionsOpen}>
          {sessionsOpen ? 'Hide chats' : `Chats${sessions.length ? ` (${sessions.length})` : ''}`}
        </Button>
        <Button size="sm" variant="primary" onClick={() => void newChat()}>New chat</Button>
      </div>

      <SessionsPanel
        sessions={sessions}
        filtered={filtered}
        activeId={activeId}
        parentId={parentId}
        activeSpanId={activeSpanId}
        filter={filter}
        busy={busy}
        selectMode={selectMode}
        selectedIds={selectedIds}
        onFilter={setFilter}
        onNewChat={newChat}
        onSelect={(id) => { selectSession(id); setSessionsOpen(false); }}
        onSelectSpan={(pid, sp) => { selectSpan(pid, sp); setSessionsOpen(false); }}
        onDelete={(id) => void deleteChat(id)}
        onRename={(id, t) => void renameChat(id, t)}
        onToggleSelectMode={toggleSelectMode}
        onToggleSelected={toggleSelected}
        onSelectAllFiltered={selectAllFiltered}
        onClearSelection={clearSelection}
        onDeleteSelected={() => void deleteSelected()}
      />

      <Card className="chat-panel">
        <LeafBanner leaf={leaf} leafRendered={leafRendered} />
        <ChatHeader
          activeId={activeId}
          activeMeta={activeMeta}
          messages={messages}
          isRenaming={isRenaming}
          onRename={(id, t) => void renameChat(id, t)}
          busy={busy}
          agentView={agentView}
          onBackToParent={backToParent}
        />
        <ContextBar tokenStats={tokenStats} leaf={leaf} messagesLen={messages.length} cost={cost} llmStats={llmStats} busy={busy} />
        <div className="chat-main">
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
            onSendSuggestion={(v) => void send(v)}
            onClearError={() => setError(null)}
            onApprovalsChange={patchApprovals}
            bottomRef={bottomRef}
          />
          <ToolRail messages={messages} busy={busy} />
        </div>
        <ChatDock
          input={input}
          busy={busy}
          messagesLen={messages.length}
          cost={cost}
          showSlash={showSlash}
          slashFilter={slashFilter}
          showMention={showMention}
          mentionFilter={mentionFilter}
          mentionPaths={mentionPaths}
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

      {showCanvasCol && (
        <CanvasPanel
          artifacts={canvas.artifacts}
          activeId={canvas.activeId}
          open={canvas.open}
          detached={canvas.detached}
          onSelect={canvas.setActiveId}
          onOpenChange={canvas.setOpen}
          onClose={canvas.close}
          onCloseOne={canvas.closeOne}
          onDetach={canvas.detach}
          onReattach={canvas.reattach}
        />
      )}
    </div>
  );
}
