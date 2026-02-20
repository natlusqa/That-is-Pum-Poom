import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { FiVideo, FiMapPin, FiWifi, FiEye, FiUsers, FiActivity } from 'react-icons/fi';
import { cameraAPI, employeeAPI, attendanceAPI } from '../services/api';
import { useToast } from '../components/ToastProvider';
import './Dashboard.css';

function Dashboard() {
  const [cameras, setCameras] = useState([]);
  const [employeeCount, setEmployeeCount] = useState(0);
  const [todayEvents, setTodayEvents] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
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

      // Load today's stats
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
    } catch (err) {
      setError('Ошибка загрузки данных');
      addToast('Ошибка загрузки данных', 'error');
    } finally {
      setLoading(false);
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
        <div className="page-header">
          <h1><FiVideo /> Камеры видеонаблюдения</h1>
        </div>

        <div className="grid grid-3 dashboard-stats">
          <div className="card">
            <div className="card-title"><FiVideo /> Камеры</div>
            <div className="card-value">{cameras.length}</div>
            <div className="card-sub">Всего подключенных</div>
          </div>
          <div className="card">
            <div className="card-title"><FiUsers /> Сотрудники</div>
            <div className="card-value">{employeeCount}</div>
            <div className="card-sub">Зарегистрировано</div>
          </div>
          <div className="card">
            <div className="card-title"><FiActivity /> События сегодня</div>
            <div className="card-value">{todayEvents}</div>
            <div className="card-sub">Детекций за сегодня</div>
          </div>
        </div>

        {error && <div className="alert alert-error">{error}</div>}

        {cameras.length === 0 ? (
          <div className="empty-state">
            <FiVideo size={64} />
            <h2>Камеры не добавлены</h2>
            <p>Обратитесь к администратору для добавления камер</p>
          </div>
        ) : (
          <div className="grid grid-3">
            {cameras.map((camera) => (
              <Link
                key={camera.id}
                to={`/camera/${camera.id}`}
                className="camera-card"
              >
                <div className="camera-preview">
                  <FiEye size={48} />
                  {camera.face_recognition_enabled && (
                    <span className="badge badge-info camera-badge">
                      Распознавание лиц
                    </span>
                  )}
                </div>
                <div className="camera-info">
                  <h3>{camera.name}</h3>
                  <div className="camera-meta">
                    <span><FiMapPin size={14} /> {camera.location || 'Не указано'}</span>
                    <span><FiWifi size={14} /> {camera.ip_address}</span>
                  </div>
                  <span className={`badge ${camera.is_online ? 'badge-success' : 'badge-warning'}`}>
                    {camera.is_online ? 'Онлайн' : 'Оффлайн'}
                  </span>
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
