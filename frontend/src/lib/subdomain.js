/**
 * Subdomain routing helpers.
 *
 * In production:
 *   datawatch.io          → landing
 *   admin.datawatch.io    → admin portal
 *   acme.datawatch.io     → workspace "acme"
 *
 * In development (localhost):
 *   We can't use real subdomains easily, so we fall back to stored workspace slug.
 *   app.localhost or any *.localhost also works if you configure /etc/hosts.
 */

const BASE_DOMAIN = import.meta.env.VITE_BASE_DOMAIN || 'datawatch.io'
const ADMIN_SUBDOMAIN = import.meta.env.VITE_ADMIN_SUBDOMAIN || 'admin'

export function getHostContext() {
  const hostname = window.location.hostname

  // Local dev
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return { type: 'dev', workspace: null }
  }

  // Exact base domain (no subdomain)
  if (hostname === BASE_DOMAIN || hostname === `www.${BASE_DOMAIN}`) {
    return { type: 'landing', workspace: null }
  }

  // Extract subdomain
  if (hostname.endsWith(`.${BASE_DOMAIN}`)) {
    const sub = hostname.slice(0, -(BASE_DOMAIN.length + 1))
    if (sub === ADMIN_SUBDOMAIN) return { type: 'admin', workspace: null }
    return { type: 'workspace', workspace: sub }
  }

  return { type: 'dev', workspace: null }
}

export function isAdminContext() {
  return getHostContext().type === 'admin'
}

export function isLandingContext() {
  return getHostContext().type === 'landing'
}

export function getWorkspaceFromHost() {
  const ctx = getHostContext()
  return ctx.workspace || null
}
