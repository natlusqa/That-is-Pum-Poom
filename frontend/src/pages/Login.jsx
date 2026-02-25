import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FiShield, FiUser, FiLock, FiLogIn } from 'react-icons/fi';
import { authAPI } from '../services/api';
import { useToast } from '../components/ToastProvider';
import './Login.css';

function Login({ onLogin }) {
  const navigate = useNavigate();
  const { addToast } = useToast();
  const [credentials, setCredentials] = useState({ username: '', password: '' });
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
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
      const msg = err.response?.data?.error || 'Login failed. Check your credentials.';
      addToast(msg, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (e) => {
    setCredentials({ ...credentials, [e.target.name]: e.target.value });
  };

  return (
    <div className="login-page">
      <div className="login-container">
        <div className="login-card">
          <div className="login-header">
            <FiShield size={48} className="login-icon" />
            <h1>Surveillance AI</h1>
            <p>Intelligent video monitoring system</p>
          </div>

          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">
                <FiUser size={14} /> Username
              </label>
              <input
                type="text"
                name="username"
                className="form-control"
                value={credentials.username}
                onChange={handleChange}
                placeholder="Enter username"
                required
                autoFocus
                autoComplete="username"
              />
            </div>

            <div className="form-group">
              <label className="form-label">
                <FiLock size={14} /> Password
              </label>
              <input
                type="password"
                name="password"
                className="form-control"
                value={credentials.password}
                onChange={handleChange}
                placeholder="Enter password"
                required
                autoComplete="current-password"
              />
            </div>

            <button type="submit" className="btn btn-primary btn-block" disabled={loading}>
              {loading ? (
                <><div className="spinner-small"></div> Signing in...</>
              ) : (
                <><FiLogIn /> Sign In</>
              )}
            </button>
          </form>

          <div className="login-footer">
            <p className="login-hint">
              Default: <strong>admin</strong> / <strong>admin123</strong>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Login;
