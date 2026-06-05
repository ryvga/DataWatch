import axios from 'axios'
import { storage, clearSession } from '@/lib/storage'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  timeout: 15000,
})

// Inject Bearer JWT on every request (JWT-only auth — no more API key fallback for users)
api.interceptors.request.use((config) => {
  const token = storage.getItem('dw_token')
  if (token) config.headers['Authorization'] = `Bearer ${token}`
  return config
})

// On 401 clear session and redirect to login
api.interceptors.response.use(
  (res) => res,
  async (err) => {
    if (err.response?.status === 401 && !err.config._retry) {
      err.config._retry = true
      clearSession()
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

// Separate admin API client using staff JWT
export const adminApi = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  timeout: 15000,
})

adminApi.interceptors.request.use((config) => {
  const token = storage.getItem('dw_staff_token')
  if (token) config.headers['Authorization'] = `Bearer ${token}`
  return config
})

adminApi.interceptors.response.use(
  (res) => res,
  async (err) => {
    if (err.response?.status === 401 && !err.config._retry) {
      err.config._retry = true
      storage.removeItem('dw_staff_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api
