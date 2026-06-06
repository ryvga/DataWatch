import { useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { AlertCircle, Loader2 } from 'lucide-react'
import { acceptInvite } from '../api/endpoints'
import { BrandMark, ThemeToggle } from '../components/app-ui'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { notify } from '@/lib/notify'

function getApiError(err, fallback) {
  const detail = err.response?.data?.detail || err.response?.data?.error || err.message
  if (Array.isArray(detail)) return detail.map((item) => item.msg || item.message || String(item)).join(', ')
  if (detail && typeof detail === 'object') return detail.message || JSON.stringify(detail)
  return detail || fallback
}

export default function AcceptInvite() {
  const nav = useNavigate()
  const params = useParams()
  const [searchParams] = useSearchParams()
  const token = params.token || searchParams.get('token') || ''
  const [form, setForm] = useState({ full_name: '', password: '', confirm_password: '' })
  const [error, setError] = useState(token ? '' : 'Invite token is missing.')
  const [loading, setLoading] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    setError('')
    if (!token) {
      setError('Invite token is missing.')
      return
    }
    if (form.password !== form.confirm_password) {
      setError('Passwords do not match.')
      return
    }

    setLoading(true)
    try {
      await acceptInvite(token, {
        full_name: form.full_name,
        password: form.password,
      })
      notify.ok('Invite accepted', 'Sign in with your new account.')
      nav('/login', { replace: true })
    } catch (err) {
      setError(getApiError(err, 'Failed to accept invite'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto flex min-h-screen w-full max-w-xl flex-col px-4 py-4">
        <header className="flex items-center justify-between">
          <BrandMark />
          <ThemeToggle />
        </header>

        <main className="grid flex-1 place-items-center py-8">
          <Card className="w-full">
            <CardHeader>
              <CardTitle>Accept invite</CardTitle>
              <CardDescription>Create your Panopta account for this workspace.</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={submit} className="flex flex-col gap-4">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="invite-full-name">Full name</Label>
                  <Input
                    id="invite-full-name"
                    value={form.full_name}
                    onChange={(event) => setForm((prev) => ({ ...prev, full_name: event.target.value }))}
                    required
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="invite-password">Password</Label>
                  <Input
                    id="invite-password"
                    type="password"
                    minLength={8}
                    value={form.password}
                    onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
                    required
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="invite-confirm-password">Confirm password</Label>
                  <Input
                    id="invite-confirm-password"
                    type="password"
                    minLength={8}
                    value={form.confirm_password}
                    onChange={(event) => setForm((prev) => ({ ...prev, confirm_password: event.target.value }))}
                    required
                  />
                </div>

                {error && (
                  <Alert variant="destructive" className="py-2">
                    <AlertCircle className="size-4" />
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                )}

                <Button type="submit" disabled={loading || !token}>
                  {loading && <Loader2 className="mr-2 size-4 animate-spin" />}
                  Create account
                </Button>
              </form>
            </CardContent>
          </Card>
        </main>
      </div>
    </div>
  )
}
