import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FiShield, FiUser, FiLock, FiLogIn, FiEye, FiEyeOff } from 'react-icons/fi';
import { authAPI } from '../services/api';
import { useToast } from '../components/ToastProvider';
import './Login.css';

function Login({ onLogin }) {
  const navigate = useNavigate();
  const { addToast } = useToast();
  const [credentials, setCredentials] = useState({ username: '', password: '' });
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [authError, setAuthError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setAuthError('');

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
      const msg = err.response?.status === 401
        ? 'Неправильный логин или пароль'
        : (err.response?.data?.error || 'Не удалось войти. Проверьте логин и пароль.');
      setAuthError(msg);
      addToast(msg, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (e) => {
    if (authError) setAuthError('');
    setCredentials({ ...credentials, [e.target.name]: e.target.value });
  };

  return (
    <div className="login-page">
      <div className="login-container">
        <div className="login-card">
          <div className="login-header">
            <FiShield size={48} className="login-icon" />
            <h1>Surveillance AI</h1>
            <p>Интеллектуальная система видеомониторинга</p>
          </div>

          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">
                <FiUser size={14} /> Имя пользователя
              </label>
              <input
                type="text"
                name="username"
                className="form-control"
                value={credentials.username}
                onChange={handleChange}
                placeholder="Введите имя пользователя"
                required
                autoFocus
                autoComplete="username"
              />
            </div>

            <div className="form-group">
              <label className="form-label">
                <FiLock size={14} /> Пароль
              </label>
              <div className="password-input-wrap">
                <input
                  type={showPassword ? 'text' : 'password'}
                  name="password"
                  className="form-control"
                  value={credentials.password}
                  onChange={handleChange}
                  placeholder="Введите пароль"
                  required
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  className="password-toggle-btn"
                  onClick={() => setShowPassword((prev) => !prev)}
                  title={showPassword ? 'Скрыть пароль' : 'Показать пароль'}
                  aria-label={showPassword ? 'Скрыть пароль' : 'Показать пароль'}
                >
                  {showPassword ? <FiEyeOff size={16} /> : <FiEye size={16} />}
                </button>
              </div>
            </div>

            {authError && (
              <div className="alert alert-error" style={{ marginBottom: '14px' }}>
                {authError}
              </div>
            )}

            <button type="submit" className="btn btn-primary btn-block" disabled={loading}>
              {loading ? (
                <><div className="spinner-small"></div> Вход...</>
              ) : (
                <><FiLogIn /> Войти</>
              )}
            </button>
          </form>

          <div className="login-footer">
            <p className="login-hint">Surveillance AI &mdash; Безопасный доступ</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Login;
