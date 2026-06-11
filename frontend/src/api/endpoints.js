import api, { adminApi } from './client'

// Auth
export const register = (data) => api.post('/auth/register', data)
export const login = (data) => api.post('/auth/login', data)
export const staffLogin = (data) => api.post('/auth/staff/login', data)
export const getMe = () => api.get('/auth/me')
export const updateProfile = (data) => api.patch('/auth/profile', data)
export const changePassword = (data) => api.patch('/auth/change-password', data)
export const getInvites = () => api.get('/auth/invites')
export const createInvite = (data) => api.post('/auth/invites', data)
export const revokeInvite = (id) => api.delete(`/auth/invites/${id}`)
export const acceptInvite = (token, data) => api.post(`/auth/invites/${token}/accept`, data)
export const requestPasswordReset = (data) => api.post('/auth/reset-password/request', data)
export const confirmPasswordReset = (data) => api.post('/auth/reset-password/confirm', data)

// Billing
export const getBillingStatus = () => api.get('/api/v1/billing/status')
export const createBillingSubscription = (data) => api.post('/api/v1/billing/create-subscription', data)
export const captureBillingSubscription = (data) => api.post('/api/v1/billing/capture-subscription', data)
export const cancelBillingSubscription = () => api.post('/api/v1/billing/cancel')

// Sources
export const getSources = () => api.get('/api/v1/sources')
export const createSource = (data) => api.post('/api/v1/sources', data)
export const updateSource = (id, data) => api.patch(`/api/v1/sources/${id}`, data)
export const testSource = (id) => api.post(`/api/v1/sources/${id}/test`)
export const testSourceConfig = (data) => api.post('/api/v1/sources/test-connection', data)
export const discoverSource = (id) => api.post(`/api/v1/sources/${id}/discover`)
export const deleteSource = (id) => api.delete(`/api/v1/sources/${id}`)
export const getConnectorTypes = () => api.get('/api/v1/sources/connector-types')
export const getSchemas = (id) => api.get(`/api/v1/sources/${id}/schemas`)
export const getSourceTableSchema = (id, params) => api.get(`/api/v1/sources/${id}/table-schema`, { params })
export const getOrgMembers = () => api.get('/orgs/me/members')

// Tables
export const getTables = () => api.get('/api/v1/tables')
export const getTable = (id) => api.get(`/api/v1/tables/${id}`)
export const createTable = (data) => api.post('/api/v1/tables', data)
export const updateTable = (id, data) => api.patch(`/api/v1/tables/${id}`, data)
export const deleteTable = (id) => api.delete(`/api/v1/tables/${id}`)
export const runTable = (id) => api.post(`/api/v1/tables/${id}/run`)
export const triggerProfile = (id) => api.post(`/api/v1/tables/${id}/profile`)
export const getProfiles = (id, params) => api.get(`/api/v1/tables/${id}/profiles`, { params })
export const getTableProfiles = getProfiles
export const getProfile = (tableId, profileId) => api.get(`/api/v1/tables/${tableId}/profiles/${profileId}`)
export const getChecks = (id, params) => api.get(`/api/v1/tables/${id}/checks`, { params })
export const getTableCheckResults = getChecks
export const getCheckHistory = (id, limit = 50) => api.get(`/api/v1/tables/${id}/check-history?limit=${limit}`)
export const runCustomCheck = (id, data) => api.post(`/api/v1/tables/${id}/custom-check`, data, { timeout: 120000 })

// Incidents
export const getIncidents = (params) => api.get('/api/v1/incidents', { params })
export const getIncident = (id) => api.get(`/api/v1/incidents/${id}`)
export const acknowledgeIncident = (id) => api.patch(`/api/v1/incidents/${id}/acknowledge`)
export const investigateIncident = (id) => api.patch(`/api/v1/incidents/${id}/investigate`)
export const resolveIncident = (id) => api.patch(`/api/v1/incidents/${id}/resolve`)
export const muteIncident = (id, data) => api.patch(`/api/v1/incidents/${id}/mute`, data)
export const markFalsePositive = (id) => api.patch(`/api/v1/incidents/${id}/false-positive`)
export const getIncidentStats = () => api.get('/api/v1/incidents/stats')
export const retryNarration = (id) => api.post(`/api/v1/incidents/${id}/narration/retry`)

// Alerts
export const getAlerts = () => api.get('/api/v1/alerts')
export const getAlertChannels = () => api.get('/api/v1/alerts/channels')
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
export const generateWeeklySummary = () => api.post('/api/v1/reports/weekly/ai-summary')

// AI features
export const recommendMonitors = (sourceId, data) => api.post(`/api/v1/sources/${sourceId}/recommend-monitors`, data, { timeout: 180000 })
export const nlRule = (tableId, data) => api.post(`/api/v1/tables/${tableId}/nl-rule`, data, { timeout: 180000 })

// Custom Monitors
export const getAllCustomMonitors = () => api.get('/api/v1/custom-monitors')
export const getCustomMonitors = (tableId) => api.get(`/api/v1/tables/${tableId}/custom-monitors`)
export const createCustomMonitor = (tableId, data) => api.post(`/api/v1/tables/${tableId}/custom-monitors`, data)
export const updateCustomMonitor = (tableId, monitorId, data) => api.patch(`/api/v1/tables/${tableId}/custom-monitors/${monitorId}`, data)
export const deleteCustomMonitor = (tableId, monitorId) => api.delete(`/api/v1/tables/${tableId}/custom-monitors/${monitorId}`)
export const runCustomMonitorNow = (tableId, monitorId) => api.post(`/api/v1/tables/${tableId}/custom-monitors/${monitorId}/run`, null, { timeout: 120000 })
export const retryAutopilot = (tableId) => api.post(`/api/v1/tables/${tableId}/retry-autopilot`)

// ── Admin (staff only) ────────────────────────────────────────────────────────

const ADMIN = '/api/v1/admin'
export const adminGetStats = () => adminApi.get(`${ADMIN}/stats`)
export const adminGetOrgs = (params) => adminApi.get(`${ADMIN}/orgs`, { params })
export const adminGetOrg = (id) => adminApi.get(`${ADMIN}/orgs/${id}`)
export const adminDeleteOrg = (id) => adminApi.delete(`${ADMIN}/orgs/${id}`)
export const adminSuspendOrg = (id) => adminApi.patch(`${ADMIN}/orgs/${id}/suspend`)
export const adminUnsuspendOrg = (id) => adminApi.patch(`${ADMIN}/orgs/${id}/unsuspend`)
export const adminUpdatePlan = (id, data) => adminApi.patch(`${ADMIN}/orgs/${id}/plan`, data)
export const adminSetLLMKey = (id, data) => adminApi.put(`${ADMIN}/orgs/${id}/llm-key`, data)
export const adminRemoveLLMKey = (id) => adminApi.delete(`${ADMIN}/orgs/${id}/llm-key`)
export const adminCreateApiKey = (id, data) => adminApi.post(`${ADMIN}/orgs/${id}/api-key`, data)
export const adminGetOrgUsage = (id, params) => adminApi.get(`${ADMIN}/orgs/${id}/usage`, { params })
export const adminGetOrgSources = (id) => adminApi.get(`${ADMIN}/orgs/${id}/sources`)
export const adminCancelOrgSubscription = (id, data) => adminApi.post(`${ADMIN}/orgs/${id}/subscription/cancel`, data)
export const adminGetOrgUsers = (id) => adminApi.get(`${ADMIN}/orgs/${id}/users`)
export const adminGetAllUsers = (params) => adminApi.get(`${ADMIN}/users`, { params })
export const adminDeactivateUser = (id) => adminApi.patch(`${ADMIN}/users/${id}/deactivate`)
export const adminReactivateUser = (id) => adminApi.patch(`${ADMIN}/users/${id}/reactivate`)
export const adminChangeUserRole = (id, data) => adminApi.patch(`${ADMIN}/users/${id}/role`, data)
export const adminDeactivateOrgUser = (orgId, userId) => adminApi.patch(`${ADMIN}/orgs/${orgId}/users/${userId}/deactivate`)
export const adminReactivateOrgUser = (orgId, userId) => adminApi.patch(`${ADMIN}/orgs/${orgId}/users/${userId}/reactivate`)
export const adminGetStaff = () => adminApi.get(`${ADMIN}/staff`)
export const adminCreateStaff = (data) => adminApi.post(`${ADMIN}/staff`, data)
export const adminDeactivateStaff = (id) => adminApi.patch(`${ADMIN}/staff/${id}/deactivate`)
export const adminResetStaffPassword = (id) => adminApi.post(`${ADMIN}/staff/${id}/reset-password`)
export const adminGetInvites = (orgId) => adminApi.get(`${ADMIN}/orgs/${orgId}/invites`)

// ── Teams ──────────────────────────────────────────────────────────────────
export const getTeams = () => api.get('/api/v1/teams')
export const createTeam = (body) => api.post('/api/v1/teams', body)
export const updateTeam = (id, body) => api.patch(`/api/v1/teams/${id}`, body)
export const deleteTeam = (id) => api.delete(`/api/v1/teams/${id}`)
export const getTeam = (id) => api.get(`/api/v1/teams/${id}`)
export const getTeamMembers = (id) => api.get(`/api/v1/teams/${id}/members`)
export const addTeamMember = (id, body) => api.post(`/api/v1/teams/${id}/members`, body)
export const removeTeamMember = (teamId, userId) => api.delete(`/api/v1/teams/${teamId}/members/${userId}`)
export const updateTeamMemberRole = (teamId, userId, body) => api.patch(`/api/v1/teams/${teamId}/members/${userId}`, body)

// ── On-call ─────────────────────────────────────────────────────────────────
export const getOncall = (teamId) => api.get(`/api/v1/teams/${teamId}/oncall`)
export const getCurrentOncall = (teamId) => api.get(`/api/v1/teams/${teamId}/oncall/current`)
export const addOncallSlot = (teamId, body) => api.post(`/api/v1/teams/${teamId}/oncall`, body)
export const deleteOncallSlot = (teamId, slotId) => api.delete(`/api/v1/teams/${teamId}/oncall/${slotId}`)

// ── Notification preferences ─────────────────────────────────────────────────
export const getNotificationPrefs = () => api.get('/api/v1/me/notification-preferences')
export const updateNotificationPrefs = (body) => api.patch('/api/v1/me/notification-preferences', body)

// ── Notification preferences + Assignment ────────────────────────────────────
export const assignIncident = (id, body) => api.patch(`/api/v1/incidents/${id}/assign`, body)
