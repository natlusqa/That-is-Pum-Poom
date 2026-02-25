import React from 'react';
import { Outlet } from 'react-router-dom';
import Navbar from '../Navbar';
import './Layout.css';

function Layout({ user, onLogout, theme, onToggleTheme }) {
  return (
    <div className="app-layout">
      <Navbar user={user} onLogout={onLogout} theme={theme} onToggleTheme={onToggleTheme} />
      <main className="app-content">
        <Outlet />
      </main>
    </div>
  );
}

export default Layout;
