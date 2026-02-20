import React, { useState, useEffect } from 'react';
import { FiVideo, FiPlus, FiEdit2, FiTrash2, FiEye } from 'react-icons/fi';
import { Link } from 'react-router-dom';
import { cameraAPI } from '../services/api';
import { useToast } from '../components/ToastProvider';

function Cameras() {
  const [cameras, setCameras] = useState([]);
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

  useEffect(() => {
    loadCameras();
  }, []);

  const loadCameras = async () => {
    try {
      const response = await cameraAPI.getAll();
      setCameras(response.data);
    } catch (err) {
      setError('Ошибка загрузки камер');
      addToast('Ошибка загрузки камер', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleInputChange = (e) => {
    const value = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    setFormData({
      ...formData,
      [e.target.name]: value,
    });
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
    if (!camera?.ip_address) {
      return '';
    }
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
        if (!parsed) {
          setModalError('Некорректная RTSP ссылка');
          return;
        }
        payload = { ...payload, ...parsed };
      }
      delete payload.rtsp_url;

      if (editingCamera) {
        await cameraAPI.update(editingCamera.id, payload);
        setSuccess('Камера обновлена!');
      } else {
        await cameraAPI.create(payload);
        setSuccess('Камера добавлена!');
      }
      setShowModal(false);
      resetForm();
      loadCameras();
    } catch (err) {
      const message = err.response?.data?.error || 'Ошибка при сохранении камеры';
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
    if (!window.confirm('Вы уверены, что хотите удалить эту камеру?')) {
      return;
    }

    try {
      setDeletingId(id);
      await cameraAPI.delete(id);
      setSuccess('Камера удалена');
      setCameras((prev) => prev.filter((cam) => cam.id !== id));
    } catch (err) {
      const status = err.response?.status;
      const message = err.response?.data?.error || 'Ошибка при удалении камеры';
      if (status === 404) {
        // Камера уже удалена — убираем из списка на фронте
        setCameras((prev) => prev.filter((cam) => cam.id !== id));
        setSuccess('Камера удалена');
      } else {
        setError(message);
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
    setInputMode('link');
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
        <div className="page-header flex-between">
          <h1><FiVideo /> Управление камерами</h1>
          <button
            onClick={() => {
              resetForm();
              setShowModal(true);
            }}
            className="btn btn-primary"
          >
            <FiPlus /> Добавить камеру
          </button>
        </div>

        {error && (
          <div className="alert alert-error">
            {error}
            <button onClick={() => setError('')} className="alert-close">×</button>
          </div>
        )}

        {success && (
          <div className="alert alert-success">
            {success}
            <button onClick={() => setSuccess('')} className="alert-close">×</button>
          </div>
        )}

        {cameras.length === 0 ? (
          <div className="empty-state">
            <FiVideo size={64} />
            <h2>Нет камер</h2>
            <p>Добавьте первую камеру для начала работы</p>
          </div>
        ) : (
          <div className="card">
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Название</th>
                    <th>IP адрес</th>
                    <th>Порт</th>
                    <th>Протокол</th>
                    <th>Расположение</th>
                    <th>Распознавание</th>
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {cameras.map((camera) => (
                    <tr key={camera.id}>
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
                          <span className="badge badge-success">Включено</span>
                        ) : (
                          <span className="badge badge-gray">Выключено</span>
                        )}
                      </td>
                      <td>
                        <div className="btn-group">
                          <Link to={`/camera/${camera.id}`} className="btn btn-sm btn-icon" title="Просмотр">
                            <FiEye />
                          </Link>
                          <button
                            onClick={() => handleEdit(camera)}
                            className="btn btn-sm btn-icon"
                            title="Редактировать"
                          >
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

        {showModal && (
          <div className="modal-overlay" onClick={resetForm}>
            <div className="modal" onClick={(e) => e.stopPropagation()}>
              <div className="modal-header">
                <h2 className="modal-title">
                  {editingCamera ? 'Редактировать камеру' : 'Добавить камеру'}
                </h2>
                <button onClick={resetForm} className="btn btn-icon">×</button>
              </div>

              <form onSubmit={handleSubmit}>
                <div className="modal-body">
                  {modalError && (
                    <div className="alert alert-error">
                      {modalError}
                    </div>
                  )}

                  <div className="form-group">
                    <label className="form-label">Способ добавления</label>
                    <div className="form-check">
                      <input
                        type="radio"
                        name="input_mode"
                        id="input_mode_link"
                        checked={inputMode === 'link'}
                        onChange={() => setInputMode('link')}
                      />
                      <label htmlFor="input_mode_link">По RTSP ссылке</label>
                    </div>
                    <div className="form-check">
                      <input
                        type="radio"
                        name="input_mode"
                        id="input_mode_manual"
                        checked={inputMode === 'manual'}
                        onChange={() => setInputMode('manual')}
                      />
                      <label htmlFor="input_mode_manual">Вручную</label>
                    </div>
                  </div>

                  {inputMode === 'link' && (
                  <div className="form-group">
                    <label className="form-label">RTSP ссылка (опционально)</label>
                    <input
                      type="text"
                      name="rtsp_url"
                      className="form-control"
                      value={formData.rtsp_url}
                      onChange={handleInputChange}
                      placeholder="rtsp://user:pass@192.168.1.10:554/stream"
                      required={inputMode === 'link'}
                    />
                  </div>
                  )}

                  <div className="grid grid-2">
                    <div className="form-group">
                      <label className="form-label">Название *</label>
                      <input
                        type="text"
                        name="name"
                        className="form-control"
                        value={formData.name}
                        onChange={handleInputChange}
                        required
                      />
                    </div>

                    <div className="form-group">
                      <label className="form-label">Расположение</label>
                      <input
                        type="text"
                        name="location"
                        className="form-control"
                        value={formData.location}
                        onChange={handleInputChange}
                      />
                    </div>
                  </div>

                  {inputMode === 'manual' && (
                    <>
                      <div className="grid grid-3">
                        <div className="form-group">
                          <label className="form-label">IP адрес *</label>
                          <input
                            type="text"
                            name="ip_address"
                            className="form-control"
                            value={formData.ip_address}
                            onChange={handleInputChange}
                            placeholder="192.168.1.100"
                            required
                          />
                        </div>

                        <div className="form-group">
                          <label className="form-label">Порт *</label>
                          <input
                            type="number"
                            name="port"
                            className="form-control"
                            value={formData.port}
                            onChange={handleInputChange}
                            required
                          />
                        </div>

                        <div className="form-group">
                          <label className="form-label">Протокол *</label>
                          <select
                            name="protocol"
                            className="form-control"
                            value={formData.protocol}
                            onChange={handleInputChange}
                            required
                          >
                            <option value="rtsp">RTSP</option>
                            <option value="http">HTTP</option>
                          </select>
                        </div>
                      </div>

                      <div className="form-group">
                        <label className="form-label">Путь к потоку</label>
                        <input
                          type="text"
                          name="path"
                          className="form-control"
                          value={formData.path}
                          onChange={handleInputChange}
                          placeholder="/stream"
                        />
                      </div>

                      <div className="grid grid-2">
                        <div className="form-group">
                          <label className="form-label">Логин камеры</label>
                          <input
                            type="text"
                            name="username"
                            className="form-control"
                            value={formData.username}
                            onChange={handleInputChange}
                          />
                        </div>

                        <div className="form-group">
                          <label className="form-label">Пароль камеры</label>
                          <input
                            type="password"
                            name="password"
                            className="form-control"
                            value={formData.password}
                            onChange={handleInputChange}
                          />
                        </div>
                      </div>
                    </>
                  )}

                  <div className="form-group">
                    <div className="form-check">
                      <input
                        type="checkbox"
                        name="face_recognition_enabled"
                        id="face_recognition_enabled"
                        checked={formData.face_recognition_enabled}
                        onChange={handleInputChange}
                      />
                      <label htmlFor="face_recognition_enabled">
                        Включить распознавание лиц на этой камере
                      </label>
                    </div>
                  </div>
                </div>

                <div className="modal-footer">
                  <button type="button" onClick={resetForm} className="btn btn-secondary">
                    Отмена
                  </button>
                  <button type="submit" className="btn btn-primary">
                    {editingCamera ? 'Сохранить' : 'Добавить'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default Cameras;
