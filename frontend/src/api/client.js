import axios from 'axios';
// Keep browser requests on the Vite origin in development. The dev proxy forwards
// /api and /health to FastAPI and avoids CORS failures when Vite picks 5174+.
const API_BASE = import.meta.env.VITE_API_URL || (import.meta.env.DEV ? '' : 'http://localhost:8000');
const api = axios.create({ baseURL: API_BASE, timeout: 30000 });
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('satoshi_access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});
export default api;
