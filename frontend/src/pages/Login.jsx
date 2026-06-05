import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertCircle, Activity, Loader2 } from 'lucide-react'
import { login, register } from '../api/endpoints'
import { BrandMark, ThemeToggle } from '../components/app-ui'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { setWorkspaceSession, isSessionValid } from '@/lib/storage'
import { getWorkspaceFromHost } from '@/lib/subdomain'

export default function Login() {
  const nav = useNavigate()
  const [mode, setMode] = useState('login')
  const [form, setForm] = useState({ email: '', password: '', org_name: '', org_slug: '', full_name: '' })
  const [remember, setRemember] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  // Pre-fill workspace from subdomain if available
  useEffect(() => {
    if (isSessionValid()) { nav('/'); return }
    const ws = getWorkspaceFromHost()
    if (ws) setForm((f) => ({ ...f, org_slug: ws }))
  }, [])

  const set = (key) => (e) => setForm((p) => ({ ...p, [key]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    if (!form.org_slug.trim()) { setError('Workspace is required'); return }
    setLoading(true)
    try {
      if (mode === 'login') {
        const res = await login({ email: form.email, password: form.password, org_slug: form.org_slug.trim().toLowerCase() })
        setWorkspaceSession({
          token: res.data.access_token,
          org_slug: res.data.org_slug,
          org_name: res.data.org_name,
          user_role: res.data.user_role,
          remember,
        })
      } else {
        await register({
          email: form.email,
          password: form.password,
          org_name: form.org_name,
          org_slug: form.org_slug.trim().toLowerCase(),
          full_name: form.full_name || undefined,
        })
        const res = await login({ email: form.email, password: form.password, org_slug: form.org_slug.trim().toLowerCase() })
        setWorkspaceSession({
          token: res.data.access_token,
          org_slug: res.data.org_slug,
          org_name: res.data.org_name,
          user_role: res.data.user_role,
          remember,
        })
      }
      nav('/')
    } catch (err) {
      setError(err.response?.data?.detail || 'Authentication failed')
    } finally {
      setLoading(false)
    }
  }

  const workspaceLocked = !!getWorkspaceFromHost()

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col px-4 py-4">
        <header className="flex items-center justify-between">
          <BrandMark />
          <ThemeToggle />
        </header>

        <main className="grid flex-1 place-items-center py-8">
          <div className="grid w-full max-w-5xl overflow-hidden rounded-xl border bg-card shadow-lg lg:grid-cols-[minmax(0,1fr)_minmax(390px,440px)]">

            {/* Left panel */}
            <section className="relative hidden overflow-hidden border-r lg:flex lg:flex-col lg:justify-between bg-gradient-to-br from-primary/8 via-background to-primary/4 p-8">
              <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,hsl(var(--primary)/0.12),transparent_60%)]" />
              <div className="relative max-w-md">
                <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/8 px-3 py-1.5 text-xs font-semibold text-primary">
                  <Activity className="size-3" />
                  Data Quality Platform
                </div>
                <h1 className="text-3xl font-bold tracking-tight leading-tight">
                  Monitor warehouse quality before incidents reach users.
                </h1>
                <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
                  DataWatch tracks table profiles, detects anomalies with statistical methods, and turns high-priority incidents into AI-generated operator reports.
                </p>
              </div>
              <div className="relative grid max-w-md grid-cols-3 gap-2">
                {[
                  { label: 'Profiles', desc: 'row, freshness, schema' },
                  { label: 'Detection', desc: 'z-score, IsoForest, STL' },
                  { label: 'Incidents', desc: 'AI narration' },
                ].map((item) => (
                  <div key={item.label} className="rounded-lg border bg-card/80 p-3 backdrop-blur">
                    <div className="text-xs font-semibold text-foreground">{item.label}</div>
                    <div className="mt-1 text-xs text-muted-foreground">{item.desc}</div>
                  </div>
                ))}
              </div>
            </section>

            {/* Right panel */}
            <Card className="rounded-none border-0 shadow-none">
              <CardHeader className="pb-4">
                <CardTitle className="text-xl font-bold">
                  {mode === 'login' ? 'Welcome back' : 'Create workspace'}
                </CardTitle>
                <CardDescription>
                  {mode === 'login'
                    ? 'Sign in to your workspace to continue.'
                    : 'Register a new organisation and open your workspace.'}
                </CardDescription>
              </CardHeader>

              <CardContent className="flex flex-col gap-5">
                <Tabs value={mode} onValueChange={(v) => { setMode(v); setError('') }}>
                  <TabsList className="grid w-full grid-cols-2">
                    <TabsTrigger value="login">Sign in</TabsTrigger>
                    <TabsTrigger value="register">Register</TabsTrigger>
                  </TabsList>
                </Tabs>

                <form onSubmit={submit} className="flex flex-col gap-4">
                  {/* Workspace slug — always shown */}
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="workspace">Workspace</Label>
                    <div className="flex items-center rounded-md border bg-muted/40 px-3 py-2 text-sm">
                      <span className="text-muted-foreground select-none">app.datawatch.io/</span>
                      <input
                        id="workspace"
                        className="flex-1 bg-transparent outline-none font-mono ml-1"
                        placeholder="acme"
                        value={form.org_slug}
                        onChange={set('org_slug')}
                        disabled={workspaceLocked}
                        pattern="[a-z0-9-]+"
                        required
                      />
                    </div>
                    {workspaceLocked && (
                      <p className="text-xs text-muted-foreground">Workspace detected from URL.</p>
                    )}
                  </div>

                  {mode === 'register' && (
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="flex flex-col gap-1.5">
                        <Label htmlFor="org-name">Organisation name</Label>
                        <Input id="org-name" value={form.org_name} onChange={set('org_name')} placeholder="Acme Corp" required />
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <Label htmlFor="full-name">Your name</Label>
                        <Input id="full-name" value={form.full_name} onChange={set('full_name')} placeholder="Jane Doe" />
                      </div>
                    </div>
                  )}

                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="email">Email address</Label>
                    <Input id="email" type="email" value={form.email} onChange={set('email')} placeholder="you@company.com" required />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="password">Password</Label>
                    <Input id="password" type="password" value={form.password} onChange={set('password')} placeholder="Enter password" required />
                  </div>

                  <div className="flex items-center gap-2">
                    <Checkbox id="remember" checked={remember} onCheckedChange={(v) => setRemember(!!v)} />
                    <Label htmlFor="remember" className="text-sm font-normal cursor-pointer select-none">
                      Keep me signed in for 7 days
                    </Label>
                  </div>

                  {error && (
                    <Alert variant="destructive" className="py-2">
                      <AlertCircle className="size-4" />
                      <AlertDescription>{error}</AlertDescription>
                    </Alert>
                  )}

                  <Button type="submit" disabled={loading} className="w-full font-semibold">
                    {loading && <Loader2 className="size-4 mr-2 animate-spin" />}
                    {mode === 'login' ? 'Sign in' : 'Create workspace'}
                  </Button>
                </form>

                {mode === 'login' && (
                  <>
                    <Separator />
                    <p className="text-center text-xs text-muted-foreground">
                      Don't have a workspace?{' '}
                      <button
                        type="button"
                        className="underline underline-offset-4 hover:text-foreground"
                        onClick={() => setMode('register')}
                      >
                        Create one
                      </button>
                    </p>
                  </>
                )}
              </CardContent>
            </Card>
          </div>
        </main>
      </div>
    </div>
  )
}
