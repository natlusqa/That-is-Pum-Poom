import React, { useState, useEffect, useRef, useCallback } from 'react';
import { FiVideo, FiPlus, FiEdit2, FiTrash2, FiEye, FiSearch, FiCheckCircle, FiXCircle, FiX, FiWifi } from 'react-icons/fi';
import { Link } from 'react-router-dom';
import { cameraAPI, discoveryAPI } from '../services/api';
import { useToast } from '../components/ToastProvider';

const STAGE_LABELS = {
  starting: 'Initialization',
  network: 'Detecting networks',
  onvif: 'ONVIF Discovery',
  arp: 'ARP table scan',
  ping: 'Ping sweep',
  scan: 'Host analysis',
  ports: 'Port scanning',
  verify: 'Verifying streams',
  done: 'Complete',
};

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
  const pollRef = useRef(null);

  useEffect(() => {
    loadCameras();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const loadCameras = async () => {
    try {
      const response = await cameraAPI.getAll();
      setCameras(response.data);
    } catch (err) {
      setError('Failed to load cameras');
      addToast('Failed to load cameras', 'error');
    } finally {
      setLoading(false);
    }
  };

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
      setDiscoveryState(prev => ({ ...prev, scanning: true, progress: 0, results: [], error: null, stage: 'starting', message: 'Initializing...' }));
      await discoveryAPI.startScan();
      startPolling();
    } catch (err) {
      const msg = err.response?.data?.error || 'Failed to start discovery';
      addToast(msg, 'error');
      setDiscoveryState(prev => ({ ...prev, scanning: false, error: msg }));
    }
  };

  const handleStopDiscovery = async () => {
    try {
      await discoveryAPI.stopScan();
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
      setDiscoveryState(prev => ({ ...prev, scanning: false }));
      addToast('Discovery stopped', 'info');
    } catch {
      // ignore
    }
  };

  const handleAddAllCameras = async () => {
    try {
      setAddingAll(true);
      const res = await discoveryAPI.addAll();
      const { added_count, skipped_count } = res.data;
      addToast(`Added ${added_count} cameras${skipped_count ? `, ${skipped_count} duplicates skipped` : ''}`, 'success');
      setShowDiscovery(false);
      loadCameras();
    } catch (err) {
      const msg = err.response?.data?.error || 'Failed to add cameras';
      addToast(msg, 'error');
    } finally {
      setAddingAll(false);
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
        if (!parsed) { setModalError('Invalid RTSP URL'); return; }
        payload = { ...payload, ...parsed };
      }
      delete payload.rtsp_url;

      if (editingCamera) {
        await cameraAPI.update(editingCamera.id, payload);
        addToast('Camera updated', 'success');
      } else {
        await cameraAPI.create(payload);
        addToast('Camera added', 'success');
      }
      setShowModal(false);
      resetForm();
      loadCameras();
    } catch (err) {
      const message = err.response?.data?.error || 'Failed to save camera';
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
    if (!window.confirm('Are you sure you want to delete this camera?')) return;
    try {
      setDeletingId(id);
      await cameraAPI.delete(id);
      addToast('Camera deleted', 'success');
      setCameras(prev => prev.filter(cam => cam.id !== id));
    } catch (err) {
      if (err.response?.status === 404) {
        setCameras(prev => prev.filter(cam => cam.id !== id));
      } else {
        const message = err.response?.data?.error || 'Failed to delete camera';
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

  return (
    <div className="page-container">
      <div className="container">
        <div className="page-header flex-between">
          <h1><FiVideo /> Camera Management</h1>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button onClick={openDiscoveryModal} className="btn btn-primary" style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)' }}>
              <FiSearch /> Auto Discover
            </button>
            <button onClick={() => { resetForm(); setShowModal(true); }} className="btn btn-primary">
              <FiPlus /> Add Camera
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
            <h2>No cameras</h2>
            <p>Add your first camera or use Auto Discover to find cameras on the network</p>
          </div>
        ) : (
          <div className="card">
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>IP Address</th>
                    <th>Port</th>
                    <th>Protocol</th>
                    <th>Location</th>
                    <th>Face Recognition</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {cameras.map(camera => (
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
                          <span className="badge badge-success">ON</span>
                        ) : (
                          <span className="badge badge-gray">OFF</span>
                        )}
                      </td>
                      <td>
                        <div className="btn-group">
                          <Link to={`/camera/${camera.id}`} className="btn btn-sm btn-icon" title="View">
                            <FiEye />
                          </Link>
                          <button onClick={() => handleEdit(camera)} className="btn btn-sm btn-icon" title="Edit">
                            <FiEdit2 />
                          </button>
                          <button
                            onClick={() => handleDelete(camera.id)}
                            className="btn btn-sm btn-icon btn-danger"
                            title="Delete"
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
                  {editingCamera ? 'Edit Camera' : 'Add Camera'}
                </h2>
                <button onClick={resetForm} className="btn btn-icon">&times;</button>
              </div>

              <form onSubmit={handleSubmit}>
                <div className="modal-body">
                  {modalError && <div className="alert alert-error">{modalError}</div>}

                  <div className="form-group">
                    <label className="form-label">Input method</label>
                    <div className="form-check">
                      <input type="radio" name="input_mode" id="input_mode_link"
                        checked={inputMode === 'link'} onChange={() => setInputMode('link')} />
                      <label htmlFor="input_mode_link">RTSP URL</label>
                    </div>
                    <div className="form-check">
                      <input type="radio" name="input_mode" id="input_mode_manual"
                        checked={inputMode === 'manual'} onChange={() => setInputMode('manual')} />
                      <label htmlFor="input_mode_manual">Manual</label>
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
                      <label className="form-label">Name *</label>
                      <input type="text" name="name" className="form-control"
                        value={formData.name} onChange={handleInputChange} required />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Location</label>
                      <input type="text" name="location" className="form-control"
                        value={formData.location} onChange={handleInputChange} />
                    </div>
                  </div>

                  {inputMode === 'manual' && (
                    <>
                      <div className="grid grid-3">
                        <div className="form-group">
                          <label className="form-label">IP Address *</label>
                          <input type="text" name="ip_address" className="form-control"
                            value={formData.ip_address} onChange={handleInputChange}
                            placeholder="192.168.1.100" required />
                        </div>
                        <div className="form-group">
                          <label className="form-label">Port *</label>
                          <input type="number" name="port" className="form-control"
                            value={formData.port} onChange={handleInputChange} required />
                        </div>
                        <div className="form-group">
                          <label className="form-label">Protocol *</label>
                          <select name="protocol" className="form-control"
                            value={formData.protocol} onChange={handleInputChange} required>
                            <option value="rtsp">RTSP</option>
                            <option value="http">HTTP</option>
                          </select>
                        </div>
                      </div>
                      <div className="form-group">
                        <label className="form-label">Stream Path</label>
                        <input type="text" name="path" className="form-control"
                          value={formData.path} onChange={handleInputChange} placeholder="/stream" />
                      </div>
                      <div className="grid grid-2">
                        <div className="form-group">
                          <label className="form-label">Username</label>
                          <input type="text" name="username" className="form-control"
                            value={formData.username} onChange={handleInputChange} />
                        </div>
                        <div className="form-group">
                          <label className="form-label">Password</label>
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
                      <label htmlFor="face_recognition_enabled">Enable face recognition</label>
                    </div>
                  </div>
                </div>

                <div className="modal-footer">
                  <button type="button" onClick={resetForm} className="btn btn-secondary">Cancel</button>
                  <button type="submit" className="btn btn-primary">
                    {editingCamera ? 'Save' : 'Add'}
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
                <h2 className="modal-title"><FiWifi /> Auto Discovery</h2>
                <button onClick={() => !discoveryState.scanning && setShowDiscovery(false)} className="btn btn-icon"
                  disabled={discoveryState.scanning}>&times;</button>
              </div>

              <div className="modal-body">
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
                      Found {verifiedCount} verified camera{verifiedCount !== 1 ? 's' : ''}
                    </h3>
                    <div style={{ maxHeight: 280, overflowY: 'auto' }}>
                      {discoveryState.results.filter(r => r.verified).map((cam, idx) => (
                        <div key={idx} style={{
                          display: 'flex', alignItems: 'center', gap: '0.75rem',
                          padding: '0.6rem 0.75rem', borderRadius: 8,
                          background: 'var(--bg-secondary)', marginBottom: 6,
                        }}>
                          <FiCheckCircle color="#22c55e" size={18} />
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>{cam.name}</div>
                            <div style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {cam.stream_url}
                            </div>
                          </div>
                          <span className="badge badge-success" style={{ fontSize: '0.7rem' }}>
                            {cam.protocol?.toUpperCase()} :{cam.port}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* No results after scan */}
                {!discoveryState.scanning && discoveryState.progress >= 100 && verifiedCount === 0 && (
                  <div style={{ textAlign: 'center', padding: '2rem 0', color: 'var(--text-tertiary)' }}>
                    <FiXCircle size={48} style={{ marginBottom: '0.75rem', opacity: 0.5 }} />
                    <p>No cameras found on the network</p>
                    <p style={{ fontSize: '0.8rem' }}>Make sure cameras are powered on and connected</p>
                  </div>
                )}

                {/* Initial state */}
                {!discoveryState.scanning && discoveryState.progress === 0 && !discoveryState.error && (
                  <div style={{ textAlign: 'center', padding: '2rem 0', color: 'var(--text-secondary)' }}>
                    <FiSearch size={48} style={{ marginBottom: '0.75rem', opacity: 0.5 }} />
                    <p style={{ fontWeight: 500 }}>One-click camera auto-discovery</p>
                    <p style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)', maxWidth: 400, margin: '0.5rem auto 0' }}>
                      Automatically scans all local networks using ONVIF, ARP, ping sweep, and port scanning.
                      Verifies each RTSP stream with multiple credential combinations.
                    </p>
                  </div>
                )}
              </div>

              <div className="modal-footer" style={{ justifyContent: 'space-between' }}>
                {discoveryState.scanning ? (
                  <>
                    <span style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>
                      {verifiedCount > 0 ? `${verifiedCount} found so far...` : 'Scanning...'}
                    </span>
                    <button onClick={handleStopDiscovery} className="btn btn-secondary">
                      <FiX /> Stop
                    </button>
                  </>
                ) : (
                  <>
                    <button onClick={() => setShowDiscovery(false)} className="btn btn-secondary">Close</button>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      {verifiedCount > 0 && (
                        <button onClick={handleAddAllCameras} className="btn btn-primary"
                          disabled={addingAll}
                          style={{ background: 'linear-gradient(135deg, #22c55e, #16a34a)' }}>
                          {addingAll ? 'Adding...' : `Add All ${verifiedCount} Cameras`}
                        </button>
                      )}
                      <button onClick={handleStartDiscovery} className="btn btn-primary"
                        style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)' }}>
                        <FiSearch /> {discoveryState.progress > 0 ? 'Scan Again' : 'Start Scan'}
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
