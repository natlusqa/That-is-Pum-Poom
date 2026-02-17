import { create } from 'zustand';

export type KorganStatus = 'idle' | 'listening' | 'thinking' | 'speaking' | 'alert' | 'crisis';
export type AutonomyLevel = 'manual' | 'suggestion' | 'conditional' | 'full';

export type ActionType = 'info' | 'success' | 'warning' | 'error' | 'rollback' | 'agent';

export interface ActionLogEntry {
  id: string;
  timestamp: Date;
  message: string;
  type: ActionType;
  actionId?: string;  // For rollback support
}

interface KorganState {
  status: KorganStatus;
  autonomyLevel: AutonomyLevel;
  actionLog: ActionLogEntry[];
  thinkingProgress: number;
  crisisMode: boolean;
  connected: boolean;

  setStatus: (status: KorganStatus) => void;
  setAutonomyLevel: (level: AutonomyLevel) => void;
  addAction: (message: string, type?: ActionType, actionId?: string) => void;
  setThinkingProgress: (progress: number) => void;
  setCrisisMode: (crisis: boolean) => void;
  setConnected: (connected: boolean) => void;
}

export const useKorganStore = create<KorganState>((set) => ({
  status: 'idle',
  autonomyLevel: 'manual',
  actionLog: [],
  thinkingProgress: 0,
  crisisMode: false,
  connected: false,

  setStatus: (status) => set({ status }),
  setAutonomyLevel: (level) => set({ autonomyLevel: level }),
  addAction: (message, type = 'info', actionId) =>
    set((state) => ({
      actionLog: [
        ...state.actionLog,
        {
          id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
          timestamp: new Date(),
          message,
          type,
          actionId,
        },
      ].slice(-50),  // Keep last 50 entries
    })),
  setThinkingProgress: (progress) => set({ thinkingProgress: progress }),
  setCrisisMode: (crisis) => set({ crisisMode: crisis }),
  setConnected: (connected) => set({ connected }),
}));
