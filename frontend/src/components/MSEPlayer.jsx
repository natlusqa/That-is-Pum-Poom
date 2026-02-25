import { useRef, useEffect, useCallback, useState } from 'react';

/**
 * MSE (Media Source Extensions) player using go2rtc WebSocket API.
 * Provides ~0.5-1s latency — much better than HLS/MP4 (3-9s).
 *
 * Protocol:
 * 1. Connect WebSocket to /go2rtc/api/ws?src=CAMERA_URL
 * 2. First text message = MIME codec string (e.g. "video/mp4; codecs=\"avc1.640029\"")
 * 3. Subsequent binary messages = fMP4 init segment + media segments
 * 4. Append to MediaSource SourceBuffer for near-real-time playback
 */
function MSEPlayer({ cameraUrl, muted = true, onError, onConnected, className }) {
  const videoRef = useRef(null);
  const wsRef = useRef(null);
  const msRef = useRef(null);
  const sbRef = useRef(null);
  const queueRef = useRef([]);
  const reconnectTimer = useRef(null);
  const [status, setStatus] = useState('connecting');
  const retryCount = useRef(0);
  const MAX_RETRIES = 10;
  const MAX_BUFFER_DURATION = 4; // seconds — trim buffer beyond this

  const cleanup = useCallback(() => {
    clearTimeout(reconnectTimer.current);
    reconnectTimer.current = null;

    if (wsRef.current) {
      wsRef.current.onopen = null;
      wsRef.current.onmessage = null;
      wsRef.current.onerror = null;
      wsRef.current.onclose = null;
      if (wsRef.current.readyState < 2) wsRef.current.close();
      wsRef.current = null;
    }

    if (sbRef.current) {
      try {
        if (msRef.current?.readyState === 'open') {
          sbRef.current.abort();
        }
      } catch { /* ignore */ }
      sbRef.current = null;
    }

    if (msRef.current) {
      try {
        if (msRef.current.readyState === 'open') {
          msRef.current.endOfStream();
        }
      } catch { /* ignore */ }
      msRef.current = null;
    }

    queueRef.current = [];

    if (videoRef.current) {
      videoRef.current.src = '';
      videoRef.current.load();
    }
  }, []);

  const trimBuffer = useCallback(() => {
    const sb = sbRef.current;
    const video = videoRef.current;
    if (!sb || !video || sb.updating) return;

    try {
      if (sb.buffered.length > 0) {
        const buffEnd = sb.buffered.end(sb.buffered.length - 1);
        const buffStart = sb.buffered.start(0);
        const currentTime = video.currentTime;

        // Remove old data that's more than MAX_BUFFER_DURATION behind current time
        if (currentTime - buffStart > MAX_BUFFER_DURATION) {
          sb.remove(buffStart, currentTime - 1);
        }

        // If playback falls behind too much, seek to near-live
        if (buffEnd - currentTime > 3) {
          video.currentTime = buffEnd - 0.5;
        }
      }
    } catch { /* ignore */ }
  }, []);

  const appendBuffer = useCallback((data) => {
    const sb = sbRef.current;
    if (!sb) return;

    if (sb.updating) {
      queueRef.current.push(data);
      return;
    }

    try {
      sb.appendBuffer(data);
    } catch (e) {
      if (e.name === 'QuotaExceededError') {
        // Buffer full — trim and retry
        trimBuffer();
        queueRef.current.push(data);
      } else {
        console.error('MSE append error:', e);
      }
    }
  }, [trimBuffer]);

  const connect = useCallback(() => {
    if (!cameraUrl) return;
    cleanup();

    if (retryCount.current >= MAX_RETRIES) {
      setStatus('error');
      onError?.('Maximum reconnection attempts reached');
      return;
    }

    setStatus('connecting');

    const wsProtocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${location.host}/go2rtc/api/ws?src=${encodeURIComponent(cameraUrl)}`;

    try {
      const ws = new WebSocket(wsUrl);
      ws.binaryType = 'arraybuffer';
      wsRef.current = ws;

      ws.onopen = () => {
        retryCount.current = 0;
      };

      ws.onmessage = (ev) => {
        if (typeof ev.data === 'string') {
          // First message: codec MIME type
          const codecMime = ev.data;

          if (!MediaSource.isTypeSupported(codecMime)) {
            console.error('Unsupported codec:', codecMime);
            setStatus('error');
            onError?.(`Unsupported codec: ${codecMime}`);
            return;
          }

          const ms = new MediaSource();
          msRef.current = ms;

          const video = videoRef.current;
          if (!video) return;

          video.src = URL.createObjectURL(ms);

          ms.onsourceopen = () => {
            try {
              const sb = ms.addSourceBuffer(codecMime);
              sb.mode = 'segments';
              sbRef.current = sb;

              sb.onupdateend = () => {
                // Process queued segments
                if (queueRef.current.length > 0 && !sb.updating) {
                  try {
                    sb.appendBuffer(queueRef.current.shift());
                  } catch { /* ignore */ }
                }
                trimBuffer();
              };

              setStatus('connected');
              onConnected?.();
              retryCount.current = 0;
            } catch (e) {
              console.error('Failed to create SourceBuffer:', e);
              setStatus('error');
              onError?.('Failed to initialize video decoder');
            }
          };
        } else {
          // Binary data: fMP4 segment
          appendBuffer(ev.data);
        }
      };

      ws.onerror = () => {
        // Error will trigger onclose
      };

      ws.onclose = (ev) => {
        // Don't reconnect if intentionally closed
        if (!wsRef.current) return;

        retryCount.current++;
        const delay = Math.min(1000 * Math.pow(2, retryCount.current - 1), 10000);

        if (retryCount.current < MAX_RETRIES) {
          setStatus('reconnecting');
          reconnectTimer.current = setTimeout(connect, delay);
        } else {
          setStatus('error');
          onError?.('Stream connection lost');
        }
      };
    } catch (err) {
      console.error('WebSocket connection error:', err);
      setStatus('error');
      onError?.('Failed to connect to stream');
    }
  }, [cameraUrl, cleanup, appendBuffer, trimBuffer, onError, onConnected]);

  // Auto-play when video has data
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const handleCanPlay = () => {
      video.play().catch(() => {
        // Autoplay blocked — already muted so should work
      });
    };

    video.addEventListener('canplay', handleCanPlay);
    return () => video.removeEventListener('canplay', handleCanPlay);
  }, []);

  // Keep playback near live edge
  useEffect(() => {
    if (status !== 'connected') return;

    const interval = setInterval(() => {
      const video = videoRef.current;
      const sb = sbRef.current;
      if (!video || !sb || sb.buffered.length === 0) return;

      const buffEnd = sb.buffered.end(sb.buffered.length - 1);
      // If we're more than 2s behind live, jump ahead
      if (buffEnd - video.currentTime > 2) {
        video.currentTime = buffEnd - 0.3;
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [status]);

  useEffect(() => {
    connect();
    return cleanup;
  }, [connect, cleanup]);

  // Expose video ref for snapshot
  useEffect(() => {
    if (videoRef.current) {
      videoRef.current._mseStatus = status;
    }
  }, [status]);

  return (
    <div className={`mse-player ${className || ''}`} style={{ position: 'relative' }}>
      <video
        ref={videoRef}
        autoPlay
        muted={muted}
        playsInline
        style={{ width: '100%', height: '100%', objectFit: 'contain', background: '#000' }}
      />

      {status === 'connecting' && (
        <div className="mse-overlay">
          <div className="spinner"></div>
          <span>Connecting to stream...</span>
        </div>
      )}

      {status === 'reconnecting' && (
        <div className="mse-overlay">
          <div className="spinner"></div>
          <span>Reconnecting... (attempt {retryCount.current}/{MAX_RETRIES})</span>
        </div>
      )}

      {status === 'error' && (
        <div className="mse-overlay mse-overlay-error">
          <span>Stream unavailable</span>
          <button
            className="btn btn-sm btn-primary"
            onClick={() => { retryCount.current = 0; connect(); }}
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
