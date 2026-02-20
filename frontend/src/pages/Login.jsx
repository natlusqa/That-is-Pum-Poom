import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FiVideo, FiUser, FiLock, FiLogIn } from 'react-icons/fi';
import { authAPI } from '../services/api';
import { useToast } from '../components/ToastProvider';
import './Login.css';

function Login({ onLogin }) {
  const navigate = useNavigate();
  const { addToast } = useToast();
  const [credentials, setCredentials] = useState({
    username: '',
    password: '',
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const response = await authAPI.login(credentials);
      if (onLogin) {
        onLogin(response.data.user, response.data.token);
      } else {
        localStorage.setItem('token', response.data.token);
        localStorage.setItem('user', JSON.stringify(response.data.user));
      }
      navigate('/');
    } catch (err) {
      setError(err.response?.data?.error || 'Ошибка входа. Проверьте данные.');
      addToast(err.response?.data?.error || 'Ошибка входа. Проверьте данные.', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (e) => {
    setCredentials({
      ...credentials,
      [e.target.name]: e.target.value,
    });
  };

  return (
    <div className="login-page">
      <div className="login-container">
        <div className="login-card">
          <div className="login-header">
            <FiVideo size={48} className="login-icon" />
            <h1>Система видеонаблюдения</h1>
            <p>с распознаванием лиц</p>
          </div>

          {error && (
            <div className="alert alert-error">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">
                <FiUser /> Имя пользователя
              </label>
              <input
                type="text"
                name="username"
                className="form-control"
                value={credentials.username}
                onChange={handleChange}
                placeholder="admin"
                required
                autoFocus
              />
            </div>

            <div className="form-group">
              <label className="form-label">
                <FiLock /> Пароль
              </label>
              <input
                type="password"
                name="password"
                className="form-control"
                value={credentials.password}
                onChange={handleChange}
                placeholder="••••••••"
                required
              />
            </div>

            <button
              type="submit"
              className="btn btn-primary btn-block"
              disabled={loading}
            >
              {loading ? (
                <>
                  <div className="spinner-small"></div>
                  Вход...
                </>
              ) : (
                <>
                  <FiLogIn />
                  Войти
                </>
              )}
            </button>
          </form>

          <div className="login-footer">
            <p className="login-hint">
              По умолчанию: <strong>admin</strong> / <strong>admin123</strong>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Login;
