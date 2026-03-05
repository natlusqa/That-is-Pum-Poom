import { useState, useEffect, useMemo } from 'react';
import { FiFilm, FiCalendar, FiVideo, FiPlay, FiTrash2, FiDownload } from 'react-icons/fi';
import { cameraAPI } from '../services/api';
import { useToast } from '../components/ToastProvider';
import { format } from 'date-fns';
import api from '../services/api';
import './Playback.css';

function Playback() {
  const [cameras, setCameras] = useState([]);
  const [recordings, setRecordings] = useState([]);
  const [timeline, setTimeline] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedCamera, setSelectedCamera] = useState('');
  const [selectedDate, setSelectedDate] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [activeRecording, setActiveRecording] = useState(null);
  const { addToast } = useToast();

  const eventTypeLabel = (type) => {
    if (type === 'face') return 'Распознавание лица';
    if (type === 'motion') return 'Движение';
    if (type === 'manual') return 'Вручную';
    if (type === 'continuous') return 'Непрерывная запись';
    return type;
  };

  useEffect(() => {
    loadCameras();
  }, []);

  useEffect(() => {
    if (selectedCamera) {
      loadRecordings();
      loadTimeline();
    }
  }, [selectedCamera, selectedDate]);

  const loadCameras = async () => {
    try {
      const res = await cameraAPI.getAll();
      setCameras(res.data);
      if (res.data.length > 0) {
        setSelectedCamera(String(res.data[0].id));
      }
    } catch {
      addToast('Не удалось загрузить камеры', 'error');
    } finally {
      setLoading(false);
    }
  };

  const loadRecordings = async () => {
    try {
      const res = await api.get('/recordings', {
        params: {
          camera_id: selectedCamera,
          date_from: selectedDate,
          date_to: selectedDate,
        }
      });
      setRecordings(res.data.items || res.data || []);
    } catch {
      setRecordings([]);
    }
  };

  const loadTimeline = async () => {
    try {
      const res = await api.get('/recordings/timeline', {
        params: {
          camera_id: selectedCamera,
          date: selectedDate,
        }
      });
      setTimeline(res.data || []);
    } catch {
      setTimeline([]);
    }
  };

  const playRecording = (rec) => {
    setActiveRecording(rec);
  };

  const deleteRecording = async (id) => {
    if (!window.confirm('Удалить эту запись?')) return;
    try {
      await api.delete(`/recordings/${id}`);
      addToast('Запись удалена', 'success');
      setRecordings(prev => prev.filter(r => r.id !== id));
      if (activeRecording?.id === id) setActiveRecording(null);
    } catch {
      addToast('Не удалось удалить запись', 'error');
    }
  };

  // Timeline computation
  const timelineSegments = useMemo(() => {
    if (!timeline.length) return [];
    const dayStart = new Date(`${selectedDate}T00:00:00`);
    const dayMs = 24 * 60 * 60 * 1000;

    return timeline.map(seg => {
      const start = new Date(seg.start_time);
      const end = seg.end_time ? new Date(seg.end_time) : new Date(start.getTime() + 30000);
      const leftPct = ((start - dayStart) / dayMs) * 100;
      const widthPct = Math.max(((end - start) / dayMs) * 100, 0.3);
      return { ...seg, leftPct, widthPct };
    });
  }, [timeline, selectedDate]);

  const timeLabels = ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00', '24:00'];

  const formatTime = (ts) => {
    try {
      return format(new Date(ts), 'HH:mm:ss');
    } catch {
      return ts;
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
        <div className="page-header">
          <h1><FiFilm /> Записи</h1>
        </div>

        {/* Filters */}
        <div className="playback-controls">
          <div className="filter-group">
            <label><FiVideo size={12} /> Камера</label>
            <select
              className="form-control"
              value={selectedCamera}
              onChange={e => setSelectedCamera(e.target.value)}
            >
              {cameras.map(cam => (
                <option key={cam.id} value={cam.id}>{cam.name}</option>
              ))}
            </select>
          </div>
          <div className="filter-group">
            <label><FiCalendar size={12} /> Дата</label>
            <input
              type="date"
              className="form-control"
              value={selectedDate}
              onChange={e => setSelectedDate(e.target.value)}
            />
          </div>
        </div>

        {/* Main layout */}
        <div className="playback-layout">
          <div>
            {/* Video Player */}
            {activeRecording ? (
              <div className="playback-video">
                <video
                  key={activeRecording.id}
                  src={`/api/recordings/${activeRecording.id}/stream`}
                  controls
                  autoPlay
                />
              </div>
            ) : (
              <div className="playback-video-empty">
                <FiPlay size={48} />
                <p>Выберите запись для воспроизведения</p>
              </div>
            )}

            {/* Timeline Scrubber */}
            <div className="timeline-container">
              <div className="timeline-header">
                <h3>Таймлайн - {selectedDate}</h3>
              </div>

              <div className="timeline-bar">
                {timelineSegments.map((seg, i) => (
                  <div
                    key={i}
                    className={`timeline-segment timeline-segment-${seg.event_type || 'face'}`}
                    style={{ left: `${seg.leftPct}%`, width: `${seg.widthPct}%` }}
                    title={`${eventTypeLabel(seg.event_type)} - ${formatTime(seg.start_time)}`}
                    onClick={() => {
                      const rec = recordings.find(r => r.id === seg.id);
                      if (rec) playRecording(rec);
                    }}
                  />
                ))}
              </div>

              <div className="timeline-labels">
                {timeLabels.map(label => <span key={label}>{label}</span>)}
              </div>

              <div className="timeline-legend">
                <div className="timeline-legend-item">
                  <div className="timeline-legend-dot" style={{ background: 'var(--danger)' }}></div>
                  Распознавание лица
                </div>
                <div className="timeline-legend-item">
                  <div className="timeline-legend-dot" style={{ background: 'var(--info)' }}></div>
                  Движение
                </div>
                <div className="timeline-legend-item">
                  <div className="timeline-legend-dot" style={{ background: 'var(--success)' }}></div>
                  Вручную
                </div>
              </div>
            </div>
          </div>

          {/* Events panel */}
          <div className="events-panel">
            <div className="events-panel-header">
              Записи ({recordings.length})
            </div>

            {recordings.length === 0 ? (
              <div className="events-empty">
                Нет записей за эту дату
              </div>
            ) : (
              recordings.map(rec => (
                <div
                  key={rec.id}
                  className={`event-item ${activeRecording?.id === rec.id ? 'active' : ''}`}
                  onClick={() => playRecording(rec)}
                >
                  <div
                    className="event-type-dot"
                    style={{
                      background: rec.event_type === 'face' ? 'var(--danger)'
                        : rec.event_type === 'motion' ? 'var(--info)'
                        : rec.event_type === 'continuous' ? 'var(--primary)'
                        : 'var(--success)'
                    }}
                  />
                  <div className="event-details">
                    <strong>{rec.employee_name || eventTypeLabel(rec.event_type)}</strong>
                    <small>{rec.camera_name}</small>
                  </div>
                  <div className="event-time">
                    {formatTime(rec.start_time)}
                  </div>
                  <button
                    className="btn-icon"
                    onClick={(e) => { e.stopPropagation(); deleteRecording(rec.id); }}
                    title="Удалить"
                  >
                    <FiTrash2 size={14} />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default Playback;
