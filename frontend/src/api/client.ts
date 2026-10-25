import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

export const DEMO_TOKEN_KEY = 'smart_freeze_token';

export const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 120000,
});

// Never choose an identity implicitly. A token is attached only after an explicit
// local-demo session is created or a real identity flow supplies one.
apiClient.interceptors.request.use((config) => {
  const token = window.localStorage.getItem(DEMO_TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  } else if (config.headers.Authorization) {
    delete config.headers.Authorization;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail = error.response?.data?.detail;
    if (error.response?.status === 401) {
      window.localStorage.removeItem(DEMO_TOKEN_KEY);
      window.dispatchEvent(new CustomEvent('auth-expired'));
      error.message = detail || 'Authentication credentials expired or invalid. Please renew session.';
    } else if (error.response?.status === 403) {
      error.message = detail || 'Access denied for this case or operation.';
    } else if (detail) {
      error.message = detail;
    } else if (!error.response) {
      error.message = 'Cannot reach the API. Check that FastAPI is running and VITE_API_BASE_URL is correct.';
    }
    // Preserve response/status fields for callers that need to distinguish HTTP states.
    return Promise.reject(error);
  }
);
