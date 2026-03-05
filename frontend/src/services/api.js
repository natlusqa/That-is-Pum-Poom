import axios from 'axios';

const API_BASE_URL = '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
});

// JWT token interceptor
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 401 auto-logout
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// --- AUTH ---
export const authAPI = {
  login: (credentials) => api.post('/auth/login', credentials),
  logout: () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
  },
  getCurrentUser: () => {
    const user = localStorage.getItem('user');
    return user ? JSON.parse(user) : null;
  },
  isAuthenticated: () => !!localStorage.getItem('token'),
};

// --- CAMERAS ---
export const cameraAPI = {
  getAll: () => api.get('/cameras'),
  getById: (id) => api.get(`/cameras/${id}`),
  create: (data) => api.post('/cameras', data),
  update: (id, data) => api.put(`/cameras/${id}`, data),
  delete: (id) => api.delete(`/cameras/${id}`),
  getVideoUrl: (id) => `${API_BASE_URL}/video/${id}`,
};

// --- CAMERA DISCOVERY ---
export const discoveryAPI = {
  startScan: (data = {}) => api.post('/camera-discovery/scan', data),
  stopScan: () => api.post('/camera-discovery/stop'),
  getStatus: () => api.get('/camera-discovery/status'),
  addCamera: (data) => api.post('/camera-discovery/add', data),
  addAll: (data = {}) => api.post('/camera-discovery/add-all', data),
};

// --- EMPLOYEES ---
export const employeeAPI = {
  getAll: (params) => api.get('/employees', { params }),
  getById: (id) => api.get(`/employees/${id}`),
  create: (formData) =>
    api.post('/employees', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  update: (id, data) => api.put(`/employees/${id}`, data),
  delete: (id) => api.delete(`/employees/${id}`),
};

// --- DEPARTMENTS ---
export const departmentAPI = {
  getAll: () => api.get('/departments'),
  create: (data) => api.post('/departments', data),
};

// --- ATTENDANCE ---
export const attendanceAPI = {
  getAll: (params) => api.get('/attendance', { params }),
  getByDate: (date) => api.get('/attendance', { params: { date } }),
  getByEmployee: (employeeId) =>
    api.get('/attendance', { params: { employee_id: employeeId } }),
  update: (id, data) => api.put(`/attendance/${id}`, data),
  getStats: (params) => api.get('/attendance/stats', { params }),
  export: (params) => api.get('/attendance/export', { params }),
};

// --- USERS ---
export const userAPI = {
  getAll: () => api.get('/users'),
  create: (data) => api.post('/users', data),
  update: (id, data) => api.put(`/users/${id}`, data),
  delete: (id) => api.delete(`/users/${id}`),
};

// --- AUDIT ---
export const auditAPI = {
  getLoginHistory: (params) => api.get('/audit/logins', { params }),
};

// --- HEALTH ---
export const healthAPI = {
  check: () => api.get('/health'),
};

export default api;
