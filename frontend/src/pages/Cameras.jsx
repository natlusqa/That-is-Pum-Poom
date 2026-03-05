import React, { useState, useEffect, useRef, useCallback } from 'react';
import { FiVideo, FiPlus, FiEdit2, FiTrash2, FiEye, FiSearch, FiCheckCircle, FiXCircle, FiX, FiWifi, FiLock } from 'react-icons/fi';
import { Link } from 'react-router-dom';
import { cameraAPI, discoveryAPI } from '../services/api';
import { useToast } from '../components/ToastProvider';

const STAGE_LABELS = {
  starting: 'Инициализация',
  network: 'Определение сетей',
  onvif: 'Поиск ONVIF',
  arp: 'Сканирование ARP',
  ping: 'Пинг-сканирование',
  scan: 'Анализ хостов',
  ports: 'Проверка портов',
  verify: 'Проверка потоков',
  done: 'Завершено',
};

function Cameras() {
  const [cameras, setCameras] = useState([]);
  const [previewUrls, setPreviewUrls] = useState({});
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingCamera, setEditingCamera] = useState(null);
  const [error, setError] = useState('');
  const [modalError, setModalError] = useState('');
  const [success, setSuccess] = useState('');
  const [deletingId, setDeletingId] = useState(null);
  const { addToast } = useToast();
  const [formData, setFormData] = useState({
    name: '',
    ip_address: '',
    port: 554,
    username: '',
    password: '',
    protocol: 'rtsp',
    path: '/stream',
    location: '',
    face_recognition_enabled: false,
    rtsp_url: '',
  });
  const [inputMode, setInputMode] = useState('link');

  // Auto-discovery state
  const [showDiscovery, setShowDiscovery] = useState(false);
  const [discoveryState, setDiscoveryState] = useState({
    scanning: false,
    stage: '',
    message: '',
    progress: 0,
    results: [],
    found_count: 0,
    error: null,
  });
  const [addingAll, setAddingAll] = useState(false);
  const [addingOne, setAddingOne] = useState({});
  const [discoveryNetwork, setDiscoveryNetwork] = useState('192.168.1.0/24');
  const pollRef = useRef(null);

  useEffect(() => {
    loadCameras();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      setPreviewUrls((prev) => {
        Object.values(prev).forEach((url) => {
          if (url) URL.revokeObjectURL(url);
        });
        return {};
      });
    };
  }, []);

  const loadCameraPreviews = useCallback(async (cameraList) => {
    const token = localStorage.getItem('token');
    if (!token || !Array.isArray(cameraList) || cameraList.length === 0) {
      setPreviewUrls({});
      return;
    }

    const next = {};
    await Promise.all(cameraList.map(async (cam) => {
      try {
        const resp = await fetch(`/api/cameras/${cam.id}/poster`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!resp.ok) return;
        const blob = await resp.blob();
        if (!blob || blob.size === 0) return;
        next[cam.id] = URL.createObjectURL(blob);
      } catch {
        // ignore per-camera preview errors
      }
    }));

    setPreviewUrls((prev) => {
      Object.values(prev).forEach((url) => {
        if (url) URL.revokeObjectURL(url);
      });
      return next;
    });
  }, []);

  const loadCameras = async () => {
    try {
      const response = await cameraAPI.getAll();
      setCameras(response.data);
      await loadCameraPreviews(response.data);
      if (Array.isArray(response.data) && response.data.length > 0) {
        const firstIp = response.data.find((c) => c?.ip_address)?.ip_address || '';
        const m = firstIp.match(/^(\d+)\.(\d+)\.(\d+)\.(\d+)$/);
        if (m) {
          setDiscoveryNetwork(`${m[1]}.${m[2]}.${m[3]}.0/24`);
        }
      }
    } catch (err) {
      setError('Не удалось загрузить камеры');
      addToast('Не удалось загрузить камеры', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!Array.isArray(cameras) || cameras.length === 0) return undefined;
    const refreshMs = 40 * 60 * 1000; // 40 minutes
    const intervalId = setInterval(() => {
      loadCameraPreviews(cameras);
    }, refreshMs);
    return () => clearInterval(intervalId);
  }, [cameras, loadCameraPreviews]);

  // ── Discovery polling ──────────────────────────────────────
  const startPolling = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const res = await discoveryAPI.getStatus();
        const data = res.data;
        setDiscoveryState(data);
        if (!data.scanning) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } catch {
        // ignore polling errors
      }
    }, 1500);
  }, []);

  const handleStartDiscovery = async () => {
    try {
      const network = (discoveryNetwork || '').trim();
      if (!network) {
        addToast('Укажите сеть в формате CIDR, например 192.168.10.0/24', 'error');
        return;
      }
      setDiscoveryState(prev => ({ ...prev, scanning: true, progress: 0, results: [], error: null, stage: 'starting', message: 'Инициализация...' }));
      await discoveryAPI.startScan({ network });
      startPolling();
    } catch (err) {
      const msg = err.response?.data?.error || 'Не удалось запустить автопоиск';
      addToast(msg, 'error');
      setDiscoveryState(prev => ({ ...prev, scanning: false, error: msg }));
    }
  };

  const handleStopDiscovery = async () => {
    try {
      await discoveryAPI.stopScan();
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
      setDiscoveryState(prev => ({ ...prev, scanning: false }));
      addToast('Автопоиск остановлен', 'info');
    } catch {
      // ignore
    }
  };

  const handleAddAllCameras = async () => {
    try {
      setAddingAll(true);
      const allResults = discoveryState.results || [];
      if (!allResults.length) {
        addToast('Нет найденных камер для добавления', 'info');
        return;
      }

      const authRequired = allResults.filter((c) => c.auth_required && !c.verified);
      let sharedUsername = '';
      let sharedPassword = '';
      if (authRequired.length > 0) {
        const userInput = window.prompt(
          `Найдено ${authRequired.length} защищенных камер.\nВведите логин для всех:`,
          'admin'
        );
        if (userInput === null || !userInput.trim()) {
          addToast('Добавление отменено: логин не указан', 'info');
          return;
        }
        const passInput = window.prompt('Введите пароль для всех защищенных камер:', '');
        if (passInput === null) {
          addToast('Добавление отменено', 'info');
          return;
        }
        sharedUsername = userInput.trim();
        sharedPassword = passInput;
      }

      const res = await discoveryAPI.addAll({
        include_auth_required: authRequired.length > 0,
        username: sharedUsername,
        password: sharedPassword,
      });
      const added = res.data?.added_count || 0;
      const updated = res.data?.updated_count || 0;
      const skipped = res.data?.skipped_count || 0;
      addToast(`Готово: добавлено ${added}, обновлено ${updated}, пропущено ${skipped}`, 'success');
      setDiscoveryState(prev => ({ ...prev, results: [] }));
      loadCameras();
    } catch (err) {
      const msg = err.response?.data?.error || 'Не удалось добавить камеры';
      addToast(msg, 'error');
    } finally {
      setAddingAll(false);
    }
  };

  const buildPathWithCredentials = (path, username, password) => {
    if (!path) return '/stream';
    let next = path;
    if (next.includes('{user}') || next.includes('{pass}')) {
      return next
        .replaceAll('{user}', encodeURIComponent(username))
        .replaceAll('{pass}', encodeURIComponent(password));
    }
    if (/user=.*password=/.test(next)) {
      next = next.replace(/user=[^&/]*/g, `user=${encodeURIComponent(username)}`);
      next = next.replace(/password=[^&/]*/g, `password=${encodeURIComponent(password)}`);
      return next;
    }
    return next;
  };

  const handleAddDiscoveredCamera = async (cam) => {
    const key = cam.stream_url || `${cam.ip_address}:${cam.port}`;
    try {
      setAddingOne(prev => ({ ...prev, [key]: true }));

      let username = cam.username || 'admin';
      let password = cam.password || '';
      let path = cam.path || '/stream';

      if (cam.auth_required && !cam.verified) {
        const userInput = window.prompt(`Камера ${cam.ip_address}:${cam.port}\nВведите логин:`, username);
        if (userInput === null) return;
        const passInput = window.prompt(`Камера ${cam.ip_address}:${cam.port}\nВведите пароль:`, '');
        if (passInput === null) return;
        if (!userInput.trim()) {
          addToast('Логин не может быть пустым', 'error');
          return;
        }
        username = userInput.trim();
        password = passInput;
        path = buildPathWithCredentials(path, username, password);
      }

      const payload = {
        name: cam.name || `Камера ${cam.ip_address}`,
        ip_address: cam.ip_address,
        port: cam.port || 554,
        username,
        password,
        protocol: cam.protocol || 'rtsp',
        path,
        location: '',
      };

      try {
        await discoveryAPI.addCamera(payload);
        addToast(`Камера ${cam.ip_address}:${cam.port} добавлена`, 'success');
      } catch (addErr) {
        if (addErr.response?.status === 409 && addErr.response?.data?.id) {
          const existingId = addErr.response.data.id;
          await cameraAPI.update(existingId, payload);
          addToast(`Камера ${cam.ip_address}:${cam.port} обновлена`, 'success');
        } else {
          throw addErr;
        }
      }

      setDiscoveryState(prev => ({
        ...prev,
        results: (prev.results || []).filter(item => (item.stream_url || `${item.ip_address}:${item.port}`) !== key),
      }));
      loadCameras();
    } catch (err) {
      const msg = err.response?.data?.error || 'Не удалось добавить камеру';
      addToast(msg, 'error');
    } finally {
      setAddingOne(prev => ({ ...prev, [key]: false }));
    }
  };

  const openDiscoveryModal = async () => {
    setShowDiscovery(true);
    // Check if there's an ongoing scan
    try {
      const res = await discoveryAPI.getStatus();
      setDiscoveryState(res.data);
      if (res.data.scanning) startPolling();
    } catch {
      // ignore
    }
  };

  // ── Camera CRUD ─────────────────────────────────────────────

  const handleInputChange = (e) => {
    const value = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    setFormData({ ...formData, [e.target.name]: value });
  };

  const parseRtspUrl = (value) => {
    try {
      const raw = value.trim();
      const parsed = new URL(raw);
      const scheme = `${parsed.protocol}//`;
      const hostStart = raw.indexOf(scheme) + scheme.length;
      const pathStart = raw.indexOf('/', hostStart);
      const rawPath = pathStart === -1 ? '' : raw.slice(pathStart);
      return {
        protocol: parsed.protocol.replace(':', ''),
        username: parsed.username || '',
        password: parsed.password || '',
        ip_address: parsed.hostname,
        port: parsed.port ? Number(parsed.port) : 554,
        path: rawPath || parsed.pathname || '/stream',
      };
    } catch {
      return null;
    }
  };

  const buildRtspUrl = (camera) => {
    if (!camera?.ip_address) return '';
    const protocol = camera.protocol || 'rtsp';
    const port = camera.port || 554;
    const path = camera.path || '/stream';
    const creds = camera.username
      ? `${camera.username}${camera.password ? `:${camera.password}` : ''}@`
      : '';
    return `${protocol}://${creds}${camera.ip_address}:${port}${path}`;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setModalError('');
    setSuccess('');

    try {
      let payload = { ...formData };
      if (inputMode === 'link') {
        const parsed = parseRtspUrl(formData.rtsp_url);
        if (!parsed) { setModalError('Некорректный RTSP URL'); return; }
        payload = { ...payload, ...parsed };
      }
      delete payload.rtsp_url;

      if (editingCamera) {
        await cameraAPI.update(editingCamera.id, payload);
        addToast('Камера обновлена', 'success');
      } else {
        await cameraAPI.create(payload);
        addToast('Камера добавлена', 'success');
      }
      setShowModal(false);
      resetForm();
      loadCameras();
    } catch (err) {
      const message = err.response?.data?.error || 'Не удалось сохранить камеру';
      setModalError(message);
      addToast(message, 'error');
    }
  };

  const handleEdit = (camera) => {
    setEditingCamera(camera);
    setFormData({
      name: camera.name,
      ip_address: camera.ip_address,
      port: camera.port,
      username: camera.username || '',
      password: camera.password || '',
      protocol: camera.protocol,
      path: camera.path,
      location: camera.location || '',
      face_recognition_enabled: camera.face_recognition_enabled,
      rtsp_url: buildRtspUrl(camera),
    });
    setInputMode('link');
    setShowModal(true);
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Вы уверены, что хотите удалить эту камеру?')) return;
    try {
      setDeletingId(id);
      await cameraAPI.delete(id);
      addToast('Камера удалена', 'success');
      setCameras(prev => prev.filter(cam => cam.id !== id));
    } catch (err) {
      if (err.response?.status === 404) {
        setCameras(prev => prev.filter(cam => cam.id !== id));
      } else {
        const message = err.response?.data?.error || 'Не удалось удалить камеру';
        addToast(message, 'error');
      }
    } finally {
      setDeletingId(null);
    }
  };

  const resetForm = () => {
    setShowModal(false);
    setEditingCamera(null);
    setModalError('');
    setFormData({
      name: '', ip_address: '', port: 554, username: '', password: '',
      protocol: 'rtsp', path: '/stream', location: '',
      face_recognition_enabled: false, rtsp_url: '',
    });
    setInputMode('link');
  };

  if (loading) {
    return (
      <div className="page-container">
        <div className="loading"><div className="spinner"></div></div>
      </div>
    );
  }

  const verifiedCount = discoveryState.results?.filter(r => r.verified).length || 0;
  const authRequiredCount = discoveryState.results?.filter(r => r.auth_required && !r.verified).length || 0;

  return (
    <div className="page-container">
      <div className="container">
        <div className="page-header flex-between">
          <h1><FiVideo /> Управление камерами</h1>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button onClick={openDiscoveryModal} className="btn btn-primary" style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)' }}>
              <FiSearch /> Автопоиск
            </button>
            <button onClick={() => { resetForm(); setShowModal(true); }} className="btn btn-primary">
              <FiPlus /> Добавить камеру
            </button>
          </div>
        </div>

        {error && (
          <div className="alert alert-error">
            {error}
            <button onClick={() => setError('')} className="alert-close">&times;</button>
          </div>
        )}

        {success && (
          <div className="alert alert-success">
            {success}
            <button onClick={() => setSuccess('')} className="alert-close">&times;</button>
          </div>
        )}

        {cameras.length === 0 ? (
          <div className="empty-state">
            <FiVideo size={64} />
            <h2>Камер нет</h2>
            <p>Добавьте первую камеру или используйте автопоиск в сети</p>
          </div>
        ) : (
          <div className="card">
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Превью</th>
                    <th>Имя</th>
                    <th>IP-адрес</th>
                    <th>Порт</th>
                    <th>Протокол</th>
                    <th>Локация</th>
                    <th>Распознавание лиц</th>
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {cameras.map(camera => (
                    <tr key={camera.id}>
                      <td>
                        {previewUrls[camera.id] ? (
                          <img
                            src={previewUrls[camera.id]}
                            alt={camera.name}
                            style={{
                              width: 120,
                              height: 68,
                              objectFit: 'cover',
                              borderRadius: 8,
                              border: '1px solid var(--border-color)',
                              background: '#000',
                            }}
                          />
                        ) : (
                          <div style={{
                            width: 120,
                            height: 68,
                            borderRadius: 8,
                            border: '1px solid var(--border-color)',
                            background: 'var(--color-bg-tertiary)',
                            color: 'var(--text-muted)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: 12,
                          }}>
                            Нет кадра
                          </div>
                        )}
                      </td>
                      <td><strong>{camera.name}</strong></td>
                      <td><code>{camera.ip_address}</code></td>
                      <td>{camera.port}</td>
                      <td>
                        <span className="badge badge-gray">
                          {camera.protocol ? camera.protocol.toUpperCase() : '-'}
                        </span>
                      </td>
                      <td>{camera.location || '-'}</td>
                      <td>
                        {camera.face_recognition_enabled ? (
                          <span className="badge badge-success">ВКЛ</span>
                        ) : (
                          <span className="badge badge-gray">ВЫКЛ</span>
                        )}
                      </td>
                      <td>
                        <div className="btn-group">
                          <Link to={`/camera/${camera.id}`} className="btn btn-sm btn-icon" title="Открыть">
                            <FiEye />
                          </Link>
                          <button onClick={() => handleEdit(camera)} className="btn btn-sm btn-icon" title="Изменить">
                            <FiEdit2 />
                          </button>
                          <button
                            onClick={() => handleDelete(camera.id)}
                            className="btn btn-sm btn-icon btn-danger"
                            title="Удалить"
                            disabled={deletingId === camera.id}
                          >
                            <FiTrash2 />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ── Add/Edit Camera Modal ──────────────────────────────── */}
        {showModal && (
          <div className="modal-overlay" onClick={resetForm}>
            <div className="modal" onClick={e => e.stopPropagation()}>
              <div className="modal-header">
                <h2 className="modal-title">
                  {editingCamera ? 'Редактировать камеру' : 'Добавить камеру'}
                </h2>
                <button onClick={resetForm} className="btn btn-icon">&times;</button>
              </div>

              <form onSubmit={handleSubmit}>
                <div className="modal-body">
                  {modalError && <div className="alert alert-error">{modalError}</div>}

                  <div className="form-group">
                    <label className="form-label">Способ ввода</label>
                    <div className="form-check">
                      <input type="radio" name="input_mode" id="input_mode_link"
                        checked={inputMode === 'link'} onChange={() => setInputMode('link')} />
                      <label htmlFor="input_mode_link">RTSP URL</label>
                    </div>
                    <div className="form-check">
                      <input type="radio" name="input_mode" id="input_mode_manual"
                        checked={inputMode === 'manual'} onChange={() => setInputMode('manual')} />
                      <label htmlFor="input_mode_manual">Вручную</label>
                    </div>
                  </div>

                  {inputMode === 'link' && (
                    <div className="form-group">
                      <label className="form-label">RTSP URL</label>
                      <input type="text" name="rtsp_url" className="form-control"
                        value={formData.rtsp_url} onChange={handleInputChange}
                        placeholder="rtsp://user:pass@192.168.1.10:554/stream"
                        required={inputMode === 'link'} />
                    </div>
                  )}

                  <div className="grid grid-2">
                    <div className="form-group">
                      <label className="form-label">Имя *</label>
                      <input type="text" name="name" className="form-control"
                        value={formData.name} onChange={handleInputChange} required />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Локация</label>
                      <input type="text" name="location" className="form-control"
                        value={formData.location} onChange={handleInputChange} />
                    </div>
                  </div>

                  {inputMode === 'manual' && (
                    <>
                      <div className="grid grid-3">
                        <div className="form-group">
                          <label className="form-label">IP-адрес *</label>
                          <input type="text" name="ip_address" className="form-control"
                            value={formData.ip_address} onChange={handleInputChange}
                            placeholder="192.168.1.100" required />
                        </div>
                        <div className="form-group">
                          <label className="form-label">Порт *</label>
                          <input type="number" name="port" className="form-control"
                            value={formData.port} onChange={handleInputChange} required />
                        </div>
                        <div className="form-group">
                          <label className="form-label">Протокол *</label>
                          <select name="protocol" className="form-control"
                            value={formData.protocol} onChange={handleInputChange} required>
                            <option value="rtsp">RTSP</option>
                            <option value="http">HTTP</option>
                          </select>
                        </div>
                      </div>
                      <div className="form-group">
                        <label className="form-label">Путь потока</label>
                        <input type="text" name="path" className="form-control"
                          value={formData.path} onChange={handleInputChange} placeholder="/stream" />
                      </div>
                      <div className="grid grid-2">
                        <div className="form-group">
                          <label className="form-label">Логин</label>
                          <input type="text" name="username" className="form-control"
                            value={formData.username} onChange={handleInputChange} />
                        </div>
                        <div className="form-group">
                          <label className="form-label">Пароль</label>
                          <input type="password" name="password" className="form-control"
                            value={formData.password} onChange={handleInputChange} />
                        </div>
                      </div>
                    </>
                  )}

                  <div className="form-group">
                    <div className="form-check">
                      <input type="checkbox" name="face_recognition_enabled" id="face_recognition_enabled"
                        checked={formData.face_recognition_enabled} onChange={handleInputChange} />
                      <label htmlFor="face_recognition_enabled">Включить распознавание лиц</label>
                    </div>
                  </div>
                </div>

                <div className="modal-footer">
                  <button type="button" onClick={resetForm} className="btn btn-secondary">Отмена</button>
                  <button type="submit" className="btn btn-primary">
                    {editingCamera ? 'Сохранить' : 'Добавить'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* ── Auto Discovery Modal ──────────────────────────────── */}
        {showDiscovery && (
          <div className="modal-overlay" onClick={() => !discoveryState.scanning && setShowDiscovery(false)}>
            <div className="modal" style={{ maxWidth: 620 }} onClick={e => e.stopPropagation()}>
              <div className="modal-header">
                <h2 className="modal-title"><FiWifi /> Автопоиск</h2>
                <button onClick={() => !discoveryState.scanning && setShowDiscovery(false)} className="btn btn-icon"
                  disabled={discoveryState.scanning}>&times;</button>
              </div>

              <div className="modal-body">
                {!discoveryState.scanning && (
                  <div className="form-group" style={{ marginBottom: '1rem' }}>
                    <label className="form-label">Сеть для сканирования (CIDR)</label>
                    <input
                      type="text"
                      className="form-control"
                      value={discoveryNetwork}
                      onChange={(e) => setDiscoveryNetwork(e.target.value)}
                      placeholder="192.168.10.0/24,192.168.11.0/24"
                    />
                    <small style={{ color: 'var(--text-tertiary)' }}>
                      Можно указать несколько сетей через запятую
                    </small>
                  </div>
                )}

                {/* Progress section */}
                {discoveryState.scanning && (
                  <div style={{ marginBottom: '1.5rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                      <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                        {STAGE_LABELS[discoveryState.stage] || discoveryState.stage}
                      </span>
                      <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>{discoveryState.progress}%</span>
                    </div>
                    <div style={{
                      height: 8, borderRadius: 4, background: 'var(--bg-tertiary)',
                      overflow: 'hidden',
                    }}>
                      <div style={{
                        height: '100%', borderRadius: 4,
                        background: 'linear-gradient(90deg, #6366f1, #8b5cf6)',
                        width: `${discoveryState.progress}%`,
                        transition: 'width 0.5s ease',
                      }} />
                    </div>
                    <p style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)', marginTop: 6 }}>
                      {discoveryState.message}
                    </p>
                  </div>
                )}

                {/* Error */}
                {discoveryState.error && !discoveryState.scanning && (
                  <div className="alert alert-error" style={{ marginBottom: '1rem' }}>
                    {discoveryState.error}
                  </div>
                )}

                {/* Results */}
                {!discoveryState.scanning && discoveryState.results?.length > 0 && (
                  <div style={{ marginBottom: '1rem' }}>
                    <h3 style={{ fontSize: '1rem', marginBottom: '0.75rem' }}>
                      Найдено проверенных: {verifiedCount}, с авторизацией: {authRequiredCount}
                    </h3>
                    <div style={{ maxHeight: 280, overflowY: 'auto' }}>
                      {discoveryState.results.map((cam, idx) => {
                        const key = cam.stream_url || `${cam.ip_address}:${cam.port}`;
                        const busy = !!addingOne[key];
                        const canConnect = !!cam.verified || !!cam.auth_required;
                        return (
                        <div key={idx} style={{
                          display: 'flex', alignItems: 'center', gap: '0.75rem',
                          padding: '0.6rem 0.75rem', borderRadius: 8,
                          background: 'var(--bg-secondary)', marginBottom: 6,
                        }}>
                          {cam.verified ? <FiCheckCircle color="#22c55e" size={18} /> : <FiLock color="#f59e0b" size={18} />}
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>{cam.name}</div>
                            <div style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {cam.stream_url}
                            </div>
                          </div>
                          {cam.auth_required && !cam.verified ? (
                            <span className="badge badge-warning" style={{ fontSize: '0.7rem' }}>
                              ТРЕБУЕТСЯ АВТОРИЗАЦИЯ
                            </span>
                          ) : (
                            <span className="badge badge-success" style={{ fontSize: '0.7rem' }}>
                              {cam.protocol?.toUpperCase()} :{cam.port}
                            </span>
                          )}
                          <button
                            onClick={() => handleAddDiscoveredCamera(cam)}
                            className="btn btn-sm btn-primary"
                            disabled={!canConnect || busy}
                          >
                            {busy ? 'Добавление...' : (cam.auth_required && !cam.verified ? 'Подключить' : 'Добавить')}
                          </button>
                        </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* No results after scan */}
                {!discoveryState.scanning && discoveryState.progress >= 100 && (discoveryState.results?.length || 0) === 0 && (
                  <div style={{ textAlign: 'center', padding: '2rem 0', color: 'var(--text-tertiary)' }}>
                    <FiXCircle size={48} style={{ marginBottom: '0.75rem', opacity: 0.5 }} />
                    <p>Камеры в сети не найдены</p>
                    <p style={{ fontSize: '0.8rem' }}>Проверьте, что камеры включены и подключены</p>
                  </div>
                )}

                {/* Initial state */}
                {!discoveryState.scanning && discoveryState.progress === 0 && !discoveryState.error && (
                  <div style={{ textAlign: 'center', padding: '2rem 0', color: 'var(--text-secondary)' }}>
                    <FiSearch size={48} style={{ marginBottom: '0.75rem', opacity: 0.5 }} />
                    <p style={{ fontWeight: 500 }}>Автопоиск камер в один клик</p>
                    <p style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)', maxWidth: 400, margin: '0.5rem auto 0' }}>
                      Автоматически сканирует локальные сети через ONVIF, ARP, ping и проверку портов.
                      Проверяет RTSP-потоки с разными комбинациями логина и пароля.
                    </p>
                  </div>
                )}
              </div>

              <div className="modal-footer" style={{ justifyContent: 'space-between' }}>
                {discoveryState.scanning ? (
                  <>
                    <span style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>
                      {verifiedCount > 0 ? `Уже найдено: ${verifiedCount}` : 'Сканирование...'}
                    </span>
                    <button onClick={handleStopDiscovery} className="btn btn-secondary">
                      <FiX /> Остановить
                    </button>
                  </>
                ) : (
                  <>
                    <button onClick={() => setShowDiscovery(false)} className="btn btn-secondary">Закрыть</button>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      {(verifiedCount + authRequiredCount) > 0 && (
                        <button onClick={handleAddAllCameras} className="btn btn-primary"
                          disabled={addingAll}
                          style={{ background: 'linear-gradient(135deg, #22c55e, #16a34a)' }}>
                          {addingAll ? 'Добавляю...' : `Добавить все найденные (${discoveryState.results?.length || 0})`}
                        </button>
                      )}
                      <button onClick={handleStartDiscovery} className="btn btn-primary"
                        style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)' }}>
                        <FiSearch /> {discoveryState.progress > 0 ? 'Сканировать снова' : 'Начать сканирование'}
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default Cameras;
