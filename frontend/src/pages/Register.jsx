import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { register } from '../api/endpoints'

const BASE_DOMAIN = import.meta.env.VITE_BASE_DOMAIN || 'panopta.app'

function workspaceUrl(slug) {
  const hostname = window.location.hostname
  const port = window.location.port ? `:${window.location.port}` : ''
  const protocol = window.location.protocol
  const isLocalhost = hostname === 'localhost' || hostname === '127.0.0.1'
  if (isLocalhost) return `${protocol}//${slug}.localhost${port}`
  return `${protocol}//${slug}.${BASE_DOMAIN}`
}

function slugify(name) {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
}

export default function Register() {
  const [form, setForm] = useState({
    org_name: '',
    org_slug: '',
    full_name: '',
    email: '',
    password: '',
    confirm_password: '',
  })
  const [slugManuallyEdited, setSlugManuallyEdited] = useState(false)
  const [errors, setErrors] = useState({})
  const [globalError, setGlobalError] = useState(null) // { type: 'slug_taken'|'email_taken'|'generic', message }
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)

  // Auto-derive slug from org name unless the user manually edited it
  useEffect(() => {
    if (!slugManuallyEdited && form.org_name) {
      setForm((f) => ({ ...f, org_slug: slugify(form.org_name) }))
    }
  }, [form.org_name, slugManuallyEdited])

  const set = (key) => (e) => {
    setForm((f) => ({ ...f, [key]: e.target.value }))
    if (errors[key]) setErrors((prev) => { const next = { ...prev }; delete next[key]; return next })
    if (globalError) setGlobalError(null)
  }

  const onSlugChange = (e) => {
    setSlugManuallyEdited(true)
    setForm((f) => ({ ...f, org_slug: e.target.value }))
    if (errors.org_slug) setErrors((prev) => { const next = { ...prev }; delete next.org_slug; return next })
    if (globalError) setGlobalError(null)
  }

  function validate() {
    const errs = {}
    if (!form.org_name.trim()) errs.org_name = 'Organisation name is required.'
    if (!form.org_slug.trim()) {
      errs.org_slug = 'Workspace URL is required.'
    } else if (!/^[a-z0-9-]+$/.test(form.org_slug)) {
      errs.org_slug = 'Only lowercase letters, numbers, and hyphens are allowed.'
    } else if (form.org_slug.length < 3) {
      errs.org_slug = 'Workspace URL must be at least 3 characters.'
    }
    if (!form.full_name.trim()) errs.full_name = 'Full name is required.'
    if (!form.email.trim()) errs.email = 'Email address is required.'
    if (!form.password) {
      errs.password = 'Password is required.'
    } else if (form.password.length < 8) {
      errs.password = 'Password must be at least 8 characters.'
    }
    if (!form.confirm_password) {
      errs.confirm_password = 'Please confirm your password.'
    } else if (form.password !== form.confirm_password) {
      errs.confirm_password = 'Passwords do not match.'
    }
    return errs
  }

  const submit = async (e) => {
    e.preventDefault()
    setGlobalError(null)

    const errs = validate()
    if (Object.keys(errs).length > 0) {
      setErrors(errs)
      return
    }

    setLoading(true)
    try {
      await register({
        org_name: form.org_name.trim(),
        org_slug: form.org_slug.trim().toLowerCase(),
        full_name: form.full_name.trim(),
        email: form.email.trim(),
        password: form.password,
      })
      setSuccess(true)
      setTimeout(() => {
        window.location.href = workspaceUrl(form.org_slug.trim().toLowerCase()) + '?registered=1'
      }, 800)
    } catch (err) {
      const detail = err.response?.data?.detail || ''
      if (err.response?.status === 409) {
        if (detail.toLowerCase().includes('slug') || detail.toLowerCase().includes('workspace')) {
          setGlobalError({ type: 'slug_taken', message: detail })
        } else if (detail.toLowerCase().includes('email')) {
          setGlobalError({ type: 'email_taken', message: detail })
        } else {
          setGlobalError({ type: 'generic', message: detail || 'Registration failed. Please try again.' })
        }
      } else {
        setGlobalError({ type: 'generic', message: detail || 'Registration failed. Please try again.' })
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-start justify-center py-10 px-4">
      <div className="w-full max-w-5xl overflow-hidden rounded-xl border border-gray-800 bg-gray-900 shadow-2xl lg:grid lg:grid-cols-[1fr_440px]">

        {/* Left panel */}
        <div className="hidden lg:flex flex-col justify-between border-r border-gray-800 bg-gradient-to-br from-blue-950/40 via-gray-900 to-gray-900 p-10">
          <div>
            <div className="mb-2 text-2xl">🔭</div>
            <h1 className="text-3xl font-bold text-white leading-tight">
              Catch data quality issues before your users do.
            </h1>
            <p className="mt-4 text-sm leading-relaxed text-gray-400">
              Connect a database, pick tables to watch, and Panopta handles the rest — statistical anomaly detection, AI-generated incident reports, and instant alerts.
            </p>
          </div>
          <div className="space-y-3">
            {[
              { step: '1', label: 'Connect your warehouse', desc: 'PostgreSQL, MySQL, BigQuery, Snowflake, and 9 more connectors.' },
              { step: '2', label: 'Set tables to monitor', desc: 'Choose schemas, set check intervals, configure sensitivity.' },
              { step: '3', label: 'Get incident reports', desc: 'AI-written explanations with root cause and recommended actions.' },
            ].map((item) => (
              <div key={item.step} className="flex items-start gap-3 rounded-lg border border-gray-700 bg-gray-800/50 p-3">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-600/20 text-xs font-bold text-blue-400">
                  {item.step}
                </div>
                <div>
                  <div className="text-xs font-semibold text-gray-200">{item.label}</div>
                  <div className="mt-0.5 text-xs text-gray-500">{item.desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right panel — registration form */}
        <div className="p-8">
          <div className="mb-6 text-center lg:text-left">
            <span className="text-2xl">🔭</span>
            <h2 className="mt-2 text-xl font-bold text-white">Create your workspace</h2>
            <p className="mt-1 text-sm text-gray-400">Set up a new Panopta organisation for your team.</p>
          </div>

          {success ? (
            <div className="flex flex-col items-center gap-4 py-12 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-full bg-green-500/10 text-3xl">
                ✅
              </div>
              <div>
                <p className="font-semibold text-white">Workspace created!</p>
                <p className="mt-1 text-sm text-gray-400">Taking you to your workspace…</p>
              </div>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4">

              {/* Organisation name */}
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-400">Organisation name</label>
                <input
                  className={`w-full rounded-lg border bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-600 outline-none transition-colors focus:ring-1 focus:ring-blue-500 ${errors.org_name ? 'border-red-500' : 'border-gray-700'}`}
                  value={form.org_name}
                  onChange={set('org_name')}
                  placeholder="Acme Corp"
                  autoFocus
                />
                {errors.org_name && <p className="mt-1 text-xs text-red-400">{errors.org_name}</p>}
              </div>

              {/* Workspace URL */}
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-400">Workspace URL</label>
                <div className={`flex items-center rounded-lg border bg-gray-800 px-3 py-2 text-sm transition-colors focus-within:ring-1 focus-within:ring-blue-500 ${errors.org_slug ? 'border-red-500' : 'border-gray-700'}`}>
                  <span className="shrink-0 select-none text-gray-500">app.panopta.app/</span>
                  <input
                    className="min-w-0 flex-1 bg-transparent font-mono text-white outline-none ml-1 placeholder-gray-600"
                    placeholder="acme-corp"
                    value={form.org_slug}
                    onChange={onSlugChange}
                    pattern="[a-z0-9-]+"
                    minLength={3}
                  />
                </div>
                {errors.org_slug ? (
                  <p className="mt-1 text-xs text-red-400">{errors.org_slug}</p>
                ) : form.org_slug ? (
                  <p className="mt-1 text-xs text-gray-500">
                    Your workspace:{' '}
                    <span className="font-mono text-gray-300">{form.org_slug}.panopta.app</span>
                  </p>
                ) : null}
              </div>

              {/* Full name */}
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-400">Full name</label>
                <input
                  className={`w-full rounded-lg border bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-600 outline-none transition-colors focus:ring-1 focus:ring-blue-500 ${errors.full_name ? 'border-red-500' : 'border-gray-700'}`}
                  value={form.full_name}
                  onChange={set('full_name')}
                  placeholder="Jane Doe"
                />
                {errors.full_name && <p className="mt-1 text-xs text-red-400">{errors.full_name}</p>}
              </div>

              {/* Email */}
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-400">Email address</label>
                <input
                  className={`w-full rounded-lg border bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-600 outline-none transition-colors focus:ring-1 focus:ring-blue-500 ${errors.email ? 'border-red-500' : 'border-gray-700'}`}
                  type="email"
                  value={form.email}
                  onChange={set('email')}
                  placeholder="you@company.com"
                />
                {errors.email && <p className="mt-1 text-xs text-red-400">{errors.email}</p>}
              </div>

              {/* Password row */}
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-400">Password</label>
                  <input
                    className={`w-full rounded-lg border bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-600 outline-none transition-colors focus:ring-1 focus:ring-blue-500 ${errors.password ? 'border-red-500' : 'border-gray-700'}`}
                    type="password"
                    value={form.password}
                    onChange={set('password')}
                    placeholder="Min. 8 characters"
                  />
                  {errors.password && <p className="mt-1 text-xs text-red-400">{errors.password}</p>}
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-400">Confirm password</label>
                  <input
                    className={`w-full rounded-lg border bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-600 outline-none transition-colors focus:ring-1 focus:ring-blue-500 ${errors.confirm_password ? 'border-red-500' : 'border-gray-700'}`}
                    type="password"
                    value={form.confirm_password}
                    onChange={set('confirm_password')}
                    placeholder="Repeat password"
                  />
                  {errors.confirm_password && <p className="mt-1 text-xs text-red-400">{errors.confirm_password}</p>}
                </div>
              </div>

              {/* Global error messages */}
              {globalError?.type === 'slug_taken' && (
                <div className="flex gap-3 rounded-lg border border-blue-700 bg-blue-950/50 p-3 text-sm text-blue-200">
                  <span className="shrink-0">ℹ️</span>
                  <div>
                    <span className="font-semibold">This workspace name is already taken.</span>{' '}
                    If your team already uses Panopta, ask your admin to invite you via{' '}
                    <span className="font-mono text-xs">Settings → Team</span>.
                  </div>
                </div>
              )}

              {globalError?.type === 'email_taken' && (
                <div className="rounded-lg border border-red-700 bg-red-950/40 px-3 py-2 text-sm text-red-300">
                  An account with this email already exists.{' '}
                  <span className="font-medium">Sign in to your existing workspace.</span>
                </div>
              )}

              {globalError?.type === 'generic' && (
                <div className="rounded-lg border border-red-700 bg-red-950/40 px-3 py-2 text-sm text-red-300">
                  {globalError.message}
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? 'Creating workspace…' : 'Create workspace'}
              </button>

              <p className="text-center text-xs text-gray-500">
                Already have a workspace?{' '}
                <Link to="/" className="text-blue-400 underline underline-offset-4 hover:text-blue-300">
                  Sign in
                </Link>
              </p>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
