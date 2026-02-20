import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { useCallback, useMemo, useState } from 'react';
import Layout from './components/Layout/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import { authAPI } from './services/api';
import { ToastProvider } from './components/ToastProvider';

import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Cameras from './pages/Cameras';
import Employees from './pages/Employees';
import CameraView from './pages/CameraView';
import Attendance from './pages/Attendance';
import Users from './pages/Users';

function App() {
  const [user, setUser] = useState(() => authAPI.getCurrentUser());

  const handleLogin = useCallback((nextUser, token) => {
    localStorage.setItem('token', token);
    localStorage.setItem('user', JSON.stringify(nextUser));
    setUser(nextUser);
  }, []);

  const handleLogout = useCallback(() => {
    authAPI.logout();
    setUser(null);
  }, []);

  const layoutProps = useMemo(
    () => ({
      user,
      onLogout: handleLogout,
    }),
    [user, handleLogout]
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
