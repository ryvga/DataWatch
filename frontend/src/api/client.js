import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  timeout: 15000,
})

// Inject API key or Bearer token
api.interceptors.request.use((config) => {
  const apiKey = localStorage.getItem('dw_api_key')
  const token = localStorage.getItem('dw_token')
  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`
  } else if (apiKey) {
    config.headers['x-api-key'] = apiKey
  }
  return config
})

// Global error handling
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('dw_token')
      localStorage.removeItem('dw_api_key')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api
