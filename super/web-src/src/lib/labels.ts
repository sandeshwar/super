/** Plain-language UI copy — keep jargon out of the product surface. */
import type { View } from './router';

export const VIEW_META: Record<View, { title: string; desc: string; icon: 'chat' | 'settings' }> = {
  chat: {
    title: 'Chat',
    desc: 'Ask questions about your code and project',
    icon: 'chat',
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
