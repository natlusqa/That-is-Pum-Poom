import React from 'react';
import { Navigate } from 'react-router-dom';
import { authAPI } from '../services/api';

function ProtectedRoute({ children, roles }) {
  if (!authAPI.isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }

  if (roles && roles.length > 0) {
    const user = authAPI.getCurrentUser();
    if (!user || !roles.includes(user.role)) {
      return <Navigate to="/" replace />;
    }
  }

  return children;
}

export default ProtectedRoute;
