import { useState, useRef, useEffect } from 'react';
import { useKorganStore } from '../store/useKorganStore';

const TYPE_ICONS: Record<string, string> = {
  info: '\u2139',
  success: '\u2713',
  warning: '\u26A0',
  error: '\u2717',
  rollback: '\u21B6',
  agent: '\u2699',
};

const TYPE_STYLES: Record<string, string> = {
  info: 'action-info',
  success: 'action-success',
  warning: 'action-warning',
  error: 'action-error',
  rollback: 'action-rollback',
  agent: 'action-agent',
};

function formatTime(date: Date) {
  return date.toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export default function ActionLog() {
  const [collapsed, setCollapsed] = useState(false);
  const [filter, setFilter] = useState<string>('all');
  const listRef = useRef<HTMLDivElement>(null);
  const { actionLog } = useKorganStore();

  // Auto-scroll to bottom
  useEffect(() => {
    if (listRef.current && !collapsed) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [actionLog, collapsed]);

  const filteredLog = filter === 'all'
    ? actionLog
    : actionLog.filter(e => e.type === filter);

  const errorCount = actionLog.filter(e => e.type === 'error').length;
  const warnCount = actionLog.filter(e => e.type === 'warning').length;

  const handleRollback = (actionId: string | undefined) => {
    if (!actionId) return;
    if (typeof window !== 'undefined' && window.korgan) {
      window.korgan.sendMessage(JSON.stringify({
        type: 'rollback',
        action_id: actionId,
      }));
    }
  };

  return (
    <div className={`action-log ${collapsed ? 'collapsed' : ''}`}>
      <button
        className="action-log-header"
        onClick={() => setCollapsed(!collapsed)}
      >
        <span>Action Journal</span>
        <div className="action-log-badges">
          {errorCount > 0 && <span className="badge badge-error">{errorCount}</span>}
          {warnCount > 0 && <span className="badge badge-warn">{warnCount}</span>}
          <span className="action-log-count">{actionLog.length}</span>
        </div>
        <span className="action-log-toggle">{collapsed ? '\u25B6' : '\u25BC'}</span>
      </button>
      {!collapsed && (
        <>
          <div className="action-log-filters">
            {['all', 'info', 'success', 'warning', 'error', 'agent'].map(f => (
              <button
                key={f}
                className={`filter-btn ${filter === f ? 'active' : ''}`}
                onClick={() => setFilter(f)}
              >
                {f === 'all' ? 'All' : TYPE_ICONS[f] || f}
              </button>
            ))}
          </div>
          <div className="action-log-list" ref={listRef}>
            {filteredLog.length === 0 ? (
              <div className="action-log-empty">No actions yet</div>
            ) : (
              filteredLog.slice(-20).map((entry) => (
                <div
                  key={entry.id}
                  className={`action-log-entry ${TYPE_STYLES[entry.type] || 'action-info'}`}
                >
                  <span className="action-icon">{TYPE_ICONS[entry.type] || '\u2022'}</span>
                  <span className="action-time">{formatTime(entry.timestamp)}</span>
                  <span className="action-message">{entry.message}</span>
                  {entry.type === 'error' && entry.actionId && (
                    <button
                      className="action-rollback-btn"
                      onClick={() => handleRollback(entry.actionId)}
                      title="Rollback this action"
                    >
                      {'\u21B6'}
                    </button>
                  )}
                </div>
              ))
            )}
          </div>
        </>
      )}
    </div>
  );
}
