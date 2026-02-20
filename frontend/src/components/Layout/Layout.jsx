import React from 'react';
import { Outlet } from 'react-router-dom';
import Navbar from '../Navbar';
import './Layout.css';

function Layout({ user, onLogout }) {
  return (
    <div className="app-layout">
      <Navbar user={user} onLogout={onLogout} />
      <main className="app-content">
        <Outlet />
      </main>
    </div>
  );
}

export default Layout;
