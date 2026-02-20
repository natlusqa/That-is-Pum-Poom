import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { FiArrowLeft, FiMaximize, FiRefreshCcw, FiCopy, FiSquare } from 'react-icons/fi';
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
  if (!camera?.ip_address) return '';
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

const buildGo2rtcUrl = (cameraUrl) => {
  if (!cameraUrl) return '';
  return `/go2rtc/api/stream.mp4?src=${encodeURIComponent(cameraUrl)}`;
};

function CameraView() {
  const { id } = useParams();
  const [camera, setCamera] = useState(null);
  const [loading, setLoading] = useState(true);
  const [streamMode, setStreamMode] = useState('webrtc');
  const [streamError, setStreamError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  const [overlayEnabled, setOverlayEnabled] = useState(false);
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
    if (container && container.requestFullscreen) {
      container.requestFullscreen();
    }
  };

  const cameraUrl = useMemo(() => buildCameraUrl(camera), [camera]);
  const go2rtcUrl = useMemo(() => buildGo2rtcUrl(cameraUrl), [cameraUrl]);
  const canDirect = camera?.protocol === 'http';

  const activeMode = useMemo(() => {
    if (streamMode === 'direct' && canDirect) return 'direct';
    if (streamMode === 'webrtc') return 'webrtc';
    if (streamMode === 'go2rtc') return 'go2rtc';
    return canDirect ? 'direct' : 'webrtc';
  }, [streamMode, canDirect]);

  const handleReload = () => {
    setStreamError('');
    setReloadKey((value) => value + 1);
  };

  const handleStreamError = (msg) => {
    if (typeof msg === 'string') {
      setStreamError(msg);
    } else if (activeMode === 'direct') {
      setStreamError('Не удалось подключиться напрямую к камере.');
    } else if (activeMode === 'go2rtc') {
      setStreamError('Не удалось загрузить поток через go2rtc.');
    } else {
      setStreamError('Ошибка подключения к потоку.');
    }
  };

  const handleStreamLoad = () => {
    setStreamError('');
  };

  const handleCopy = async (value, label) => {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      addToast(`Ссылка "${label}" скопирована`, 'success');
    } catch (err) {
      addToast('Не удалось скопировать ссылку', 'error');
    }
  };

  if (loading) {
    return (
      <div className="page-container">
        <div className="loading">
          <div className="spinner"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container">
      <div className="container">
        <div className="camera-view-header">
          <Link to="/" className="btn btn-secondary">
            <FiArrowLeft /> Назад
          </Link>
          <h1>{camera?.name || 'Камера'}</h1>
          <div className="header-actions">
            <button onClick={toggleFullscreen} className="btn btn-primary">
              <FiMaximize /> Полный экран
            </button>
          </div>
        </div>

        <div className="stream-toolbar">
          <div className="stream-actions">
            <button
              type="button"
              className={`btn btn-sm ${activeMode === 'webrtc' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setStreamMode('webrtc')}
            >
              WebRTC
            </button>
            <button
              type="button"
              className={`btn btn-sm ${activeMode === 'go2rtc' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setStreamMode('go2rtc')}
            >
              Go2RTC MP4
            </button>
            {canDirect && (
              <button
                type="button"
                className={`btn btn-sm ${activeMode === 'direct' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setStreamMode('direct')}
              >
                Прямой HTTP
              </button>
            )}
            <span className="stream-divider">|</span>
            <button
              type="button"
              className={`btn btn-sm ${overlayEnabled ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setOverlayEnabled(!overlayEnabled)}
              title="Обводка детекций"
            >
              <FiSquare /> Детекция
            </button>
            <button type="button" className="btn btn-sm btn-secondary" onClick={handleReload}>
              <FiRefreshCcw /> Обновить
            </button>
          </div>

          {streamError && (
            <div className="alert alert-error">
              {streamError}
            </div>
          )}
        </div>

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
              muted
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
              Ссылка на поток не задана. Проверьте настройки камеры.
            </div>
          )}

          {/* Bounding Box Overlay */}
          {camera?.face_recognition_enabled && (
            <BoundingBoxOverlay
              cameraId={id}
              videoRef={videoRef}
              enabled={overlayEnabled}
            />
          )}
        </div>

        <div className="stream-info">
          <div className="stream-info-row">
            <span className="stream-label">
              Ссылка камеры ({camera?.protocol?.toUpperCase() || 'RTSP'}):
            </span>
            <code className="stream-url">{cameraUrl || '—'}</code>
            <button
              type="button"
              className="btn btn-sm btn-secondary"
              onClick={() => handleCopy(cameraUrl, 'камера')}
              disabled={!cameraUrl}
            >
              <FiCopy /> Копировать
            </button>
          </div>

          <div className="stream-info-row">
            <span className="stream-label">Go2RTC MP4 URL:</span>
            <code className="stream-url">{go2rtcUrl || '—'}</code>
            <button
              type="button"
              className="btn btn-sm btn-secondary"
              onClick={() => handleCopy(go2rtcUrl, 'Go2RTC')}
              disabled={!go2rtcUrl}
            >
              <FiCopy /> Копировать
            </button>
          </div>

          {camera?.protocol === 'rtsp' && (
            <div className="stream-hint">
              WebRTC — минимальная задержка. Go2RTC MP4 — совместимость с любым браузером.
            </div>
          )}
        </div>

        {camera?.face_recognition_enabled && (
          <div className="alert alert-info mt-3">
            На этой камере включено распознавание лиц. Нажмите кнопку "Детекция" для отображения обводок.
          </div>
        )}
      </div>
    </div>
  );
}

export default CameraView;
