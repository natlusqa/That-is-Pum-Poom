import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { FiArrowLeft, FiMaximize, FiRefreshCcw, FiCopy, FiSquare, FiCamera, FiVolume2, FiVolumeX } from 'react-icons/fi';
import { cameraAPI } from '../services/api';
import { useToast } from '../components/ToastProvider';
import WebRTCPlayer from '../components/WebRTCPlayer';
import BoundingBoxOverlay from '../components/BoundingBoxOverlay';
import './CameraView.css';

const normalizePath = (path) => {
  if (!path) return '';
  return path.startsWith('/') ? path : `/${path}`;
};

const normalizeRtspPath = (path) => {
  if (!path) return '';
  const normalized = normalizePath(path);
  if (/stream=\d+\.sdp$/i.test(normalized) && !normalized.includes('?')) {
    return `${normalized}?`;
  }
  return normalized;
};

const buildCameraUrl = (camera) => {
  if (!camera) return '';

  if (camera.connection_type === 'dvr' && camera.dvr_url) {
    return camera.dvr_url;
  }

  if (!camera.ip_address) return '';
  const protocol = camera.protocol || 'rtsp';
  const port = camera.port ? `:${camera.port}` : '';
  const path = protocol === 'rtsp'
    ? normalizeRtspPath(camera.path || '')
    : normalizePath(camera.path || '');
  let creds = '';
  if (camera.username) {
    const user = encodeURIComponent(camera.username);
    const pass = camera.password && camera.password !== '****'
      ? `:${encodeURIComponent(camera.password)}`
      : '';
    creds = `${user}${pass}@`;
  }
  return `${protocol}://${creds}${camera.ip_address}${port}${path}`;
};

const buildGo2rtcUrl = (cameraUrl, format = 'mp4') => {
  if (!cameraUrl) return '';
  const endpoint = format === 'hls' ? 'stream.m3u8' : 'stream.mp4';
  return `/go2rtc/api/${endpoint}?src=${encodeURIComponent(cameraUrl)}`;
};

function CameraView() {
  const { id } = useParams();
  const [camera, setCamera] = useState(null);
  const [loading, setLoading] = useState(true);
  const [streamMode, setStreamMode] = useState('webrtc');
  const [go2rtcFormat, setGo2rtcFormat] = useState('hls');
  const [streamError, setStreamError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  const [overlayEnabled, setOverlayEnabled] = useState(false);
  const [muted, setMuted] = useState(true);
  const videoRef = useRef(null);
  const { addToast } = useToast();

  useEffect(() => {
    loadCamera();
  }, [id]);

  useEffect(() => {
    setStreamError('');
  }, [streamMode, id]);

  const loadCamera = async () => {
    try {
      const response = await cameraAPI.getById(id);
      setCamera(response.data);
    } catch (err) {
      console.error('Error loading camera:', err);
    } finally {
      setLoading(false);
    }
  };

  const toggleFullscreen = () => {
    const container = document.querySelector('.video-container');
    if (container?.requestFullscreen) {
      container.requestFullscreen();
    }
  };

  const takeSnapshot = () => {
    const video = videoRef.current;
    if (!video) {
      addToast('No video source available', 'error');
      return;
    }

    try {
      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth || video.clientWidth;
      canvas.height = video.videoHeight || video.clientHeight;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      canvas.toBlob((blob) => {
        if (!blob) return;
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `snapshot_${camera?.name || 'camera'}_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.jpg`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        addToast('Snapshot saved', 'success');
      }, 'image/jpeg', 0.95);
    } catch {
      addToast('Failed to capture snapshot', 'error');
    }
  };

  const cameraUrl = useMemo(() => buildCameraUrl(camera), [camera]);
  const go2rtcUrl = useMemo(() => buildGo2rtcUrl(cameraUrl, go2rtcFormat), [cameraUrl, go2rtcFormat]);
  const canDirect = camera?.protocol === 'http';

  const activeMode = useMemo(() => {
    if (streamMode === 'direct' && canDirect) return 'direct';
    if (streamMode === 'webrtc') return 'webrtc';
    if (streamMode === 'go2rtc') return 'go2rtc';
    return canDirect ? 'direct' : 'webrtc';
  }, [streamMode, canDirect]);

  const handleReload = () => {
    setStreamError('');
    setReloadKey((v) => v + 1);
  };

  const handleStreamError = (msg) => {
    if (typeof msg === 'string') {
      setStreamError(msg);
    } else if (activeMode === 'direct') {
      setStreamError('Direct connection to camera failed.');
    } else if (activeMode === 'go2rtc') {
      setStreamError('Failed to load stream via go2rtc.');
    } else {
      setStreamError('Stream connection error.');
    }
  };

  const handleStreamLoad = () => {
    setStreamError('');
  };

  const handleCopy = async (value, label) => {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      addToast(`${label} URL copied`, 'success');
    } catch {
      addToast('Failed to copy', 'error');
    }
  };

  if (loading) {
    return (
      <div className="page-container">
        <div className="loading"><div className="spinner"></div></div>
      </div>
    );
  }

  return (
    <div className="page-container">
      <div className="container">
        <div className="camera-view-header">
          <Link to="/" className="btn btn-secondary btn-sm">
            <FiArrowLeft /> Back
          </Link>
          <h1>{camera?.name || 'Camera'}</h1>
          <div className="btn-group">
            <button onClick={takeSnapshot} className="btn btn-sm btn-secondary" title="Snapshot">
              <FiCamera />
            </button>
            <button onClick={() => setMuted(!muted)} className="btn btn-sm btn-secondary" title={muted ? 'Unmute' : 'Mute'}>
              {muted ? <FiVolumeX /> : <FiVolume2 />}
            </button>
            <button onClick={toggleFullscreen} className="btn btn-sm btn-primary" title="Fullscreen">
              <FiMaximize />
            </button>
          </div>
        </div>

        {/* Stream mode selector */}
        <div className="stream-toolbar">
          <div className="stream-actions">
            <button
              className={`btn btn-sm ${activeMode === 'webrtc' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setStreamMode('webrtc')}
            >
              WebRTC
            </button>
            <button
              className={`btn btn-sm ${activeMode === 'go2rtc' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setStreamMode('go2rtc')}
            >
              Go2RTC
            </button>
            {activeMode === 'go2rtc' && (
              <>
                <span className="stream-divider"></span>
                <button
                  className={`btn btn-sm ${go2rtcFormat === 'hls' ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setGo2rtcFormat('hls')}
                >
                  HLS
                </button>
                <button
                  className={`btn btn-sm ${go2rtcFormat === 'mp4' ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setGo2rtcFormat('mp4')}
                >
                  MP4
                </button>
              </>
            )}
            {canDirect && (
              <button
                className={`btn btn-sm ${activeMode === 'direct' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setStreamMode('direct')}
              >
                Direct HTTP
              </button>
            )}
            <span className="stream-divider"></span>
            <button
              className={`btn btn-sm ${overlayEnabled ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setOverlayEnabled(!overlayEnabled)}
              title="Face detection overlay"
            >
              <FiSquare /> Detection
            </button>
            <button className="btn btn-sm btn-secondary" onClick={handleReload}>
              <FiRefreshCcw />
            </button>
          </div>

          {streamError && <div className="alert alert-error">{streamError}</div>}
        </div>

        {/* Video */}
        <div className="video-container" style={{ position: 'relative' }}>
          {activeMode === 'webrtc' ? (
            <WebRTCPlayer
              key={`webrtc-${reloadKey}`}
              cameraUrl={cameraUrl}
              onError={handleStreamError}
              onConnected={handleStreamLoad}
              className="video-stream"
            />
          ) : activeMode === 'go2rtc' ? (
            <video
              key={`go2rtc-${reloadKey}`}
              ref={videoRef}
              src={go2rtcUrl}
              className="video-stream"
              autoPlay
              muted={muted}
              controls
              playsInline
              onError={handleStreamError}
              onLoadedData={handleStreamLoad}
            />
          ) : activeMode === 'direct' && cameraUrl ? (
            <img
              key={`direct-${reloadKey}`}
              src={cameraUrl}
              alt="Camera Feed"
              className="video-stream"
              onError={handleStreamError}
              onLoad={handleStreamLoad}
            />
          ) : (
            <div className="video-placeholder">
              Stream URL not configured. Check camera settings.
            </div>
          )}

          {camera?.face_recognition_enabled && (
            <BoundingBoxOverlay
              cameraId={id}
              videoRef={videoRef}
              enabled={overlayEnabled}
            />
          )}
        </div>

        {/* Stream info */}
        <div className="stream-info">
          <div className="stream-info-row">
            <span className="stream-label">Camera URL:</span>
            <code className="stream-url">{cameraUrl || '-'}</code>
            <button
              className="btn btn-sm btn-secondary"
              onClick={() => handleCopy(cameraUrl, 'Camera')}
              disabled={!cameraUrl}
            >
              <FiCopy />
            </button>
          </div>

          {camera?.protocol === 'rtsp' && (
            <div className="stream-hint">
              WebRTC provides the lowest latency (~100ms). HLS has ~1s delay. MP4 offers best compatibility.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default CameraView;
