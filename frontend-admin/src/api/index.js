import axios from 'axios';

const api = axios.create({
  baseURL: '/api/v1',
  // 默认超时时间 120 秒，避免长耗时任务（知识导入、图谱构建等）前端过早报错
  timeout: 120000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    // 添加 token
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    console.error('API Error:', error);
    // 如果 token 过期或无效，清除本地存储并跳转到登录页
    // 但排除登录接口本身，让登录页可以显示错误信息
    if (error.response?.status === 401 && !error.config?.url?.includes('/auth/login')) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      // 如果不在登录页，才跳转
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export default api;

