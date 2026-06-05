import { useEffect, useMemo, useState } from 'react'
import { KeyRound, Loader2, Plus, UserX } from 'lucide-react'
import { toast } from 'sonner'
import { adminCreateStaff, adminDeactivateStaff, adminGetStaff, adminResetStaffPassword } from '../../api/endpoints'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { storage } from '@/lib/storage'
import { formatDateTime } from './adminUtils.jsx'

export default function AdminStaff() {
  const [staff, setStaff] = useState([])
  const [loading, setLoading] = useState(true)
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ email: '', password: '', full_name: '' })
  const [saving, setSaving] = useState(false)
  const [resetResult, setResetResult] = useState(null)

  const currentEmail = storage.getItem('dw_staff_email')
  const activeCount = useMemo(() => staff.filter((member) => member.is_active).length, [staff])

  const set = (key) => (event) => setForm((current) => ({ ...current, [key]: event.target.value }))

  const reload = async () => {
    setLoading(true)
    try {
      const response = await adminGetStaff()
      setStaff(Array.isArray(response.data) ? response.data : response.data?.items || [])
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to load staff')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { reload() }, [])

  const create = async (event) => {
    event.preventDefault()
    setSaving(true)
    try {
      await adminCreateStaff(form)
      toast.success(`Staff account created for ${form.email}`)
      setForm({ email: '', password: '', full_name: '' })
      setOpen(false)
      reload()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create staff')
    } finally {
      setSaving(false)
    }
  }

  const deactivate = async (member) => {
    if (!confirm(`Deactivate ${member.email}?`)) return
    setSaving(true)
    try {
      await adminDeactivateStaff(member.id)
      toast.success('Staff deactivated')
      reload()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to deactivate staff')
    } finally {
      setSaving(false)
    }
  }

  const resetPassword = async (member) => {
    setSaving(true)
    setResetResult(null)
    try {
      const response = await adminResetStaffPassword(member.id)
      const result = response.data || {}
      setResetResult({
        email: member.email,
        temporaryPassword: result.temporary_password || result.password,
        resetUrl: result.reset_url || result.url,
      })
      toast.success('Password reset created')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to reset staff password')
    } finally {
      setSaving(false)
    }
  }

  if (loading && staff.length === 0) {
    return <div className="flex justify-center py-20"><Loader2 className="size-6 animate-spin text-muted-foreground" /></div>
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Staff</h1>
          <p className="text-sm text-muted-foreground">{staff.length} staff accounts · {activeCount} active · admin portal access only</p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button size="sm"><Plus className="size-4" />Add staff</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create staff account</DialogTitle>
              <DialogDescription>Staff accounts are separate from workspace users and can access the admin portal.</DialogDescription>
            </DialogHeader>
            <form onSubmit={create} className="grid gap-4">
              <div className="grid gap-1.5">
                <Label>Email</Label>
                <Input type="email" value={form.email} onChange={set('email')} placeholder="name@datawatch.io" required />
              </div>
              <div className="grid gap-1.5">
                <Label>Full name</Label>
                <Input value={form.full_name} onChange={set('full_name')} placeholder="Jane Doe" />
              </div>
              <div className="grid gap-1.5">
                <Label>Temporary password</Label>
                <Input type="password" value={form.password} onChange={set('password')} placeholder="Temporary password" required />
              </div>
              <Button type="submit" disabled={saving}>
                {saving && <Loader2 className="size-4 animate-spin" />}
                Create account
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {resetResult && (
        <Card className="border-emerald-500/30 bg-emerald-500/10 p-4">
          <div className="text-sm font-medium text-emerald-800 dark:text-emerald-200">Password reset for {resetResult.email}</div>
          {resetResult.temporaryPassword && <code className="mt-2 block break-all font-mono text-sm">{resetResult.temporaryPassword}</code>}
          {resetResult.resetUrl && <code className="mt-2 block break-all font-mono text-sm">{resetResult.resetUrl}</code>}
          {!resetResult.temporaryPassword && !resetResult.resetUrl && <div className="mt-1 text-sm text-muted-foreground">The backend accepted the reset request.</div>}
        </Card>
      )}

      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Email</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Active status</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="w-56">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {staff.map((member) => (
                <TableRow key={member.id}>
                  <TableCell className="font-mono text-sm">
                    {member.email}
                    {member.email === currentEmail && <Badge variant="outline" className="ml-2">you</Badge>}
                  </TableCell>
                  <TableCell>{member.full_name || '-'}</TableCell>
                  <TableCell>
                    <Badge variant={member.is_active ? 'default' : 'secondary'}>{member.is_active ? 'Active' : 'Inactive'}</Badge>
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{formatDateTime(member.created_at)}</TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-2">
                      <Button variant="outline" size="sm" onClick={() => resetPassword(member)} disabled={saving || !member.is_active}>
                        <KeyRound className="size-4" />
                        Reset
                      </Button>
                      {member.is_active && member.email !== currentEmail && (
                        <Button variant="destructive" size="sm" onClick={() => deactivate(member)} disabled={saving}>
                          <UserX className="size-4" />
                          Deactivate
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
              {staff.length === 0 && (
                <TableRow><TableCell colSpan={5} className="py-10 text-center text-sm text-muted-foreground">No staff accounts found.</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </Card>
    </div>
  )
}
