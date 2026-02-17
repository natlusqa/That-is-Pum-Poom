import { useKorganStore } from '../store/useKorganStore';

const STATUS_LABELS: Record<string, string> = {
  idle: 'Idle',
  listening: 'Listening',
  thinking: 'Thinking',
  speaking: 'Speaking',
  alert: 'Alert',
  crisis: 'Crisis',
};

export default function StatusBar() {
  const { status, thinkingProgress } = useKorganStore();

  return (
    <div className="status-bar">
      <div className="status-indicator" data-status={status}>
        <span className="status-dot" />
        <span className="status-label">{STATUS_LABELS[status]}</span>
      </div>
      {status === 'thinking' && (
        <div className="status-progress">
          <div
            className="status-progress-bar"
            style={{ width: `${thinkingProgress}%` }}
          />
        </div>
      )}
    </div>
  );
}
