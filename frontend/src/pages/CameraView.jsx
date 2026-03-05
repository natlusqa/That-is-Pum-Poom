import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { FiArrowLeft, FiMaximize, FiMinimize, FiRefreshCcw, FiCamera, FiVolume2, FiVolumeX, FiSquare } from 'react-icons/fi';
import { cameraAPI } from '../services/api';
import { useToast } from '../components/ToastProvider';
import MSEPlayer from '../components/MSEPlayer';
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
  if (camera.connection_type === 'dvr' && camera.dvr_url) return camera.dvr_url;
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
      ? encodeURIComponent(camera.password)
      : '';
    creds = `${user}:${pass}@`;
  }
  return `${protocol}://${creds}${camera.ip_address}${port}${path}`;
};

function CameraView() {
  const { id } = useParams();
  const [camera, setCamera] = useState(null);
  const [loading, setLoading] = useState(true);
  const [streamError, setStreamError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  const [overlayEnabled, setOverlayEnabled] = useState(false);
  const [muted, setMuted] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const videoContainerRef = useRef(null);
  const { addToast } = useToast();

  useEffect(() => {
    loadCamera();
  }, [id]);

  const loadCamera = async () => {
    try {
      const response = await cameraAPI.getById(id);
      const cam = response.data;
      setCamera(cam);

      // Pre-warm: trigger go2rtc to start RTSP connection early (read-only, does NOT overwrite stream config)
      fetch(`/go2rtc/api/frame.jpeg?src=camera_${id}_raw`).catch(() => {});
    } catch (err) {
      console.error('Error loading camera:', err);
      addToast('Не удалось загрузить камеру', 'error');
    } finally {
      setLoading(false);
    }
  };

  const toggleFullscreen = async () => {
    const container = videoContainerRef.current;
    if (!container) return;

    try {
      if (!document.fullscreenElement) {
        await container.requestFullscreen();
        setIsFullscreen(true);
      } else {
        await document.exitFullscreen();
        setIsFullscreen(false);
      }
    } catch { /* ignore */ }
  };

  useEffect(() => {
    const handleFsChange = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', handleFsChange);
    return () => document.removeEventListener('fullscreenchange', handleFsChange);
  }, []);

  const takeSnapshot = () => {
    const video = videoContainerRef.current?.querySelector('video');
    if (!video || !video.videoWidth) {
      addToast('Нет видео для снимка', 'error');
      return;
    }

    try {
      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
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
        addToast('Снимок сохранен', 'success');
      }, 'image/jpeg', 0.95);
    } catch {
      addToast('Не удалось сделать снимок', 'error');
    }
  };

  const cameraUrl = useMemo(() => buildCameraUrl(camera), [camera]);

  const handleReload = () => {
    setStreamError('');
    setReloadKey((v) => v + 1);
  };

  const handleStreamError = (msg) => {
    setStreamError(typeof msg === 'string' ? msg : 'Ошибка подключения к потоку');
  };

  const handleStreamConnected = () => {
    setStreamError('');
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
        {/* Header */}
        <div className="camera-view-header">
          <Link to="/" className="btn btn-secondary btn-sm">
            <FiArrowLeft /> Назад
          </Link>
          <h1>{camera?.name || 'Камера'}</h1>
          <div className="camera-view-location">
            {camera?.location && <span className="camera-location-text">{camera.location}</span>}
          </div>
        </div>

        {/* Error bar */}
        {streamError && (
          <div className="alert alert-error" style={{ marginBottom: 12 }}>
            {streamError}
            <button className="alert-close" onClick={() => setStreamError('')}>&times;</button>
          </div>
        )}

        {/* Video feed */}
        <div className="video-container" ref={videoContainerRef}>
          {cameraUrl ? (
            <>
              <MSEPlayer
                key={`mse-${reloadKey}`}
                cameraUrl={cameraUrl}
                cameraId={id}
                muted={muted}
                onError={handleStreamError}
                onConnected={handleStreamConnected}
                className="video-stream"
              />

              {camera?.face_recognition_enabled && (
                <BoundingBoxOverlay
                  cameraId={id}
                  videoRef={{ current: videoContainerRef.current?.querySelector('video') }}
                  enabled={overlayEnabled}
                />
              )}
            </>
          ) : (
            <div className="video-placeholder">
              URL потока не настроен. Проверьте параметры камеры.
            </div>
          )}

          {/* Floating toolbar */}
          <div className="video-toolbar">
            {camera?.face_recognition_enabled && (
              <button
                className={`video-toolbar-btn ${overlayEnabled ? 'active' : ''}`}
                onClick={() => setOverlayEnabled(!overlayEnabled)}
                title="Показывать рамки распознавания"
              >
                <FiSquare size={16} />
              </button>
            )}
            <button
              className="video-toolbar-btn"
              onClick={takeSnapshot}
              title="Снимок"
            >
              <FiCamera size={16} />
            </button>
            <button
              className="video-toolbar-btn"
              onClick={() => setMuted(!muted)}
              title={muted ? 'Включить звук' : 'Выключить звук'}
            >
              {muted ? <FiVolumeX size={16} /> : <FiVolume2 size={16} />}
            </button>
            <button
              className="video-toolbar-btn"
              onClick={handleReload}
              title="Перезагрузить поток"
            >
              <FiRefreshCcw size={16} />
            </button>
            <button
              className="video-toolbar-btn"
              onClick={toggleFullscreen}
              title={isFullscreen ? 'Выйти из полного экрана' : 'Полный экран'}
            >
              {isFullscreen ? <FiMinimize size={16} /> : <FiMaximize size={16} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default CameraView;
