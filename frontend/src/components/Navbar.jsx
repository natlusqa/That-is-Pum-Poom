import { NavLink, useNavigate } from 'react-router-dom';
import { authAPI } from '../services/api';
import './Navbar.css';

const Navbar = ({ user, onLogout }) => {
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
    ? 'Super Admin'
    : role === 'admin'
      ? 'Admin'
      : role === 'hr'
        ? 'HR'
        : role === 'employee'
          ? 'Сотрудник'
          : role || '';

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h2>Видеотрекер</h2>
      </div>

      <nav className="sidebar-nav">
        <NavLink to="/" end>Главная</NavLink>
        {canManageEmployees && <NavLink to="/employees">Сотрудники</NavLink>}
        {canManageCameras && <NavLink to="/cameras">Камеры</NavLink>}
        <NavLink to="/attendance">Посещаемость</NavLink>
        {canManageUsers && <NavLink to="/users">Пользователи</NavLink>}
      </nav>

      {user && (
        <div className="sidebar-user">
          <div className="sidebar-user-name">{user.username}</div>
          <div className="sidebar-user-role">{roleLabel}</div>
        </div>
      )}

      <button className="logout-btn" onClick={handleLogout}>
        Выйти
      </button>
    </aside>
  );
};

export default Navbar;
