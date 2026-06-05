import { useEffect, useState } from 'react'
import { Loader2, Plus, UserX } from 'lucide-react'
import { adminCreateStaff, adminDeactivateStaff, adminGetStaff } from '../../api/endpoints'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { toast } from 'sonner'
import { storage } from '@/lib/storage'

export default function AdminStaff() {
  const [staff, setStaff] = useState([])
  const [loading, setLoading] = useState(true)
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ email: '', password: '', full_name: '' })
  const [saving, setSaving] = useState(false)

  const set = (k) => (e) => setForm((p) => ({ ...p, [k]: e.target.value }))
  const currentEmail = storage.getItem('dw_staff_email')

  const reload = () => adminGetStaff().then((r) => setStaff(r.data)).finally(() => setLoading(false))

  useEffect(() => { reload() }, [])

  const create = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      await adminCreateStaff(form)
      toast.success(`Staff account created for ${form.email}`)
      setForm({ email: '', password: '', full_name: '' })
      setOpen(false)
      reload()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create staff')
    } finally { setSaving(false) }
  }

  const deactivate = async (id, email) => {
    if (!confirm(`Deactivate ${email}?`)) return
    try {
      await adminDeactivateStaff(id)
      toast.success('Staff deactivated')
      reload()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed')
    }
  }

  if (loading) return <div className="flex justify-center py-20"><Loader2 className="size-6 animate-spin text-muted-foreground" /></div>

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Staff</h1>
          <p className="text-sm text-muted-foreground">DataWatch team members with admin portal access</p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button size="sm" className="gap-2"><Plus className="size-4" />Add staff</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create staff account</DialogTitle>
            </DialogHeader>
            <form onSubmit={create} className="flex flex-col gap-4 mt-2">
              <div className="flex flex-col gap-1.5">
                <Label>Email</Label>
                <Input type="email" value={form.email} onChange={set('email')} placeholder="name@datawatch.io" required />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Full name</Label>
                <Input value={form.full_name} onChange={set('full_name')} placeholder="Jane Doe" />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Password</Label>
                <Input type="password" value={form.password} onChange={set('password')} placeholder="Temporary password" required />
              </div>
              <Button type="submit" disabled={saving}>
                {saving && <Loader2 className="size-4 mr-2 animate-spin" />}
                Create account
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Email</TableHead>
              <TableHead>Name</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Joined</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {staff.map((s) => (
              <TableRow key={s.id}>
                <TableCell className="font-mono text-sm">
                  {s.email}
                  {s.email === currentEmail && (
                    <Badge variant="outline" className="ml-2 text-xs">you</Badge>
                  )}
                </TableCell>
                <TableCell className="text-sm">{s.full_name || '—'}</TableCell>
                <TableCell>
                  <Badge variant={s.is_active ? 'default' : 'secondary'}>
                    {s.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {new Date(s.created_at).toLocaleDateString()}
                </TableCell>
                <TableCell>
                  {s.is_active && s.email !== currentEmail && (
                    <Button variant="ghost" size="icon" onClick={() => deactivate(s.id, s.email)} title="Deactivate">
                      <UserX className="size-4 text-destructive" />
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  )
}
