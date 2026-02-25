import { NavLink, useNavigate } from 'react-router-dom';
import {
  FiHome, FiVideo, FiUsers, FiClock, FiFilm,
  FiUserCheck, FiLogOut, FiShield, FiSun, FiMoon, FiActivity
} from 'react-icons/fi';
import { authAPI } from '../services/api';
import './Navbar.css';

const Navbar = ({ user, onLogout, theme = 'dark', onToggleTheme }) => {
  const navigate = useNavigate();

  const handleLogout = () => {
    if (onLogout) {
      onLogout();
    } else {
      authAPI.logout();
    }
    navigate('/login');
  };

  const role = user?.role;
  const canManageEmployees = ['hr', 'admin', 'super_admin'].includes(role);
  const canManageCameras = ['admin', 'super_admin'].includes(role);
  const canManageUsers = ['admin', 'super_admin'].includes(role);

  const roleLabel = role === 'super_admin'
    ? 'Супер админ'
    : role === 'admin'
      ? 'Админ'
      : role === 'hr'
        ? 'Кадры'
        : role === 'employee'
          ? 'Сотрудник'
          : role || '';

  const userInitial = user?.username
    ? user.username.charAt(0).toUpperCase()
    : '?';

  return (
    <aside className="sidebar">
      {/* Brand */}
      <div className="sidebar-brand">
        <div className="sidebar-logo">
          <FiShield />
        </div>
        <div className="sidebar-brand-text">
          <div className="sidebar-brand-name">Surveillance AI</div>
          <div className="sidebar-brand-sub">Умный мониторинг</div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="sidebar-nav">
        <div className="sidebar-section-label">Основное</div>

        <NavLink to="/" end className={({ isActive }) =>
          `sidebar-nav-link ${isActive ? 'active' : ''}`
        }>
          <FiHome />
          <span className="sidebar-nav-label">Панель</span>
        </NavLink>

        {canManageCameras && (
          <NavLink to="/cameras" className={({ isActive }) =>
            `sidebar-nav-link ${isActive ? 'active' : ''}`
          }>
            <FiVideo />
            <span className="sidebar-nav-label">Камеры</span>
          </NavLink>
        )}

        <div className="sidebar-section-label">Кадры</div>

        {canManageEmployees && (
          <NavLink to="/employees" className={({ isActive }) =>
            `sidebar-nav-link ${isActive ? 'active' : ''}`
          }>
            <FiUsers />
            <span className="sidebar-nav-label">Сотрудники</span>
          </NavLink>
        )}

        <NavLink to="/attendance" className={({ isActive }) =>
          `sidebar-nav-link ${isActive ? 'active' : ''}`
        }>
          <FiClock />
          <span className="sidebar-nav-label">Посещаемость</span>
        </NavLink>

        <NavLink to="/recordings" className={({ isActive }) =>
          `sidebar-nav-link ${isActive ? 'active' : ''}`
        }>
          <FiFilm />
          <span className="sidebar-nav-label">Записи</span>
        </NavLink>

        {canManageUsers && (
          <>
            <div className="sidebar-section-label">Система</div>
            <NavLink to="/login-history" className={({ isActive }) =>
              `sidebar-nav-link ${isActive ? 'active' : ''}`
            }>
              <FiActivity />
              <span className="sidebar-nav-label">История входов</span>
            </NavLink>
            <NavLink to="/users" className={({ isActive }) =>
              `sidebar-nav-link ${isActive ? 'active' : ''}`
            }>
              <FiUserCheck />
              <span className="sidebar-nav-label">Пользователи</span>
            </NavLink>
          </>
        )}
      </nav>

      {/* User profile */}
      {user && (
        <div className="sidebar-user">
          <div className="sidebar-user-avatar">{userInitial}</div>
          <div className="sidebar-user-info">
            <div className="sidebar-user-name">{user.username}</div>
            <div className="sidebar-user-role">{roleLabel}</div>
          </div>
        </div>
      )}

      {/* Theme toggle */}
      <button className="sidebar-theme-toggle" onClick={onToggleTheme} title="Переключить тему">
        {theme === 'dark' ? <FiSun /> : <FiMoon />}
        <span className="sidebar-theme-label">
          {theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
        </span>
      </button>

      {/* Logout */}
      <button className="sidebar-logout" onClick={handleLogout}>
        <FiLogOut />
        <span className="sidebar-logout-label">Выход</span>
      </button>
    </aside>
  );
};

export default Navbar;
