/** Plain-language UI copy — keep jargon out of the product surface. */
import type { View } from './router';

export const STATUS_LABEL: Record<string, string> = {
  proven: 'Done',
  waiting: 'Waiting',
  doing: 'In progress',
  blocked: 'Blocked',
};

export function statusLabel(status: string): string {
  return STATUS_LABEL[status] ?? status;
}

export const VIEW_META: Record<View, { title: string; desc: string; icon: 'chat' | 'tree' | 'approve' | 'report' | 'settings' }> = {
  chat: {
    title: 'Chat',
    desc: 'Ask questions about the current task and your code',
    icon: 'chat',
  },
  tree: {
    title: 'Tasks',
    desc: 'See all work and how pieces depend on each other',
    icon: 'tree',
  },
  approve: {
    title: 'Review',
    desc: 'Check work and add proof before marking it done',
    icon: 'approve',
  },
  report: {
    title: 'Results',
    desc: 'What’s finished, what failed checks, and open problems',
    icon: 'report',
  },
  settings: {
    title: 'Settings',
    desc: 'Model, look, tools, and connections',
    icon: 'settings',
  },
  canvas: {
    title: 'Canvas',
    desc: 'Detached artifact viewer',
    icon: 'chat',
  },
};

export const FILTER_LABEL: Record<string, string> = {
  all: 'All',
  waiting: 'Waiting',
  doing: 'In progress',
  proven: 'Done',
  blocked: 'Blocked',
};
