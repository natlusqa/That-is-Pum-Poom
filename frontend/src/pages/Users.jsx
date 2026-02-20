import React, { useState, useEffect } from 'react';
import { FiUser, FiPlus, FiTrash2, FiShield } from 'react-icons/fi';
import { userAPI } from '../services/api';
import { useToast } from '../components/ToastProvider';

function Users() {
  const currentUser = JSON.parse(localStorage.getItem('user') || '{}');
  const canManageUsers = currentUser?.role === 'super_admin';
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const { addToast } = useToast();
  const [formData, setFormData] = useState({
    username: '',
    password: '',
    role: 'employee',
  });

  useEffect(() => {
    loadUsers();
  }, []);

  const loadUsers = async () => {
    try {
      const response = await userAPI.getAll();
      setUsers(response.data);
    } catch (err) {
      setError('Ошибка загрузки пользователей');
      addToast('Ошибка загрузки пользователей', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleInputChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    try {
      await userAPI.create(formData);
      setSuccess('Пользователь создан!');
      setShowModal(false);
      resetForm();
      loadUsers();
    } catch (err) {
      setError(err.response?.data?.error || 'Ошибка при создании пользователя');
      addToast(err.response?.data?.error || 'Ошибка при создании пользователя', 'error');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Вы уверены, что хотите удалить этого пользователя?')) {
      return;
    }

    try {
      await userAPI.delete(id);
      setSuccess('Пользователь удалён');
      loadUsers();
    } catch (err) {
      setError(err.response?.data?.error || 'Ошибка при удалении пользователя');
      addToast(err.response?.data?.error || 'Ошибка при удалении пользователя', 'error');
    }
  };

  const resetForm = () => {
    setFormData({
      username: '',
      password: '',
      role: 'employee',
    });
  };

  const formatDate = (dateString) => {
    if (!dateString) {
      return '—';
    }
    return new Date(dateString).toLocaleDateString('ru-RU');
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
          <h1><FiUser /> Управление пользователями</h1>
          {canManageUsers && (
            <button
              onClick={() => setShowModal(true)}
              className="btn btn-primary"
            >
              <FiPlus /> Добавить пользователя
            </button>
          )}
        </div>

        {!canManageUsers && (
          <div className="alert alert-info">
            Только Super Admin может добавлять пользователей и назначать роли.
          </div>
        )}

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

        <div className="card">
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Имя пользователя</th>
                  <th>Роль</th>
                  <th>Дата создания</th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id}>
                    <td>{user.id}</td>
                    <td><strong>{user.username}</strong></td>
                    <td>
                      {user.role === 'super_admin' && (
                        <span className="badge badge-danger">
                          <FiShield /> Super Admin
                        </span>
                      )}
                      {user.role === 'admin' && (
                        <span className="badge badge-warning">
                          <FiShield /> Admin
                        </span>
                      )}
                      {user.role === 'hr' && (
                        <span className="badge badge-info">
                          <FiUser /> HR
                        </span>
                      )}
                      {user.role === 'employee' && (
                        <span className="badge badge-gray">
                          <FiUser /> Сотрудник
                        </span>
                      )}
                    </td>
                    <td>{formatDate(user.created_at)}</td>
                    <td>
                      {canManageUsers ? (
                        <button
                          onClick={() => handleDelete(user.id)}
                          className="btn btn-sm btn-danger"
                        >
                          <FiTrash2 /> Удалить
                        </button>
                      ) : (
                        <span style={{ color: '#94a3b8' }}>Нет прав</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {showModal && (
          <div className="modal-overlay" onClick={() => setShowModal(false)}>
            <div className="modal" onClick={(e) => e.stopPropagation()}>
              <div className="modal-header">
                <h2 className="modal-title">Добавить пользователя</h2>
                <button onClick={() => setShowModal(false)} className="btn btn-icon">×</button>
              </div>

              <form onSubmit={handleSubmit}>
                <div className="modal-body">
                  <div className="form-group">
                    <label className="form-label">Имя пользователя *</label>
                    <input
                      type="text"
                      name="username"
                      className="form-control"
                      value={formData.username}
                      onChange={handleInputChange}
                      placeholder="username"
                      required
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Пароль *</label>
                    <input
                      type="password"
                      name="password"
                      className="form-control"
                      value={formData.password}
                      onChange={handleInputChange}
                      placeholder="••••••••"
                      minLength="6"
                      required
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Роль *</label>
                    <select
                      name="role"
                      className="form-control"
                      value={formData.role}
                      onChange={handleInputChange}
                      required
                    >
                      <option value="employee">Сотрудник (наблюдатель)</option>
                      <option value="hr">HR (сотрудники)</option>
                      <option value="admin">Admin (сотрудники + камеры)</option>
                      <option value="super_admin">Super Admin (полный доступ)</option>
                    </select>
                  </div>

                  <div className="alert alert-info">
                    <div><strong>Сотрудник:</strong> только просмотр</div>
                    <div><strong>HR:</strong> добавление/удаление сотрудников</div>
                    <div><strong>Admin:</strong> сотрудники + камеры</div>
                    <div><strong>Super Admin:</strong> полный доступ</div>
                  </div>
                </div>

                <div className="modal-footer">
                  <button type="button" onClick={() => setShowModal(false)} className="btn btn-secondary">
                    Отмена
                  </button>
                  <button type="submit" className="btn btn-primary">
                    <FiPlus /> Создать
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

export default Users;
