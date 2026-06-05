import api, { adminApi } from './client'

// Auth
export const register = (data) => api.post('/auth/register', data)
export const login = (data) => api.post('/auth/login', data)
export const staffLogin = (data) => api.post('/auth/staff/login', data)

// Sources
export const getSources = () => api.get('/api/v1/sources')
export const createSource = (data) => api.post('/api/v1/sources', data)
export const testSource = (id) => api.post(`/api/v1/sources/${id}/test`)
export const discoverSource = (id) => api.post(`/api/v1/sources/${id}/discover`)
export const deleteSource = (id) => api.delete(`/api/v1/sources/${id}`)
export const getConnectorTypes = () => api.get('/api/v1/sources/connector-types')
export const getSchemas = (id) => api.get(`/api/v1/sources/${id}/schemas`)

// Tables
export const getTables = () => api.get('/api/v1/tables')
export const getTable = (id) => api.get(`/api/v1/tables/${id}`)
export const createTable = (data) => api.post('/api/v1/tables', data)
export const updateTable = (id, data) => api.patch(`/api/v1/tables/${id}`, data)
export const deleteTable = (id) => api.delete(`/api/v1/tables/${id}`)
export const runTable = (id) => api.post(`/api/v1/tables/${id}/run`)
export const getProfiles = (id, params) => api.get(`/api/v1/tables/${id}/profiles`, { params })
export const getTableProfiles = getProfiles
export const getProfile = (tableId, profileId) => api.get(`/api/v1/tables/${tableId}/profiles/${profileId}`)
export const getChecks = (id, params) => api.get(`/api/v1/tables/${id}/checks`, { params })
export const getTableCheckResults = getChecks

// Incidents
export const getIncidents = (params) => api.get('/api/v1/incidents', { params })
export const getIncident = (id) => api.get(`/api/v1/incidents/${id}`)
export const acknowledgeIncident = (id) => api.patch(`/api/v1/incidents/${id}/acknowledge`)
export const resolveIncident = (id) => api.patch(`/api/v1/incidents/${id}/resolve`)
export const retryNarration = (id) => api.post(`/api/v1/incidents/${id}/narration/retry`)

// Alerts
export const getAlerts = () => api.get('/api/v1/alerts')
export const createAlert = (data) => api.post('/api/v1/alerts', data)
export const deleteAlert = (id) => api.delete(`/api/v1/alerts/${id}`)
export const testAlert = (id) => api.post(`/api/v1/alerts/${id}/test`)

// Org
export const getOrg = () => api.get('/orgs/me')
export const getOrgHealth = () => api.get('/orgs/me/health')
export const getHealth = () => api.get('/health')

// Reports
export const getWeeklyReport = (days = 7) => api.get(`/api/v1/reports/weekly?window_days=${days}`)
export const getIncidentReport = (id) => api.get(`/api/v1/reports/incident/${id}`)

// AI features
export const recommendMonitors = (sourceId, data) => api.post(`/api/v1/sources/${sourceId}/recommend-monitors`, data)
export const nlRule = (tableId, data) => api.post(`/api/v1/tables/${tableId}/nl-rule`, data)

// ── Admin (staff only) ────────────────────────────────────────────────────────

const ADMIN = '/api/v1/admin'
export const adminGetOrgs = () => adminApi.get(`${ADMIN}/orgs`)
export const adminGetOrg = (id) => adminApi.get(`${ADMIN}/orgs/${id}`)
export const adminUpdatePlan = (id, data) => adminApi.patch(`${ADMIN}/orgs/${id}/plan`, data)
export const adminSetLLMKey = (id, data) => adminApi.put(`${ADMIN}/orgs/${id}/llm-key`, data)
export const adminRemoveLLMKey = (id) => adminApi.delete(`${ADMIN}/orgs/${id}/llm-key`)
export const adminCreateApiKey = (id, data) => adminApi.post(`${ADMIN}/orgs/${id}/api-key`, data)
export const adminGetOrgUsers = (id) => adminApi.get(`${ADMIN}/orgs/${id}/users`)
export const adminGetAllUsers = () => adminApi.get(`${ADMIN}/users`)
export const adminGetStaff = () => adminApi.get(`${ADMIN}/staff`)
export const adminCreateStaff = (data) => adminApi.post(`${ADMIN}/staff`, data)
export const adminDeactivateStaff = (id) => adminApi.patch(`${ADMIN}/staff/${id}/deactivate`)
export const adminGetInvites = (orgId) => adminApi.get(`${ADMIN}/orgs/${orgId}/invites`)
