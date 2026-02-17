export {};

declare global {
  interface Window {
    korgan?: {
      sendMessage: (channel: string, data?: unknown) => void;
      onStatusChange: (callback: (data: unknown) => void) => void;
      onResponse: (callback: (data: unknown) => void) => void;
      onAutonomyChanged: (callback: (level: string) => void) => void;
      getStatus: () => Promise<{ status: string; autonomy: string }>;
      setAutonomyLevel: (level: string) => void;
    };
  }
}
