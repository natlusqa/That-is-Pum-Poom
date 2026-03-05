import { useRef, useEffect, useState } from 'react';
import { VideoRTC } from '../lib/video-rtc.js';

/**
 * MSEPlayer — thin React wrapper around go2rtc's official VideoRTC web component.
 * Uses the EXACT same code that powers go2rtc's built-in player (the one that works at :1985).
 */

// Register the custom element once
if (!customElements.get('video-rtc')) {
  customElements.define('video-rtc', VideoRTC);
}

function MSEPlayer({ cameraUrl, cameraId, muted = true, onError, onConnected, className }) {
  const containerRef = useRef(null);
  const rtcRef = useRef(null);
  const [status, setStatus] = useState('connecting');
  const [posterUrl, setPosterUrl] = useState(null);

  // Load poster for instant visual feedback
  useEffect(() => {
    if (!cameraId) return;
    const token = localStorage.getItem('token');
    if (!token) return;
    let revUrl = null;
    fetch(`/api/cameras/${cameraId}/poster`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => (r.ok ? r.blob() : null))
      .then(blob => {
        if (blob && blob.size > 0) {
          revUrl = URL.createObjectURL(blob);
          setPosterUrl(revUrl);
        }
      })
      .catch(() => {});
    return () => { if (revUrl) URL.revokeObjectURL(revUrl); };
  }, [cameraId]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // Create the go2rtc web component
    const el = document.createElement('video-rtc');
    el.style.display = 'block';
    el.style.width = '100%';
    el.style.height = '100%';

    // Configure: WebRTC first (handles H.265 natively = no transcoding = zero latency)
    // Falls back to MSE (uses H.264 transcode) if WebRTC unavailable
    el.mode = 'webrtc,mse';
    el.media = 'video,audio';
    el.visibilityCheck = false;
    el.background = true;

    rtcRef.current = el;
    container.appendChild(el);

    // Use raw stream for WebRTC (H.265 direct), transcoded for MSE fallback
    // VideoRTC tries WebRTC first; if it works with H.265, no transcoding needed
    const streamSrc = cameraId ? `camera_${cameraId}` : cameraUrl;
    const wsUrl = `${location.origin.replace('http', 'ws')}/go2rtc/api/ws?src=${encodeURIComponent(streamSrc)}`;

    // Monitor the internal video element for playback
    const checkVideo = setInterval(() => {
      const video = el.querySelector('video') || el.video;
      if (video && video.readyState >= 2 && !video.paused) {
        video.controls = false;
        setStatus('connected');
        onConnected?.();
        clearInterval(checkVideo);
      }
    }, 300);

    // Monitor for errors via WebSocket state
    const checkWs = setInterval(() => {
      if (el.wsState === WebSocket.CLOSED && el.pcState === WebSocket.CLOSED) {
        // Both transports failed
        if (status !== 'connecting') {
          setStatus('reconnecting');
        }
      }
    }, 2000);

    // Start the stream
    el.src = wsUrl;

    // Set muted on internal video once it appears
    const muteInterval = setInterval(() => {
      const video = el.querySelector('video') || el.video;
      if (video) {
        video.muted = muted;
        video.playsInline = true;
        video.controls = false;
        clearInterval(muteInterval);
      }
    }, 100);

    return () => {
      clearInterval(checkVideo);
      clearInterval(checkWs);
      clearInterval(muteInterval);

      // Disconnect the web component
      if (rtcRef.current) {
        try { rtcRef.current.ondisconnect(); } catch {}
        rtcRef.current = null;
      }

      // Remove from DOM
      while (container.firstChild) {
        container.removeChild(container.firstChild);
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameraUrl, cameraId]);

  // Update muted state on the fly
  useEffect(() => {
    const el = rtcRef.current;
    if (!el) return;
    const video = el.querySelector('video') || el.video;
    if (video) {
      video.muted = muted;
      video.controls = false;
    }
  }, [muted]);

  const isLoading = status === 'connecting' || status === 'reconnecting';

  const handleRetry = () => {
    setStatus('connecting');
    const el = rtcRef.current;
    if (el) {
      try { el.ondisconnect(); } catch {}
      const streamSrc = cameraId ? `camera_${cameraId}` : cameraUrl;
      const wsUrl = `${location.origin.replace('http', 'ws')}/go2rtc/api/ws?src=${encodeURIComponent(streamSrc)}`;
      el.src = wsUrl;
    }
  };

  return (
    <div className={`mse-player ${className || ''}`} style={{ position: 'relative' }}>
      {isLoading && posterUrl && (
        <img
          src={posterUrl}
          alt=""
          style={{
            position: 'absolute', top: 0, left: 0,
            width: '100%', height: '100%',
            objectFit: 'contain', zIndex: 2, background: '#000',
          }}
          onError={() => setPosterUrl(null)}
        />
      )}

      <div
        ref={containerRef}
        style={{
          width: '100%', height: '100%',
          background: '#000',
          position: 'relative',
          zIndex: isLoading ? 0 : 3,
        }}
      />

      {status === 'connecting' && (
        <div style={{
          position: 'absolute', bottom: 12, left: '50%',
          transform: 'translateX(-50%)', zIndex: 4,
          display: 'flex', alignItems: 'center', gap: 6,
          background: 'rgba(0,0,0,0.7)', borderRadius: 20,
          padding: '6px 14px', backdropFilter: 'blur(4px)',
        }}>
          <div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }}></div>
          <span style={{ fontSize: 12, color: '#fff', opacity: 0.9 }}>Connecting...</span>
        </div>
      )}

      {status === 'reconnecting' && (
        <div style={{
          position: 'absolute', bottom: 12, left: '50%',
          transform: 'translateX(-50%)', zIndex: 4,
          display: 'flex', alignItems: 'center', gap: 6,
          background: 'rgba(0,0,0,0.7)', borderRadius: 20,
          padding: '6px 14px', backdropFilter: 'blur(4px)',
        }}>
          <div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }}></div>
          <span style={{ fontSize: 12, color: '#fff', opacity: 0.9 }}>Reconnecting...</span>
        </div>
      )}

      {status === 'error' && (
        <div className="mse-overlay mse-overlay-error" style={{ zIndex: 4 }}>
          <span>Stream unavailable</span>
          <button
            className="btn btn-sm btn-primary"
            onClick={handleRetry}
            style={{ marginTop: 8 }}
          >
            Retry
          </button>
        </div>
      )}

      {status === 'connected' && (
        <div className="mse-live-badge">LIVE</div>
      )}
    </div>
  );
}

export function getVideoRef(playerElement) {
  return playerElement?.querySelector('video') || null;
}

export default MSEPlayer;
