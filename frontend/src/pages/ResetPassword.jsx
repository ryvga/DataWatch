import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { AlertCircle, Loader2 } from 'lucide-react'
import { confirmPasswordReset } from '../api/endpoints'
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

export default function ResetPassword() {
  const nav = useNavigate()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') || ''
  const [form, setForm] = useState({ new_password: '', confirm_password: '' })
  const [error, setError] = useState(token ? '' : 'Reset token is missing.')
  const [loading, setLoading] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    setError('')
    if (!token) {
      setError('Reset token is missing.')
      return
    }
    if (form.new_password !== form.confirm_password) {
      setError('Passwords do not match.')
      return
    }

    setLoading(true)
    try {
      await confirmPasswordReset({
        token,
        new_password: form.new_password,
      })
      notify.ok('Password reset', 'Sign in with your new password.')
      nav('/login', { replace: true })
    } catch (err) {
      setError(getApiError(err, 'Failed to reset password'))
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
              <CardTitle>Reset password</CardTitle>
              <CardDescription>Choose a new password for your DataWatch account.</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={submit} className="flex flex-col gap-4">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="reset-new-password">New password</Label>
                  <Input
                    id="reset-new-password"
                    type="password"
                    minLength={8}
                    value={form.new_password}
                    onChange={(event) => setForm((prev) => ({ ...prev, new_password: event.target.value }))}
                    required
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="reset-confirm-password">Confirm new password</Label>
                  <Input
                    id="reset-confirm-password"
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
                  Reset password
                </Button>
              </form>
            </CardContent>
          </Card>
        </main>
      </div>
    </div>
  )
}
