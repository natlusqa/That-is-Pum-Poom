import React, { useState, useEffect, useMemo } from 'react';
import { FiClock, FiChevronLeft, FiChevronRight, FiDownload, FiImage, FiChevronUp, FiChevronDown, FiEdit2 } from 'react-icons/fi';
import { attendanceAPI, employeeAPI } from '../services/api';
import { format } from 'date-fns';
import { ru } from 'date-fns/locale';
import { useToast } from '../components/ToastProvider';
import './Attendance.css';

function Attendance({ user }) {
  const [logs, setLogs] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [exportFormat, setExportFormat] = useState('csv');

  // Pagination
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalLogs, setTotalLogs] = useState(0);
  const perPage = 50;

  // Filters
  const [dateFrom, setDateFrom] = useState(
    format(new Date(new Date().setDate(new Date().getDate() - 7)), 'yyyy-MM-dd')
  );
  const [dateTo, setDateTo] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [selectedEmployee, setSelectedEmployee] = useState('');
  const [selectedDepartment, setSelectedDepartment] = useState('');

  // UI
  const [selectedLog, setSelectedLog] = useState(null);
  const [sortBy, setSortBy] = useState('timestamp');
  const [sortOrder, setSortOrder] = useState('desc');
  const [stats, setStats] = useState({});
  const [editMode, setEditMode] = useState(false);
  const [savingEdit, setSavingEdit] = useState(false);
  const [editForm, setEditForm] = useState({
    event_type: 'check-in',
    timestamp: '',
    confidence: '',
  });

  const { addToast } = useToast();

  useEffect(() => {
    loadEmployees();
  }, []);

  useEffect(() => {
    setPage(1);
  }, [dateFrom, dateTo, selectedEmployee, selectedDepartment]);

  useEffect(() => {
    loadAttendanceLogs();
  }, [dateFrom, dateTo, selectedEmployee, selectedDepartment, page]);

  const loadEmployees = async () => {
    try {
      const response = await employeeAPI.getAll();
      setEmployees(response.data);
    } catch {
      addToast('Ошибка загрузки сотрудников', 'error');
    }
  };

  const loadAttendanceLogs = async () => {
    setLoading(true);
    try {
      const params = {
        date_from: dateFrom,
        date_to: dateTo,
        page,
        per_page: perPage,
      };

      if (selectedEmployee) params.employee_id = selectedEmployee;
      if (selectedDepartment) params.department = selectedDepartment;

      const response = await attendanceAPI.getAll(params);
      const data = response.data;

      // Support both paginated and legacy response format
      if (data.items) {
        setLogs(data.items);
        setTotalPages(data.pages || 1);
        setTotalLogs(data.total || 0);
      } else if (Array.isArray(data)) {
        setLogs(data);
        setTotalPages(1);
        setTotalLogs(data.length);
      }

      loadStats();
    } catch (err) {
      console.error('Load error:', err);
      addToast('Ошибка загрузки логов посещаемости', 'error');
      setLogs([]);
    } finally {
      setLoading(false);
    }
  };

  const loadStats = async () => {
    try {
      const params = {
        date_from: dateFrom,
        date_to: dateTo,
      };
      if (selectedDepartment) params.department = selectedDepartment;
      const response = await attendanceAPI.getStats(params);
      setStats(response.data || {});
    } catch {
      // Silent fail for stats
    }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const params = {
        date_from: dateFrom,
        date_to: dateTo,
      };
      if (selectedEmployee) params.employee_id = selectedEmployee;
      if (selectedDepartment) params.department = selectedDepartment;
      params.format = exportFormat;

      const queryString = new URLSearchParams(params).toString();
      const token = localStorage.getItem('token');

      const response = await fetch(`/api/attendance/export?${queryString}`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!response.ok) throw new Error('Export failed');

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const ext = exportFormat === 'xlsx' ? 'xlsx' : exportFormat === 'pdf' ? 'pdf' : 'csv';
      a.download = `attendance_${dateFrom}_${dateTo}.${ext}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      addToast('Отчет скачан', 'success');
    } catch {
      addToast('Ошибка экспорта отчета', 'error');
    } finally {
      setExporting(false);
    }
  };

  const formatDateTime = (timestamp) => {
    try {
      const date = new Date(timestamp);
      return format(date, 'dd MMM yyyy HH:mm:ss', { locale: ru });
    } catch {
      return timestamp;
    }
  };

  const toDateTimeLocal = (value) => {
    if (!value) return '';
    try {
      const d = new Date(value);
      const y = d.getFullYear();
      const m = String(d.getMonth() + 1).padStart(2, '0');
      const day = String(d.getDate()).padStart(2, '0');
      const hh = String(d.getHours()).padStart(2, '0');
      const mm = String(d.getMinutes()).padStart(2, '0');
      return `${y}-${m}-${day}T${hh}:${mm}`;
    } catch {
      return '';
    }
  };

  const getEventBadge = (eventType) => {
    const badges = {
      'check-in': { color: '#27ae60', text: 'Вход' },
      'check-out': { color: '#e74c3c', text: 'Выход' },
      default: { color: '#95a5a6', text: 'Событие' },
    };
    return badges[eventType] || badges['default'];
  };

  const getStatusLabel = (status) => {
    if (status === 'on_time') return 'Вовремя';
    if (status === 'late') return 'Опоздание';
    if (status === 'left_early') return 'Ранний уход';
    return 'Нет данных';
  };

  const getDepartments = () => {
    const depts = new Set();
    employees.forEach((emp) => {
      if (emp.department) depts.add(emp.department);
    });
    return Array.from(depts).sort();
  };

  const canEditAttendance = ['hr', 'admin', 'super_admin'].includes(user?.role);

  const openEditForLog = (log) => {
    setEditForm({
      event_type: log.event_type || 'check-in',
      timestamp: toDateTimeLocal(log.timestamp),
      confidence: log.confidence ?? '',
    });
    setEditMode(true);
  };

  const handleSaveEdit = async () => {
    if (!selectedLog) return;
    if (!editForm.timestamp) {
      addToast('Укажите дату и время', 'error');
      return;
    }
    try {
      setSavingEdit(true);
      await attendanceAPI.update(selectedLog.id, {
        event_type: editForm.event_type,
        timestamp: new Date(editForm.timestamp).toISOString(),
        confidence: editForm.confidence === '' ? null : Number(editForm.confidence),
      });
      addToast('Запись посещаемости обновлена', 'success');
      setEditMode(false);
      setSelectedLog(null);
      await loadAttendanceLogs();
    } catch (err) {
      addToast(err.response?.data?.error || 'Не удалось обновить запись', 'error');
    } finally {
      setSavingEdit(false);
    }
  };

  const parseDay = (value) => {
    if (!value) return '';
    try {
      return format(new Date(value), 'yyyy-MM-dd');
    } catch {
      return '';
    }
  };

  const buildPlannedDate = (day, hhmm, fallback) => {
    const baseTime = (hhmm || fallback || '').trim();
    if (!day || !/^\d{2}:\d{2}$/.test(baseTime)) return null;
    const dt = new Date(`${day}T${baseTime}:00`);
    return Number.isNaN(dt.getTime()) ? null : dt;
  };

  const formatTimeOnly = (value) => {
    if (!value) return '—';
    try {
      return format(new Date(value), 'HH:mm');
    } catch {
      return '—';
    }
  };

  const scheduleRows = useMemo(() => {
    const byKey = new Map();

    logs.forEach((log) => {
      const day = parseDay(log.timestamp || log.first_seen_today || log.last_seen_today);
      if (!day) return;
      const key = `${log.employee_id || log.employee_name || 'unknown'}|${day}`;

      if (!byKey.has(key)) {
        byKey.set(key, {
          key,
          day,
          employee_name: log.employee_name || '—',
          employee_id: log.employee_id || '—',
          department: log.department || '—',
          schedule_check_in: log.schedule_check_in || '09:00',
          schedule_check_out: log.schedule_check_out || '18:00',
          first_seen_today: log.first_seen_today || null,
          last_seen_today: log.last_seen_today || null,
          arrival_status: log.arrival_status || null,
          departure_status: log.departure_status || null,
        });
        return;
      }

      const row = byKey.get(key);
      if (log.first_seen_today) {
        if (!row.first_seen_today || new Date(log.first_seen_today) < new Date(row.first_seen_today)) {
          row.first_seen_today = log.first_seen_today;
        }
      }
      if (log.last_seen_today) {
        if (!row.last_seen_today || new Date(log.last_seen_today) > new Date(row.last_seen_today)) {
          row.last_seen_today = log.last_seen_today;
        }
      }
      row.arrival_status = row.arrival_status || log.arrival_status || null;
      row.departure_status = row.departure_status || log.departure_status || null;
    });

    return Array.from(byKey.values())
      .map((row) => {
        const plannedIn = buildPlannedDate(row.day, row.schedule_check_in, '09:00');
        const plannedOut = buildPlannedDate(row.day, row.schedule_check_out, '18:00');
        const actualIn = row.first_seen_today ? new Date(row.first_seen_today) : null;
        const actualOut = row.last_seen_today ? new Date(row.last_seen_today) : null;

        const lateMinutes = (plannedIn && actualIn)
          ? Math.max(0, Math.round((actualIn.getTime() - plannedIn.getTime()) / 60000))
          : null;
        const earlyLeaveMinutes = (plannedOut && actualOut)
          ? Math.max(0, Math.round((plannedOut.getTime() - actualOut.getTime()) / 60000))
          : null;

        return {
          ...row,
          lateMinutes,
          earlyLeaveMinutes,
        };
      })
      .sort((a, b) => {
        const dateDiff = new Date(b.day).getTime() - new Date(a.day).getTime();
        if (dateDiff !== 0) return dateDiff;
        return (a.employee_name || '').localeCompare(b.employee_name || '', 'ru');
      });
  }, [logs]);

  const sortedLogs = [...logs].sort((a, b) => {
    let aVal, bVal;
    switch (sortBy) {
      case 'timestamp':
        aVal = new Date(a.timestamp).getTime();
        bVal = new Date(b.timestamp).getTime();
        break;
      case 'employee':
        aVal = a.employee_name || '';
        bVal = b.employee_name || '';
        break;
      case 'confidence':
        aVal = a.confidence || 0;
        bVal = b.confidence || 0;
        break;
      default:
        return 0;
    }
    return sortOrder === 'asc'
      ? aVal > bVal ? 1 : aVal < bVal ? -1 : 0
      : aVal < bVal ? 1 : aVal > bVal ? -1 : 0;
  });

  const handleSort = (column) => {
    if (sortBy === column) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(column);
      setSortOrder('desc');
    }
  };

  const SortIcon = ({ column }) => {
    if (sortBy !== column) return null;
    return sortOrder === 'asc'
      ? <FiChevronUp size={16} style={{ marginLeft: '4px' }} />
      : <FiChevronDown size={16} style={{ marginLeft: '4px' }} />;
  };

  // Compute average confidence from stats
  const getAvgConfidence = () => {
    if (!stats.by_employee) return null;
    const employees = Object.values(stats.by_employee);
    if (employees.length === 0) return null;
    const sum = employees.reduce((acc, e) => acc + (e.avg_confidence || 0), 0);
    return ((sum / employees.length) * 100).toFixed(0);
  };

  return (
    <div className="page-container attendance-page">
      <div className="container">
        <div className="page-header">
          <h1><FiClock /> Журнал посещений</h1>
        </div>

        {/* Filters */}
        <div className="filters-section">
          <div className="filter-row">
            <div className="filter-group">
              <label>С даты</label>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="form-control"
              />
            </div>

            <div className="filter-group">
              <label>По дату</label>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="form-control"
              />
            </div>

            <div className="filter-group">
              <label>Сотрудник</label>
              <select
                value={selectedEmployee}
                onChange={(e) => setSelectedEmployee(e.target.value)}
                className="form-control"
              >
                <option value="">Все</option>
                {employees.map((emp) => (
                  <option key={emp.id} value={emp.id}>{emp.name}</option>
                ))}
              </select>
            </div>

            <div className="filter-group">
              <label>Отдел</label>
              <select
                value={selectedDepartment}
                onChange={(e) => setSelectedDepartment(e.target.value)}
                className="form-control"
              >
                <option value="">Все</option>
                {getDepartments().map((dept) => (
                  <option key={dept} value={dept}>{dept}</option>
                ))}
              </select>
            </div>

            <div className="filter-group export-group">
              <label>Экспорт</label>
              <div className="export-actions">
                <select
                  value={exportFormat}
                  onChange={(e) => setExportFormat(e.target.value)}
                  className="form-control"
                >
                  <option value="csv">CSV</option>
                  <option value="xlsx">Excel</option>
                  <option value="pdf">PDF</option>
                </select>
                <button
                  className="btn btn-primary"
                  onClick={handleExport}
                  disabled={exporting || logs.length === 0}
                >
                  <FiDownload /> {exporting ? 'Экспорт...' : 'Скачать'}
                </button>
              </div>
            </div>

            <div className="filter-actions">
              <button
                onClick={() => {
                  setDateFrom(format(new Date(new Date().setDate(new Date().getDate() - 7)), 'yyyy-MM-dd'));
                  setDateTo(format(new Date(), 'yyyy-MM-dd'));
                  setSelectedEmployee('');
                  setSelectedDepartment('');
                }}
                className="btn btn-secondary"
              >
                Сброс
              </button>
            </div>
          </div>
        </div>

        {/* Stats */}
        {stats.by_employee && Object.keys(stats.by_employee).length > 0 && (
          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-value">{stats.total_logs || 0}</div>
              <div className="stat-label">Всего записей</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{Object.keys(stats.by_employee).length}</div>
              <div className="stat-label">Уникальных сотрудников</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{getAvgConfidence() || '—'}%</div>
              <div className="stat-label">Средняя уверенность</div>
            </div>
          </div>
        )}

        {/* Table */}
        {loading ? (
          <div className="loading-state">
            <div className="spinner"></div>
            <p>Загрузка логов...</p>
          </div>
        ) : sortedLogs.length === 0 ? (
          <div className="empty-state">
            <FiClock size={48} />
            <h3>Нет записей</h3>
            <p>По вашим фильтрам нет данных</p>
          </div>
        ) : (
          <div className="card">
            <div className="table-responsive">
              <table className="attendance-table">
                <thead>
                  <tr>
                    <th onClick={() => handleSort('timestamp')} className="sortable">
                      Дата и время <SortIcon column="timestamp" />
                    </th>
                    <th onClick={() => handleSort('employee')} className="sortable">
                      Сотрудник <SortIcon column="employee" />
                    </th>
                    <th>Отдел</th>
                    <th>Приход (план/факт)</th>
                    <th>Уход (план/факт)</th>
                    <th>Событие</th>
                    <th onClick={() => handleSort('confidence')} className="sortable">
                      Уверенность <SortIcon column="confidence" />
                    </th>
                    <th>Камера</th>
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedLogs.map((log) => {
                    const eventBadge = getEventBadge(log.event_type);
                    return (
                      <tr key={log.id} className="log-row">
                        <td className="timestamp-cell">
                          <strong>{formatDateTime(log.timestamp)}</strong>
                        </td>
                        <td className="employee-cell">
                          <strong>{log.employee_name}</strong>
                          <small>{log.employee_id}</small>
                        </td>
                        <td>{log.department || '—'}</td>
                        <td>
                          <div>
                            <strong>{log.schedule_check_in || '09:00'}</strong>
                            <small style={{ display: 'block', color: 'var(--text-muted)' }}>
                              {log.first_seen_today ? formatDateTime(log.first_seen_today).split(' ').slice(-1)[0] : '—'} ({getStatusLabel(log.arrival_status)})
                            </small>
                          </div>
                        </td>
                        <td>
                          <div>
                            <strong>{log.schedule_check_out || '18:00'}</strong>
                            <small style={{ display: 'block', color: 'var(--text-muted)' }}>
                              {log.last_seen_today ? formatDateTime(log.last_seen_today).split(' ').slice(-1)[0] : '—'} ({getStatusLabel(log.departure_status)})
                            </small>
                          </div>
                        </td>
                        <td>
                          <span className="event-badge" style={{ backgroundColor: eventBadge.color }}>
                            {eventBadge.text}
                          </span>
                        </td>
                        <td>
                          <div className="confidence-bar">
                            <div
                              className="confidence-progress"
                              style={{ width: `${(log.confidence || 0) * 100}%` }}
                            />
                            <span className="confidence-text">
                              {(log.confidence || 0) > 0 ? `${((log.confidence || 0) * 100).toFixed(0)}%` : '—'}
                            </span>
                          </div>
                        </td>
                        <td>{log.camera_name || '—'}</td>
                        <td>
                          <button
                            onClick={() => setSelectedLog(log)}
                            className="btn-icon"
                            title="Показать детали"
                          >
                            <FiImage size={18} />
                          </button>
                          {canEditAttendance && log.can_edit && (
                            <button
                              onClick={() => {
                                setSelectedLog(log);
                                openEditForLog(log);
                              }}
                              className="btn-icon"
                              title="Редактировать запись"
                            >
                              <FiEdit2 size={18} />
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="pagination">
                <button
                  className="btn btn-sm btn-secondary"
                  disabled={page <= 1}
                  onClick={() => setPage(page - 1)}
                >
                  <FiChevronLeft /> Назад
                </button>
                <span className="pagination-info">
                  Стр. {page} из {totalPages} ({totalLogs} записей)
                </span>
                <button
                  className="btn btn-sm btn-secondary"
                  disabled={page >= totalPages}
                  onClick={() => setPage(page + 1)}
                >
                  Вперед <FiChevronRight />
                </button>
              </div>
            )}
          </div>
        )}

        {!loading && scheduleRows.length > 0 && (
          <div className="card" style={{ marginTop: '1rem' }}>
            <div style={{ padding: '1rem 1rem 0.5rem 1rem' }}>
              <h3 style={{ margin: 0 }}>Таблица расписания и опозданий</h3>
            </div>
            <div className="table-responsive">
              <table className="attendance-table">
                <thead>
                  <tr>
                    <th>Дата</th>
                    <th>Сотрудник</th>
                    <th>Отдел</th>
                    <th>План прихода</th>
                    <th>Факт прихода</th>
                    <th>Опоздание (мин)</th>
                    <th>План ухода</th>
                    <th>Факт ухода</th>
                    <th>Ранний уход (мин)</th>
                    <th>Статус</th>
                  </tr>
                </thead>
                <tbody>
                  {scheduleRows.map((row) => (
                    <tr key={row.key}>
                      <td>{row.day}</td>
                      <td>
                        <strong>{row.employee_name}</strong>
                        <small style={{ display: 'block', color: 'var(--text-muted)' }}>{row.employee_id}</small>
                      </td>
                      <td>{row.department || '—'}</td>
                      <td>{row.schedule_check_in || '09:00'}</td>
                      <td>{formatTimeOnly(row.first_seen_today)}</td>
                      <td>
                        {row.lateMinutes === null ? '—' : row.lateMinutes > 0 ? row.lateMinutes : 0}
                      </td>
                      <td>{row.schedule_check_out || '18:00'}</td>
                      <td>{formatTimeOnly(row.last_seen_today)}</td>
                      <td>
                        {row.earlyLeaveMinutes === null ? '—' : row.earlyLeaveMinutes > 0 ? row.earlyLeaveMinutes : 0}
                      </td>
                      <td>
                        Приход: {getStatusLabel(row.arrival_status)}<br />
                        Уход: {getStatusLabel(row.departure_status)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Detail Modal */}
        {selectedLog && (
          <div className="modal-overlay" onClick={() => { setSelectedLog(null); setEditMode(false); }}>
            <div className="modal" onClick={(e) => e.stopPropagation()}>
              <div className="modal-header">
                <h2>Детали события</h2>
                <button className="btn-close" onClick={() => { setSelectedLog(null); setEditMode(false); }}>x</button>
              </div>
              <div className="modal-body">
                <div className="proof-info">
                  <div className="info-row">
                    <span className="info-label">Сотрудник:</span>
                    <span className="info-value">{selectedLog.employee_name}</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">ID:</span>
                    <span className="info-value">{selectedLog.employee_id}</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Отдел:</span>
                    <span className="info-value">{selectedLog.department || '—'}</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Событие:</span>
                    <span className="info-value">{getEventBadge(selectedLog.event_type).text}</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Приход (план/факт):</span>
                    <span className="info-value">
                      {(selectedLog.schedule_check_in || '09:00')} / {selectedLog.first_seen_today ? formatDateTime(selectedLog.first_seen_today).split(' ').slice(-1)[0] : '—'} ({getStatusLabel(selectedLog.arrival_status)})
                    </span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Уход (план/факт):</span>
                    <span className="info-value">
                      {(selectedLog.schedule_check_out || '18:00')} / {selectedLog.last_seen_today ? formatDateTime(selectedLog.last_seen_today).split(' ').slice(-1)[0] : '—'} ({getStatusLabel(selectedLog.departure_status)})
                    </span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Дата:</span>
                    <span className="info-value">{formatDateTime(selectedLog.timestamp)}</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Камера:</span>
                    <span className="info-value">{selectedLog.camera_name}</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Уверенность:</span>
                    <span className="info-value">
                      {((selectedLog.confidence || 0) * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>

                {canEditAttendance && (
                  <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--border-color)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                      <h3 style={{ margin: 0, fontSize: '1rem' }}>Редактирование посещаемости</h3>
                      {!editMode && selectedLog.can_edit && (
                        <button className="btn btn-secondary btn-sm" onClick={() => openEditForLog(selectedLog)}>
                          <FiEdit2 /> Редактировать
                        </button>
                      )}
                    </div>

                    {!selectedLog.can_edit ? (
                      <small style={{ color: 'var(--text-tertiary)' }}>
                        Можно редактировать только записи за последние 7 дней.
                      </small>
                    ) : editMode ? (
                      <div className="grid grid-2">
                        <div className="form-group">
                          <label className="form-label">Тип события</label>
                          <select
                            className="form-control"
                            value={editForm.event_type}
                            onChange={(e) => setEditForm(prev => ({ ...prev, event_type: e.target.value }))}
                          >
                            <option value="check-in">Вход</option>
                            <option value="check-out">Выход</option>
                          </select>
                        </div>
                        <div className="form-group">
                          <label className="form-label">Дата и время</label>
                          <input
                            type="datetime-local"
                            className="form-control"
                            value={editForm.timestamp}
                            onChange={(e) => setEditForm(prev => ({ ...prev, timestamp: e.target.value }))}
                          />
                        </div>
                        <div className="form-group">
                          <label className="form-label">Уверенность (0..1)</label>
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            max="1"
                            className="form-control"
                            value={editForm.confidence}
                            onChange={(e) => setEditForm(prev => ({ ...prev, confidence: e.target.value }))}
                          />
                        </div>
                        <div className="form-group" style={{ display: 'flex', alignItems: 'end', gap: '0.5rem' }}>
                          <button className="btn btn-primary" onClick={handleSaveEdit} disabled={savingEdit}>
                            {savingEdit ? 'Сохранение...' : 'Сохранить'}
                          </button>
                          <button className="btn btn-secondary" onClick={() => setEditMode(false)} disabled={savingEdit}>
                            Отмена
                          </button>
                        </div>
                      </div>
                    ) : (
                      <small style={{ color: 'var(--text-tertiary)' }}>
                        Доступно для ролей HR, Admin и Super Admin.
                      </small>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default Attendance;
