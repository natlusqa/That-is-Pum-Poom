import React, { useState, useEffect, useMemo } from 'react';
import { FiUsers, FiPlus, FiTrash2, FiUser, FiEdit2, FiRefreshCw } from 'react-icons/fi';
import { employeeAPI, departmentAPI } from '../services/api';
import { useToast } from '../components/ToastProvider';
import { useAuthImage } from '../hooks/useAuthImage';
import './Employees.css';

function EmployeeAvatar({ emp, getEmployeePhotoUrl }) {
  const imageUrl = emp.photo_path ? getEmployeePhotoUrl(emp.photo_path) : '';
  const { blobUrl, error } = useAuthImage(imageUrl);

  if (blobUrl && !error) {
    return (
      <img
        src={blobUrl}
        alt={emp.name || 'Сотрудник'}
        className="employee-avatar-img"
      />
    );
  }

  return <FiUser />;
}

function Employees({ user }) {
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [departments, setDepartments] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingEmployee, setEditingEmployee] = useState(null);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const { addToast } = useToast();

  const [formData, setFormData] = useState({
    name: '',
    position: '',
    department: '',
    photo: null, // FILE
  });
  const [editFormData, setEditFormData] = useState({
    name: '',
    position: '',
    department: '',
  });

  const [photoPreview, setPhotoPreview] = useState(null);

  useEffect(() => {
    Promise.all([loadEmployees(), loadDepartments()]);
  }, []);

  const loadEmployees = async () => {
    try {
      const res = await employeeAPI.getAll({ include_inactive: true });
      setEmployees(res.data);
    } catch {
      setError('Ошибка загрузки сотрудников');
      addToast('Ошибка загрузки сотрудников', 'error');
    } finally {
      setLoading(false);
    }
  };

  const loadDepartments = async () => {
    try {
      const res = await departmentAPI.getAll();
      setDepartments(res.data || []);
    } catch {
      // Не блокируем страницу сотрудников, если отделы не загрузились
      setDepartments([]);
    }
  };

  const handleInputChange = (e) => {
    setFormData(prev => ({
      ...prev,
      [e.target.name]: e.target.value,
    }));
  };

  const handlePhotoChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setFormData(prev => ({
      ...prev,
      photo: file, // ✅ File
    }));

    setPhotoPreview(URL.createObjectURL(file));
  };

  const resetForm = () => {
    setFormData({
      name: '',
      position: '',
      department: '',
      photo: null,
    });
    setPhotoPreview(null);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setSubmitting(true);

    if (!formData.photo) {
      setError('Загрузите фото сотрудника');
      addToast('Загрузите фото сотрудника', 'error');
      setSubmitting(false);
      return;
    }

    try {
      const data = new FormData();
      data.append('name', formData.name);
      data.append('position', formData.position);
      data.append('department', formData.department);
      data.append('photo', formData.photo); // ✅ multipart

      const response = await employeeAPI.create(data);
      const createdEmployeeId = response?.data?.employee_id;

      setSuccess(createdEmployeeId
        ? `Сотрудник успешно добавлен. ID: ${createdEmployeeId}`
        : 'Сотрудник успешно добавлен');
      setShowModal(false);
      resetForm();
      Promise.all([loadEmployees(), loadDepartments()]);
    } catch (err) {
      setError(err.response?.data?.error || 'Ошибка при добавлении');
      addToast(err.response?.data?.error || 'Ошибка при добавлении', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const openEditModal = (emp) => {
    setEditingEmployee(emp);
    setEditFormData({
      name: emp.name || '',
      position: emp.position || '',
      department: emp.department || '',
    });
    setShowEditModal(true);
  };

  const handleEditInputChange = (e) => {
    setEditFormData(prev => ({
      ...prev,
      [e.target.name]: e.target.value,
    }));
  };

  const handleEditSubmit = async (e) => {
    e.preventDefault();
    if (!editingEmployee) return;

    setError('');
    setSuccess('');

    try {
      await employeeAPI.update(editingEmployee.id, {
        name: editFormData.name,
        position: editFormData.position,
        department: editFormData.department,
      });
      setSuccess('Данные сотрудника обновлены');
      setShowEditModal(false);
      setEditingEmployee(null);
      Promise.all([loadEmployees(), loadDepartments()]);
    } catch (err) {
      setError(err.response?.data?.error || 'Ошибка при редактировании');
      addToast(err.response?.data?.error || 'Ошибка при редактировании', 'error');
    }
  };

  const handleDeactivate = async (id) => {
    if (!window.confirm('Деактивировать сотрудника?')) return;

    try {
      await employeeAPI.update(id, { active: false });
      setSuccess('Сотрудник деактивирован');
      loadEmployees();
    } catch {
      setError('Ошибка деактивации');
      addToast('Ошибка деактивации', 'error');
    }
  };

  const handleActivate = async (id) => {
    if (!window.confirm('Активировать сотрудника?')) return;

    try {
      await employeeAPI.update(id, { active: true });
      setSuccess('Сотрудник активирован');
      loadEmployees();
    } catch {
      setError('Ошибка активации');
      addToast('Ошибка активации', 'error');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Удалить сотрудника навсегда?')) return;

    try {
      await employeeAPI.delete(id);
      setSuccess('Сотрудник удалён');
      loadEmployees();
    } catch {
      setError('Ошибка удаления');
      addToast('Ошибка удаления', 'error');
    }
  };

  const getEmployeePhotoUrl = (photoPath) => {
    if (!photoPath) return '';
    const encodedPath = encodeURIComponent(photoPath);
    return `/api/employees/photo/${encodedPath}`;
  };

  const groupedEmployees = useMemo(() => {
    const grouped = {};
    employees.forEach((emp) => {
      const key = (emp.department || 'Без отдела').trim() || 'Без отдела';
      if (!grouped[key]) {
        grouped[key] = [];
      }
      grouped[key].push(emp);
    });
    return Object.entries(grouped).sort(([a], [b]) => a.localeCompare(b, 'ru'));
  }, [employees]);

  if (loading) {
    return <div className="loading"><div className="spinner" /></div>;
  }

  return (
    <div className="page-container">
      <div className="page-header flex-between">
        <h1><FiUsers /> Сотрудники</h1>
        {['hr', 'admin', 'super_admin'].includes(user?.role) && (
          <button className="btn btn-primary" onClick={() => setShowModal(true)}>
            <FiPlus /> Добавить
          </button>
        )}
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {success && <div className="alert alert-success">{success}</div>}

      {groupedEmployees.map(([departmentName, departmentEmployees]) => (
        <section key={departmentName} className="department-section">
          <div className="department-header">
            <h2>{departmentName}</h2>
            <span>{departmentEmployees.length} чел.</span>
          </div>
          <div className="grid grid-3">
            {departmentEmployees.map(emp => (
              <div key={emp.id} className="employee-card">
                <div className="employee-avatar">
                  <EmployeeAvatar emp={emp} getEmployeePhotoUrl={getEmployeePhotoUrl} />
                </div>
                <h3>{emp.name}</h3>
                <p>ID: {emp.employee_id}</p>
                <p>{emp.position || '—'}</p>
                <p>{emp.department || '—'}</p>
                <p>Статус: {emp.active ? 'Активен' : 'Неактивен'}</p>

                {['hr', 'admin', 'super_admin'].includes(user?.role) && (
                  <div className="btn-group">
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => openEditModal(emp)}
                    >
                      <FiEdit2 /> Изменить
                    </button>
                    {emp.active ? (
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => handleDeactivate(emp.id)}
                      >
                        <FiRefreshCw /> Деактивировать
                      </button>
                    ) : (
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={() => handleActivate(emp.id)}
                      >
                        <FiRefreshCw /> Активировать
                      </button>
                    )}
                    <button
                      className="btn btn-danger btn-sm"
                      onClick={() => handleDelete(emp.id)}
                    >
                      <FiTrash2 /> Удалить
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      ))}

      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2 className="modal-title">Добавить сотрудника</h2>
              <button onClick={() => setShowModal(false)} className="btn btn-icon">×</button>
            </div>

            <form onSubmit={handleSubmit}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">ФИО *</label>
                  <input
                    name="name"
                    className="form-control"
                    placeholder="Иванов Иван"
                    required
                    onChange={handleInputChange}
                  />
                </div>

                <div className="grid grid-2">
                  <div className="form-group">
                    <label className="form-label">Должность</label>
                    <input
                      name="position"
                      className="form-control"
                      placeholder="Sys admin"
                      onChange={handleInputChange}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Отдел</label>
                    <input
                      name="department"
                      className="form-control"
                      placeholder="IT"
                      list="department-options"
                      required
                      onChange={handleInputChange}
                    />
                    <datalist id="department-options">
                      {departments.map((dep) => (
                        <option key={dep.id} value={dep.name} />
                      ))}
                    </datalist>
                    <span className="form-text">ID сотрудника генерируется автоматически по отделу: 1..., 2..., 3...</span>
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Фото *</label>
                  <input type="file" accept="image/*" onChange={handlePhotoChange} required />
                  <span className="form-text">Загрузите фото лица для распознавания.</span>
                </div>

                {photoPreview && (
                  <div className="photo-preview">
                    <img src={photoPreview} alt="Предпросмотр" />
                  </div>
                )}
              </div>

              <div className="modal-footer">
                <button type="button" onClick={() => setShowModal(false)} className="btn btn-secondary">
                  Отмена
                </button>
                <button type="submit" className="btn btn-primary" disabled={submitting}>
                  {submitting ? 'Добавление...' : 'Добавить'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showEditModal && editingEmployee && (
        <div className="modal-overlay" onClick={() => setShowEditModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2 className="modal-title">Редактировать сотрудника</h2>
              <button onClick={() => setShowEditModal(false)} className="btn btn-icon">×</button>
            </div>

            <form onSubmit={handleEditSubmit}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">ФИО *</label>
                  <input
                    name="name"
                    className="form-control"
                    value={editFormData.name}
                    onChange={handleEditInputChange}
                    required
                  />
                </div>

                <div className="grid grid-2">
                  <div className="form-group">
                    <label className="form-label">Должность</label>
                    <input
                      name="position"
                      className="form-control"
                      value={editFormData.position}
                      onChange={handleEditInputChange}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Отдел</label>
                    <input
                      name="department"
                      className="form-control"
                      list="department-options"
                      value={editFormData.department}
                      onChange={handleEditInputChange}
                      required
                    />
                    <datalist id="department-options">
                      {departments.map((dep) => (
                        <option key={dep.id} value={dep.name} />
                      ))}
                    </datalist>
                  </div>
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" onClick={() => setShowEditModal(false)} className="btn btn-secondary">
                  Отмена
                </button>
                <button type="submit" className="btn btn-primary">
                  <FiEdit2 /> Сохранить
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default Employees;
