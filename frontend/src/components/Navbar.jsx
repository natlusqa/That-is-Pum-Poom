import { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import {
  FiHome, FiVideo, FiUsers, FiClock, FiSearch,
  FiUserCheck, FiLogOut, FiChevronLeft, FiChevronRight, FiShield
} from 'react-icons/fi';
import { authAPI } from '../services/api';
import './Navbar.css';

const Navbar = ({ user, onLogout }) => {
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(false);

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
          ? 'Employee'
          : role || '';

  const userInitial = user?.username
    ? user.username.charAt(0).toUpperCase()
    : '?';

  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
      {/* Collapse toggle */}
      <button
        className="sidebar-toggle"
        onClick={() => setCollapsed(!collapsed)}
        title={collapsed ? 'Expand' : 'Collapse'}
      >
        {collapsed ? <FiChevronRight /> : <FiChevronLeft />}
      </button>

      {/* Brand */}
      <div className="sidebar-brand">
        <div className="sidebar-logo">
          <FiShield />
        </div>
        <div className="sidebar-brand-text">
          <div className="sidebar-brand-name">Surveillance AI</div>
          <div className="sidebar-brand-sub">Smart Monitoring</div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="sidebar-nav">
        <div className="sidebar-section-label">Main</div>

        <NavLink to="/" end className={({ isActive }) =>
          `sidebar-nav-link ${isActive ? 'active' : ''}`
        }>
          <FiHome />
          <span className="sidebar-nav-label">Dashboard</span>
        </NavLink>

        {canManageCameras && (
          <NavLink to="/cameras" className={({ isActive }) =>
            `sidebar-nav-link ${isActive ? 'active' : ''}`
          }>
            <FiVideo />
            <span className="sidebar-nav-label">Cameras</span>
          </NavLink>
        )}

        {canManageCameras && (
          <NavLink to="/camera-discovery" className={({ isActive }) =>
            `sidebar-nav-link ${isActive ? 'active' : ''}`
          }>
            <FiSearch />
            <span className="sidebar-nav-label">Discovery</span>
          </NavLink>
        )}

        <div className="sidebar-section-label">HR</div>

        {canManageEmployees && (
          <NavLink to="/employees" className={({ isActive }) =>
            `sidebar-nav-link ${isActive ? 'active' : ''}`
          }>
            <FiUsers />
            <span className="sidebar-nav-label">Employees</span>
          </NavLink>
        )}

        <NavLink to="/attendance" className={({ isActive }) =>
          `sidebar-nav-link ${isActive ? 'active' : ''}`
        }>
          <FiClock />
          <span className="sidebar-nav-label">Attendance</span>
        </NavLink>

        {canManageUsers && (
          <>
            <div className="sidebar-section-label">System</div>
            <NavLink to="/users" className={({ isActive }) =>
              `sidebar-nav-link ${isActive ? 'active' : ''}`
            }>
              <FiUserCheck />
              <span className="sidebar-nav-label">Users</span>
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

      {/* Logout */}
      <button className="sidebar-logout" onClick={handleLogout}>
        <FiLogOut />
        <span className="sidebar-logout-label">Logout</span>
      </button>
    </aside>
  );
};

export default Navbar;
