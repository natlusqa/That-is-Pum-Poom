import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  FiVideo, FiMapPin, FiWifi, FiUsers, FiActivity, FiPlus,
  FiCpu, FiRefreshCcw
} from 'react-icons/fi';
import { cameraAPI, employeeAPI, attendanceAPI, authAPI } from '../services/api';
import { useToast } from '../components/ToastProvider';
import './Dashboard.css';

function CameraThumbnail({ cameraId, isOnline }) {
  const [src, setSrc] = useState('');
  const [error, setError] = useState(false);

  const loadPoster = useCallback(async () => {
    const token = localStorage.getItem('token');
    const headers = token ? { Authorization: `Bearer ${token}` } : {};

    const fetchAsBlobUrl = async (url) => {
      const res = await fetch(url, { headers });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      setSrc(prev => {
        if (prev) URL.revokeObjectURL(prev);
        return URL.createObjectURL(blob);
      });
      setError(false);
    };

    try {
      if (isOnline) {
        await fetchAsBlobUrl(`/api/cameras/${cameraId}/poster`);
        return;
      }
    } catch {
      // fallback below
    }

    try {
      await fetchAsBlobUrl(`/api/cameras/${cameraId}/last-frame`);
    } catch {
      setError(true);
    }
  }, [cameraId, isOnline]);

  useEffect(() => {
    loadPoster();
    if (isOnline) {
      const interval = setInterval(loadPoster, 15000);
      return () => {
        clearInterval(interval);
        if (src) URL.revokeObjectURL(src);
      };
    } else {
      // For offline cameras, refresh last saved frame less often.
      const interval = setInterval(loadPoster, 60000);
      return () => {
        clearInterval(interval);
        if (src) URL.revokeObjectURL(src);
      };
    }
  }, [loadPoster]);

  if (!isOnline || error || !src) {
    return (
      <div className="camera-thumb-placeholder">
        <FiVideo size={32} />
        {!isOnline && <span>Не в сети</span>}
      </div>
    );
  }

  return <img src={src} alt="Поток с камеры" className="camera-thumb-img" />;
}

function Dashboard() {
  const [cameras, setCameras] = useState([]);
  const [employeeCount, setEmployeeCount] = useState(0);
  const [todayEvents, setTodayEvents] = useState(0);
  const [loading, setLoading] = useState(true);
  const { addToast } = useToast();
  const currentUser = authAPI.getCurrentUser();
  const canManageCameras = ['admin', 'super_admin'].includes(currentUser?.role);

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    try {
      const [camsRes, empsRes] = await Promise.all([
        cameraAPI.getAll(),
        employeeAPI.getAll(),
      ]);
      setCameras(camsRes.data);
      setEmployeeCount(empsRes.data.length);

      const today = new Date().toISOString().split('T')[0];
      try {
        const statsRes = await attendanceAPI.getStats({
          date_from: today,
          date_to: today,
        });
        setTodayEvents(statsRes.data?.total_logs || 0);
      } catch {
        // Stats may fail if no logs yet
      }
    } catch {
      addToast('Не удалось загрузить данные панели', 'error');
    } finally {
      setLoading(false);
    }
  };

  const onlineCameras = cameras.filter(c => c.is_online).length;
  const aiCameras = cameras.filter(c => c.face_recognition_enabled).length;

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
        <div className="page-header flex-between">
          <h1><FiActivity /> Панель</h1>
          <div className="btn-group">
            <button className="btn btn-secondary btn-sm" onClick={loadDashboard}>
              <FiRefreshCcw /> Обновить
            </button>
            {canManageCameras && (
              <Link to="/cameras" className="btn btn-primary btn-sm">
                <FiPlus /> Добавить камеру
              </Link>
            )}
          </div>
        </div>

        {/* Stats */}
        <div className="dashboard-stats">
          <div className="stat-card">
            <div className="stat-icon stat-icon-blue"><FiVideo /></div>
            <div className="stat-content">
              <div className="stat-label">Камеры</div>
              <div className="stat-value">{cameras.length}</div>
              <div className="stat-sub">{onlineCameras} в сети</div>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon stat-icon-green"><FiWifi /></div>
            <div className="stat-content">
              <div className="stat-label">Онлайн</div>
              <div className="stat-value">{onlineCameras}</div>
              <div className="stat-sub">из {cameras.length} всего</div>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon stat-icon-purple"><FiUsers /></div>
            <div className="stat-content">
              <div className="stat-label">Сотрудники</div>
              <div className="stat-value">{employeeCount}</div>
              <div className="stat-sub">зарегистрировано</div>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon stat-icon-amber"><FiActivity /></div>
            <div className="stat-content">
              <div className="stat-label">Обнаружения</div>
              <div className="stat-value">{todayEvents}</div>
              <div className="stat-sub">сегодня</div>
            </div>
          </div>
        </div>

        {/* Camera Grid */}
        <div className="dashboard-section-header">
          <h2><FiVideo /> Камеры в реальном времени</h2>
          <div className="flex gap-2">
            {aiCameras > 0 && (
              <span className="badge badge-info"><FiCpu size={10} /> {aiCameras} AI</span>
            )}
            {canManageCameras && (
              <Link to="/cameras" className="btn btn-ghost btn-sm">Управление</Link>
            )}
          </div>
        </div>

        {cameras.length === 0 ? (
          <div className="empty-state">
            <FiVideo size={56} />
            <h2>Камеры не добавлены</h2>
            <p>Добавьте первую камеру, чтобы начать мониторинг</p>
            {canManageCameras && (
              <Link to="/cameras" className="btn btn-primary mt-2">
                <FiPlus /> Добавить камеру
              </Link>
            )}
          </div>
        ) : (
          <div className="camera-grid">
            {cameras.map((camera) => (
              <Link key={camera.id} to={`/camera/${camera.id}`} className="camera-card">
                <div className="camera-preview">
                  <CameraThumbnail cameraId={camera.id} isOnline={camera.is_online} />
                  {camera.face_recognition_enabled && (
                    <span className="badge badge-info camera-badge"><FiCpu size={10} /> AI</span>
                  )}
                  <div className="camera-status-indicator">
                    <span className={`status-dot ${camera.is_online ? 'status-dot-online' : 'status-dot-offline'}`} />
                    {camera.is_online ? 'В сети' : 'Не в сети'}
                  </div>
                </div>
                <div className="camera-info">
                  <h3>{camera.name}</h3>
                  <div className="camera-meta">
                    {camera.location && <span><FiMapPin size={12} /> {camera.location}</span>}
                    <span><FiWifi size={12} /> {camera.ip_address}</span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default Dashboard;
