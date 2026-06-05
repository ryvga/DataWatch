const memory = new Map()

function getLocalStorage() {
  try {
    if (typeof window !== 'undefined' && window.localStorage) return window.localStorage
  } catch (_) {}
  return null
}

export const storage = {
  getItem(key) {
    const local = getLocalStorage()
    return local ? local.getItem(key) : memory.get(key) || null
  },
  setItem(key, value) {
    const local = getLocalStorage()
    if (local) local.setItem(key, value)
    else memory.set(key, value)
  },
  removeItem(key) {
    const local = getLocalStorage()
    if (local) local.removeItem(key)
    memory.delete(key)
  },
}

export function setSessionExpiry(days) {
  const expiry = Date.now() + days * 24 * 60 * 60 * 1000
  storage.setItem('dw_session_expiry', String(expiry))
}

export function clearSession() {
  storage.removeItem('dw_token')
  storage.removeItem('dw_session_expiry')
  storage.removeItem('dw_workspace')
  storage.removeItem('dw_org_name')
  storage.removeItem('dw_user_role')
}

export function getWorkspace() {
  return storage.getItem('dw_workspace')
}

export function setWorkspaceSession({ token, org_slug, org_name, user_role, remember = false }) {
  storage.setItem('dw_token', token)
  storage.setItem('dw_workspace', org_slug)
  if (org_name) storage.setItem('dw_org_name', org_name)
  if (user_role) storage.setItem('dw_user_role', user_role)
  setSessionExpiry(remember ? 7 : 1)
}

export function isSessionValid() {
  const expiry = storage.getItem('dw_session_expiry')
  if (!expiry) {
    // No expiry set: if creds exist, set a 1-day default so old sessions keep working today
    const hasToken = !!(storage.getItem('dw_token') || storage.getItem('dw_api_key'))
    if (hasToken) {
      setSessionExpiry(1)
      return true
    }
    return false
  }
  if (Date.now() > Number(expiry)) {
    clearSession()
    return false
  }
  return true
}
