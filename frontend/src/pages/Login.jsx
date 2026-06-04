import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { login, register } from '../api/endpoints'

export default function Login() {
  const nav = useNavigate()
  const [mode, setMode] = useState('login') // 'login' | 'register'
  const [form, setForm] = useState({ email: '', password: '', org_name: '', org_slug: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const set = (k) => (e) => setForm((p) => ({ ...p, [k]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (mode === 'login') {
        const r = await login({ email: form.email, password: form.password })
        localStorage.setItem('dw_token', r.data.access_token)
      } else {
        const r = await register({
          email: form.email,
          password: form.password,
          org_name: form.org_name,
          org_slug: form.org_slug,
        })
        localStorage.setItem('dw_api_key', r.data.api_key)
        // Also login to get a JWT for the session
        const lr = await login({ email: form.email, password: form.password })
        localStorage.setItem('dw_token', lr.data.access_token)
      }
      nav('/')
    } catch (err) {
      setError(err.response?.data?.detail || 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <span className="text-3xl">🔭</span>
          <h1 className="text-2xl font-bold text-white mt-2">DataWatch</h1>
          <p className="text-sm text-gray-500 mt-1">Data quality monitoring</p>
        </div>

        <div className="card space-y-5">
          {/* Mode toggle */}
          <div className="flex rounded-lg overflow-hidden border border-gray-700">
            {['login', 'register'].map((m) => (
              <button
                key={m}
                onClick={() => { setMode(m); setError('') }}
                className={`flex-1 py-2 text-sm font-medium transition-colors capitalize ${
                  mode === m ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-gray-200'
                }`}
              >
                {m === 'login' ? 'Sign In' : 'Register'}
              </button>
            ))}
          </div>

          <form onSubmit={submit} className="space-y-4">
            {mode === 'register' && (
              <>
                <div>
                  <label className="label">Organisation Name</label>
                  <input className="input" value={form.org_name} onChange={set('org_name')} placeholder="Acme Corp" required />
                </div>
                <div>
                  <label className="label">Organisation Slug</label>
                  <input className="input" value={form.org_slug} onChange={set('org_slug')} placeholder="acme" pattern="[a-z0-9-]+" required />
                  <p className="text-xs text-gray-600 mt-1">lowercase letters, numbers, hyphens</p>
                </div>
              </>
            )}
            <div>
              <label className="label">Email</label>
              <input className="input" type="email" value={form.email} onChange={set('email')} placeholder="you@company.com" required />
            </div>
            <div>
              <label className="label">Password</label>
              <input className="input" type="password" value={form.password} onChange={set('password')} placeholder="••••••••" required />
            </div>

            {error && (
              <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2 text-sm text-red-400">
                {error}
              </div>
            )}

            <button type="submit" disabled={loading} className="btn-primary w-full justify-center">
              {loading ? 'Loading…' : mode === 'login' ? 'Sign In' : 'Create Account'}
            </button>
          </form>
        </div>

        {/* API key shortcut */}
        <div className="mt-4 card text-xs text-gray-500 space-y-1">
          <p className="font-medium text-gray-400">Have an API key?</p>
          <p>Paste it below to skip login:</p>
          <input
            className="input text-xs"
            placeholder="dw_..."
            onBlur={(e) => {
              const v = e.target.value.trim()
              if (v.startsWith('dw_')) { localStorage.setItem('dw_api_key', v); nav('/') }
            }}
          />
        </div>
      </div>
    </div>
  )
}
