import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  FiVideo, FiMapPin, FiWifi, FiUsers, FiActivity, FiPlus,
  FiCpu, FiRefreshCcw
} from 'react-icons/fi';
import { cameraAPI, employeeAPI, attendanceAPI } from '../services/api';
import { useToast } from '../components/ToastProvider';
import './Dashboard.css';

function CameraThumbnail({ cameraId, isOnline }) {
  const [src, setSrc] = useState('');
  const [error, setError] = useState(false);

  const loadPoster = useCallback(() => {
    if (!isOnline) return;
    const token = localStorage.getItem('token');
    fetch(`/api/cameras/${cameraId}/poster`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(res => {
        if (!res.ok) throw new Error('Failed');
        return res.blob();
      })
      .then(blob => {
        setSrc(prev => {
          if (prev) URL.revokeObjectURL(prev);
          return URL.createObjectURL(blob);
        });
        setError(false);
      })
      .catch(() => setError(true));
  }, [cameraId, isOnline]);

  useEffect(() => {
    loadPoster();
    if (isOnline) {
      const interval = setInterval(loadPoster, 15000);
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
        {!isOnline && <span>Offline</span>}
      </div>
    );
  }

  return <img src={src} alt="Camera feed" className="camera-thumb-img" />;
}

function Dashboard() {
  const [cameras, setCameras] = useState([]);
  const [employeeCount, setEmployeeCount] = useState(0);
  const [todayEvents, setTodayEvents] = useState(0);
  const [loading, setLoading] = useState(true);
  const { addToast } = useToast();

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
      addToast('Failed to load dashboard data', 'error');
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
          <h1><FiActivity /> Dashboard</h1>
          <div className="btn-group">
            <button className="btn btn-secondary btn-sm" onClick={loadDashboard}>
              <FiRefreshCcw /> Refresh
            </button>
            <Link to="/cameras" className="btn btn-primary btn-sm">
              <FiPlus /> Add Camera
            </Link>
          </div>
        </div>

        {/* Stats */}
        <div className="dashboard-stats">
          <div className="stat-card">
            <div className="stat-icon stat-icon-blue"><FiVideo /></div>
            <div className="stat-content">
              <div className="stat-label">Cameras</div>
              <div className="stat-value">{cameras.length}</div>
              <div className="stat-sub">{onlineCameras} online</div>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon stat-icon-green"><FiWifi /></div>
            <div className="stat-content">
              <div className="stat-label">Online</div>
              <div className="stat-value">{onlineCameras}</div>
              <div className="stat-sub">of {cameras.length} total</div>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon stat-icon-purple"><FiUsers /></div>
            <div className="stat-content">
              <div className="stat-label">Employees</div>
              <div className="stat-value">{employeeCount}</div>
              <div className="stat-sub">registered</div>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon stat-icon-amber"><FiActivity /></div>
            <div className="stat-content">
              <div className="stat-label">Detections</div>
              <div className="stat-value">{todayEvents}</div>
              <div className="stat-sub">today</div>
            </div>
          </div>
        </div>

        {/* Camera Grid */}
        <div className="dashboard-section-header">
          <h2><FiVideo /> Live Cameras</h2>
          <div className="flex gap-2">
            {aiCameras > 0 && (
              <span className="badge badge-info"><FiCpu size={10} /> {aiCameras} AI</span>
            )}
            <Link to="/cameras" className="btn btn-ghost btn-sm">Manage</Link>
          </div>
        </div>

        {cameras.length === 0 ? (
          <div className="empty-state">
            <FiVideo size={56} />
            <h2>No cameras added</h2>
            <p>Add your first camera to start monitoring</p>
            <Link to="/cameras" className="btn btn-primary mt-2">
              <FiPlus /> Add Camera
            </Link>
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
                    {camera.is_online ? 'Online' : 'Offline'}
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
