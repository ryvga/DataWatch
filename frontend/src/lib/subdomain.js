/**
 * Subdomain-based context routing — works the same in dev and prod.
 *
 * Dev:  localhost:5173           → landing
 *       acme.localhost:5173      → workspace "acme"
 *       {ADMIN_SUB}.localhost    → admin portal (subdomain value kept in env, not hardcoded)
 *
 * Prod: datawatch.io             → landing
 *       acme.datawatch.io        → workspace "acme"
 *       {ADMIN_SUB}.datawatch.io → admin portal
 *
 * The admin subdomain is ONLY known from the env var — never exposed in code
 * so it cannot be guessed by scanning the JS bundle.
 */

const BASE_DOMAIN = import.meta.env.VITE_BASE_DOMAIN || 'datawatch.io'
const ADMIN_SUBDOMAIN = import.meta.env.VITE_ADMIN_SUBDOMAIN  // undefined by default — must be set explicitly

export const DEV_MODE = import.meta.env.DEV === true

function isLocalhost(hostname) {
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '[::1]'
}

export function getHostContext() {
  const hostname = window.location.hostname

  // ── Exact root domains → landing ─────────────────────────────────────────
  if (isLocalhost(hostname) || hostname === BASE_DOMAIN || hostname === `www.${BASE_DOMAIN}`) {
    return { type: 'landing', workspace: null }
  }

  // ── Subdomains of localhost (dev) ─────────────────────────────────────────
  if (hostname.endsWith('.localhost')) {
    const sub = hostname.slice(0, -'.localhost'.length)
    if (ADMIN_SUBDOMAIN && sub === ADMIN_SUBDOMAIN) {
      return { type: 'admin', workspace: null }
    }
    return { type: 'workspace', workspace: sub }
  }

  // ── Subdomains of BASE_DOMAIN (prod) ──────────────────────────────────────
  if (hostname.endsWith(`.${BASE_DOMAIN}`)) {
    const sub = hostname.slice(0, -(BASE_DOMAIN.length + 1))
    if (ADMIN_SUBDOMAIN && sub === ADMIN_SUBDOMAIN) {
      return { type: 'admin', workspace: null }
    }
    return { type: 'workspace', workspace: sub }
  }

  // Fallback
  return { type: 'landing', workspace: null }
}

export function getWorkspaceFromHost() {
  const ctx = getHostContext()
  return ctx.workspace || null
}

/** Build the URL to navigate a user to their workspace */
export function workspaceUrl(slug) {
  const hostname = window.location.hostname
  const port = window.location.port ? `:${window.location.port}` : ''
  const protocol = window.location.protocol

  if (isLocalhost(hostname)) {
    return `${protocol}//${slug}.localhost${port}`
  }
  return `${protocol}//${slug}.${BASE_DOMAIN}`
}
