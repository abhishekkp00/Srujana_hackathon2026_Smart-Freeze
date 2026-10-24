import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

export const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 15000,
});

// Attach authenticated session token or active development demonstration persona
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('smart_freeze_token') || 'dev_token_admin';
  if (token && token !== 'unauthenticated') {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    let message = 'An unexpected error occurred';
    if (error.response?.status === 401) {
      message = 'Authentication Required (HTTP 401): Please select an authorized persona.';
    } else if (error.response?.status === 403) {
      message = `Access Denied (HTTP 403): ${error.response.data?.detail || 'Unauthorized for this case or operation.'}`;
    } else if (error.response?.data?.detail) {
      message = error.response.data.detail;
    } else if (error.message) {
      message = error.message;
    }
    return Promise.reject(new Error(message));
  }
);
