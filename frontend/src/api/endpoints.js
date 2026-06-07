import api from './client'

// Auth
export const register = (data) => api.post('/auth/register', data)
export const login = (data) => api.post('/auth/login', data)

// Sources
export const getSources = () => api.get('/api/v1/sources')
export const createSource = (data) => api.post('/api/v1/sources', data)
export const testSource = (id) => api.post(`/api/v1/sources/${id}/test`)
export const discoverSource = (id) => api.post(`/api/v1/sources/${id}/discover`)
export const deleteSource = (id) => api.delete(`/api/v1/sources/${id}`)

// Tables
export const getTables = () => api.get('/api/v1/tables')
export const getTable = (id) => api.get(`/api/v1/tables/${id}`)
export const createTable = (data) => api.post('/api/v1/tables', data)
export const updateTable = (id, data) => api.patch(`/api/v1/tables/${id}`, data)
export const deleteTable = (id) => api.delete(`/api/v1/tables/${id}`)
export const runTable = (id) => api.post(`/api/v1/tables/${id}/run`)
export const getProfiles = (id, params) => api.get(`/api/v1/tables/${id}/profiles`, { params })
export const getProfile = (tableId, profileId) => api.get(`/api/v1/tables/${tableId}/profiles/${profileId}`)
export const getChecks = (id, params) => api.get(`/api/v1/tables/${id}/checks`, { params })

// Incidents
export const getIncidents = (params) => api.get('/api/v1/incidents', { params })
export const getIncident = (id) => api.get(`/api/v1/incidents/${id}`)
export const acknowledgeIncident = (id) => api.patch(`/api/v1/incidents/${id}/acknowledge`)
export const resolveIncident = (id) => api.patch(`/api/v1/incidents/${id}/resolve`)

// Alerts
export const getAlerts = () => api.get('/api/v1/alerts')
export const createAlert = (data) => api.post('/api/v1/alerts', data)
export const deleteAlert = (id) => api.delete(`/api/v1/alerts/${id}`)
export const testAlert = (id) => api.post(`/api/v1/alerts/${id}/test`)

// Org
export const getOrg = () => api.get('/orgs/me')
export const getHealth = () => api.get('/health')
export const getOrgMembers = () => api.get('/orgs/me/members')

// ── Teams (for pickers — minimal) ─────────────────────────────────────────────
export const getTeams = (params) => api.get('/api/v1/teams', { params })

// ── Incident assignment ───────────────────────────────────────────────────────
export const assignIncident = (id, body) => api.patch(`/api/v1/incidents/${id}/assign`, body)

// ── Notification preferences ──────────────────────────────────────────────────
export const getNotificationPrefs = () => api.get('/api/v1/me/notification-preferences')
export const updateNotificationPrefs = (body) => api.patch('/api/v1/me/notification-preferences', body)
