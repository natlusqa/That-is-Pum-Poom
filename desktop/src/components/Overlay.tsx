import { useKorganStore } from '../store/useKorganStore';

const GLOW_WIDTH = 4;
const GLOW_INTENSITY = 0.85;

const statusConfig = {
  idle: { color: '#0066FF', animation: 'none', opacity: 0.3 },
  listening: { color: '#0066FF', animation: 'pulse', opacity: 0.9 },
  thinking: { color: '#0066FF', animation: 'particles', opacity: 0.95 },
  speaking: { color: '#0066FF', animation: 'wave', opacity: 0.9 },
  alert: { color: '#FF8800', animation: 'pulse', opacity: 0.95 },
  crisis: { color: '#FF3333', animation: 'flash', opacity: 1 },
};

export default function Overlay() {
  const { status, crisisMode } = useKorganStore();
  const effectiveStatus = crisisMode ? 'crisis' : status;
  const config = statusConfig[effectiveStatus];

  return (
    <div
      className="korgan-overlay"
      data-status={effectiveStatus}
      data-animation={config.animation}
      style={
        {
          '--glow-color': config.color,
          '--glow-width': `${GLOW_WIDTH}px`,
          '--glow-intensity': GLOW_INTENSITY,
          '--glow-opacity': config.opacity,
        } as React.CSSProperties
      }
    >
      <div className="glow-edge glow-top" />
      <div className="glow-edge glow-right" />
      <div className="glow-edge glow-bottom" />
      <div className="glow-edge glow-left" />
      <div className="glow-corner glow-corner-tl" />
      <div className="glow-corner glow-corner-tr" />
      <div className="glow-corner glow-corner-br" />
      <div className="glow-corner glow-corner-bl" />
    </div>
  );
}
