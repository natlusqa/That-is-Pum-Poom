import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { useCallback, useEffect, useMemo, useState } from 'react';
import Layout from './components/Layout/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import { authAPI } from './services/api';
import { ToastProvider } from './components/ToastProvider';

import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Cameras from './pages/Cameras';
import CameraDiscovery from './pages/CameraDiscovery';
import Employees from './pages/Employees';
import CameraView from './pages/CameraView';
import Attendance from './pages/Attendance';
import Users from './pages/Users';
import Recordings from './pages/Playback';
import LoginHistory from './pages/LoginHistory';

const THEME_STORAGE_KEY = 'ui_theme';

function App() {
  const [user, setUser] = useState(() => authAPI.getCurrentUser());
  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem(THEME_STORAGE_KEY);
    return saved === 'light' ? 'light' : 'dark';
  });

  const handleLogin = useCallback((nextUser, token) => {
    localStorage.setItem('token', token);
    localStorage.setItem('user', JSON.stringify(nextUser));
    setUser(nextUser);
  }, []);

  const handleLogout = useCallback(() => {
    authAPI.logout();
    setUser(null);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  const layoutProps = useMemo(
    () => ({
      user,
      onLogout: handleLogout,
      theme,
      onToggleTheme: toggleTheme,
    }),
    [user, handleLogout, theme, toggleTheme]
  );

  return (
    <ToastProvider>
      <BrowserRouter>
        <Routes>

        {/* Публичная страница */}
        <Route path="/login" element={<Login onLogin={handleLogin} />} />

        {/* Защищённая зона */}
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout {...layoutProps} />
            </ProtectedRoute>
          }
        >
          <Route index element={<Dashboard />} />
          <Route
            path="cameras"
            element={
              <ProtectedRoute roles={['admin', 'super_admin']}>
                <Cameras />
              </ProtectedRoute>
            }
          />
          <Route
            path="camera-discovery"
            element={
              <ProtectedRoute roles={['admin', 'super_admin']}>
                <CameraDiscovery />
              </ProtectedRoute>
            }
          />
          <Route
            path="camera/:id"
            element={
              <ProtectedRoute roles={['admin', 'super_admin']}>
                <CameraView />
              </ProtectedRoute>
            }
          />
          <Route
            path="employees"
            element={
              <ProtectedRoute roles={['hr', 'admin', 'super_admin']}>
                <Employees user={user} />
              </ProtectedRoute>
            }
          />
          <Route path="attendance" element={<Attendance />} />
          <Route path="recordings" element={<Recordings />} />
          <Route
            path="login-history"
            element={
              <ProtectedRoute roles={['admin', 'super_admin']}>
                <LoginHistory />
              </ProtectedRoute>
            }
          />
          <Route
            path="users"
            element={
              <ProtectedRoute roles={['admin', 'super_admin']}>
                <Users />
              </ProtectedRoute>
            }
          />
        </Route>

        </Routes>
      </BrowserRouter>
    </ToastProvider>
  );
}

export default App;
