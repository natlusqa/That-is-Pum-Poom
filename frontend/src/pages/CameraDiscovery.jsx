import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { FiArrowLeft, FiPlay, FiLoader, FiRefreshCcw, FiPlus } from 'react-icons/fi';
import { cameraAPI } from '../services/api';
import { useToast } from '../components/ToastProvider';
import './CameraDiscovery.css';

function CameraDiscovery() {
  const [network, setNetwork] = useState('192.168.1.0/24');
  const [scanning, setScanning] = useState(false);
  const [results, setResults] = useState([]);
  const [expanding, setExpanding] = useState({});
  const [filter, setFilter] = useState('all');
  const [addingcameras, setAddingCameras] = useState({});
  const [addingAll, setAddingAll] = useState(false);
  const [scanProgress, setScanProgress] = useState(0);
  const [scanMessage, setScanMessage] = useState('');
  const { addToast } = useToast();

  useEffect(() => {
    checkScanStatus();
    const interval = setInterval(checkScanStatus, 2000);
    return () => clearInterval(interval);
  }, []);

  const checkScanStatus = async () => {
    try {
      const response = await fetch('/api/camera-discovery/status', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      const data = await response.json();
      setScanning(data.scanning);
      setResults(data.results || []);
      setScanProgress(data.progress || 0);
      setScanMessage(data.message || '');
    } catch (err) {
      console.error('Failed to get discovery status:', err);
    }
  };

  const startScan = async () => {
    try {
      setScanning(true);
      setResults([]);
      const response = await fetch('/api/camera-discovery/scan', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({ network })
      });

      if (!response.ok) throw new Error('Failed to start scan');

      addToast('Сканирование сети начато...', 'info');

      // Poll for status
      const statusInterval = setInterval(async () => {
        const statusResponse = await fetch('/api/camera-discovery/status', {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          }
        });
        const statusData = await statusResponse.json();
        setScanning(statusData.scanning);
        setResults(statusData.results || []);

        if (!statusData.scanning) {
          clearInterval(statusInterval);
          addToast(`Сканирование завершено. Найдено: ${statusData.found_count} точек подключения`, 'success');
        }
      }, 2000);
    } catch (err) {
      console.error('Scan error:', err);
      addToast('Ошибка сканирования сети', 'error');
      setScanning(false);
    }
  };

  const addCamera = async (cameraInfo) => {
    try {
      setAddingCameras(prev => ({ ...prev, [cameraInfo.stream_url]: true }));

      const response = await fetch('/api/camera-discovery/add', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          name: `Камера ${cameraInfo.ip_address}:${cameraInfo.port}`,
          ip_address: cameraInfo.ip_address,
          port: cameraInfo.port,
          username: cameraInfo.username || 'admin',
          password: cameraInfo.password || '',
          protocol: cameraInfo.protocol || 'rtsp',
          path: cameraInfo.path || '/stream',
          location: ''
        })
      });

      if (!response.ok) throw new Error('Failed to add camera');

      const data = await response.json();
      addToast(`Камера "${data.name}" добавлена`, 'success');

      // Remove from discovered list
      setResults(prev => prev.filter(r => r.stream_url !== cameraInfo.stream_url));
    } catch (err) {
      console.error('Add camera error:', err);
      addToast('Ошибка при добавлении камеры', 'error');
    } finally {
      setAddingCameras(prev => ({ ...prev, [cameraInfo.stream_url]: false }));
    }
  };

  const addAllCameras = async () => {
    try {
      setAddingAll(true);
      const response = await fetch('/api/camera-discovery/add-all', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (!response.ok) throw new Error('Failed to add cameras');

      const data = await response.json();
      addToast(`Добавлено ${data.added_count} камер (пропущено дубликатов: ${data.skipped_count})`, 'success');
      setResults([]);
    } catch (err) {
      console.error('Add all cameras error:', err);
      addToast('Ошибка при добавлении камер', 'error');
    } finally {
      setAddingAll(false);
    }
  };

  const filteredResults = results.filter(r => {
    if (filter === 'rtsp') return r.protocol === 'rtsp';
    if (filter === 'http') return r.protocol === 'http';
    return true;
  });

  const groupedByIp = {};
  filteredResults.forEach(r => {
    if (!groupedByIp[r.ip_address]) {
      groupedByIp[r.ip_address] = [];
    }
    groupedByIp[r.ip_address].push(r);
  });

  const toggleExpand = (ip) => {
    setExpanding(prev => ({
      ...prev,
      [ip]: !prev[ip]
    }));
  };

  return (
    <div className="page-container">
      <div className="container">
        <div className="discovery-header">
          <Link to="/" className="btn btn-secondary">
            <FiArrowLeft /> Назад
          </Link>
          <h1>Обнаружение камер</h1>
        </div>

        <div className="discovery-panel">
          <h3>Сканирование сети</h3>
          <div className="network-input-group">
            <input
              type="text"
              value={network}
              onChange={(e) => setNetwork(e.target.value)}
              placeholder="192.168.1.0/24"
              disabled={scanning}
              className="network-input"
            />
            <button
              onClick={startScan}
              disabled={scanning}
              className="btn btn-primary"
            >
              {scanning ? (
                <>
                  <FiLoader className="spin" /> Сканирование...
                </>
              ) : (
                <>
                  <FiPlay /> Начать сканирование
                </>
              )}
            </button>
          </div>
          <p className="network-hint">
            Введите сеть в нотации CIDR (например: 192.168.1.0/24)
          </p>
        </div>

        {filteredResults.length > 0 && (
          <div className="discovery-results">
            <div className="results-header">
              <h3>Найдено точек подключения: {filteredResults.length}</h3>
              {filteredResults.filter(r => r.verified).length > 0 && (
                <button
                  onClick={addAllCameras}
                  disabled={addingAll}
                  className="btn btn-primary"
                  style={{ marginBottom: 8 }}
                >
                  {addingAll ? (
                    <><FiLoader className="spin" /> Добавляю...</>
                  ) : (
                    <><FiPlus /> Добавить все ({filteredResults.filter(r => r.verified).length})</>
                  )}
                </button>
              )}
              <div className="filter-buttons">
                <button
                  className={`btn btn-sm ${filter === 'all' ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setFilter('all')}
                >
                  Все ({results.length})
                </button>
                <button
                  className={`btn btn-sm ${filter === 'rtsp' ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setFilter('rtsp')}
                >
                  RTSP ({results.filter(r => r.protocol === 'rtsp').length})
                </button>
                <button
                  className={`btn btn-sm ${filter === 'http' ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setFilter('http')}
                >
                  HTTP ({results.filter(r => r.protocol === 'http').length})
                </button>
              </div>
            </div>

            {Object.entries(groupedByIp).map(([ip, cameras]) => (
              <div key={ip} className="camera-group">
                <button
                  className="group-header"
                  onClick={() => toggleExpand(ip)}
                >
                  <span className="group-title">
                    {expanding[ip] ? '▼' : '▶'} {ip} ({cameras.length} опций)
                  </span>
                </button>

                {expanding[ip] && (
                  <div className="group-content">
                    {cameras.map((camera, idx) => (
                      <div key={idx} className="camera-item">
                        <div className="camera-info">
                          <div className="camera-addr">
                            <span className="protocol-badge">{camera.protocol.toUpperCase()}</span>
                            <span className="port">:{camera.port}</span>
                            <span className="path">{camera.path}</span>
                          </div>
                          <div className="camera-url">
                            <small>{camera.stream_url}</small>
                          </div>
                        </div>
                        <button
                          onClick={() => addCamera(camera)}
                          disabled={addingCameras[camera.stream_url]}
                          className="btn btn-sm btn-primary"
                          title="Добавить камеру"
                        >
                          {addingCameras[camera.stream_url] ? (
                            <>
                              <FiLoader className="spin" /> Добавляю...
                            </>
                          ) : (
                            <>
                              <FiPlus /> Добавить
                            </>
                          )}
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {!scanning && results.length === 0 && (
          <div className="no-results">
            <p>💡 Нажмите "Начать сканирование" для поиска камер в сети</p>
          </div>
        )}

        {scanning && (
          <div className="scanning-state">
            <div className="spinner"></div>
            <p>Сканирование сети {network}...</p>
            <div style={{ width: '100%', maxWidth: 400, margin: '12px auto' }}>
              <div style={{ background: 'var(--bg-tertiary, #333)', borderRadius: 6, height: 8, overflow: 'hidden' }}>
                <div style={{
                  width: `${scanProgress}%`,
                  height: '100%',
                  background: 'var(--accent, #4f8cff)',
                  borderRadius: 6,
                  transition: 'width 0.3s ease'
                }} />
              </div>
              <small style={{ marginTop: 4, display: 'block' }}>{scanProgress}% — {scanMessage}</small>
            </div>
            {results.length > 0 && <small>Уже найдено: {results.filter(r => r.verified).length} камер</small>}
          </div>
        )}
      </div>
    </div>
  );
}

export default CameraDiscovery;
