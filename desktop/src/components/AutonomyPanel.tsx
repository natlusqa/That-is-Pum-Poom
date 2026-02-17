import { useState } from 'react';
import { useKorganStore, type AutonomyLevel } from '../store/useKorganStore';

const AUTONOMY_OPTIONS: { value: AutonomyLevel; label: string; desc: string; icon: string; color: string }[] = [
  { value: 'manual', label: 'Manual', desc: 'All actions require your approval', icon: '\u{1F6E1}', color: '#4488ff' },
  { value: 'suggestion', label: 'Suggestion', desc: 'System suggests, you decide', icon: '\u{1F4AC}', color: '#44aaff' },
  { value: 'conditional', label: 'Conditional', desc: 'Safe actions auto-execute', icon: '\u26A1', color: '#ffaa00' },
  { value: 'full', label: 'Full Autonomous', desc: 'Full auto within allowlist', icon: '\u{1F680}', color: '#ff6644' },
];

export default function AutonomyPanel() {
  const { autonomyLevel, crisisMode, setAutonomyLevel } = useKorganStore();
  const [confirming, setConfirming] = useState<AutonomyLevel | null>(null);

  const handleChange = (level: AutonomyLevel) => {
    // Require confirmation for elevated levels
    if (level === 'conditional' || level === 'full') {
      if (confirming === level) {
        // Second click confirms
        doChange(level);
        setConfirming(null);
      } else {
        setConfirming(level);
        setTimeout(() => setConfirming(null), 5000); // Auto-cancel after 5s
      }
    } else {
      doChange(level);
    }
  };

  const doChange = (level: AutonomyLevel) => {
    setAutonomyLevel(level);
    if (typeof window !== 'undefined' && window.korgan) {
      window.korgan.setAutonomyLevel(level);
    }
  };

  const handleCrisisExit = () => {
    if (typeof window !== 'undefined' && window.korgan) {
      window.korgan.sendMessage(JSON.stringify({ type: 'crisis_exit' }));
    }
  };

  const currentOption = AUTONOMY_OPTIONS.find(o => o.value === autonomyLevel);

  return (
    <div className="autonomy-panel">
      <div className="autonomy-header">
        <span>Autonomy</span>
        <span className="autonomy-current" style={{ color: currentOption?.color }}>
          {currentOption?.icon} {currentOption?.label}
        </span>
      </div>

      {crisisMode && (
        <div className="autonomy-crisis-banner">
          <span className="crisis-icon">{'\u26A0'}</span>
          <div>
            <strong>Crisis Mode Active</strong>
            <p>System downgraded to Manual. All actions require approval.</p>
          </div>
          <button className="crisis-exit-btn" onClick={handleCrisisExit}>
            Exit Crisis
          </button>
        </div>
      )}

      <div className="autonomy-options">
        {AUTONOMY_OPTIONS.map((option) => {
          const isActive = autonomyLevel === option.value;
          const isConfirming = confirming === option.value;

          return (
            <button
              key={option.value}
              className={`autonomy-option ${isActive ? 'active' : ''} ${isConfirming ? 'confirming' : ''}`}
              onClick={() => handleChange(option.value)}
              disabled={crisisMode && option.value !== 'manual'}
              style={{ '--level-color': option.color } as React.CSSProperties}
            >
              <div className="option-top">
                <span className="option-icon">{option.icon}</span>
                <span className="option-label">{option.label}</span>
                {isActive && <span className="option-active-dot" />}
              </div>
              <span className="option-desc">{option.desc}</span>
              {isConfirming && (
                <span className="option-confirm">Click again to confirm</span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
