import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ExternalLink, Loader2, Search } from 'lucide-react'
import { adminGetAllUsers } from '../../api/endpoints'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

export default function AdminUsers() {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [q, setQ] = useState('')

  useEffect(() => {
    adminGetAllUsers().then((r) => setUsers(r.data)).finally(() => setLoading(false))
  }, [])

  const filtered = users.filter(
    (u) => u.email.includes(q) || (u.full_name || '').toLowerCase().includes(q.toLowerCase()) || u.org_slug.includes(q)
  )

  if (loading) return <div className="flex justify-center py-20"><Loader2 className="size-6 animate-spin text-muted-foreground" /></div>

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold">All Users</h1>
        <p className="text-sm text-muted-foreground">{users.length} users across all workspaces</p>
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
        <Input className="pl-9" placeholder="Search by email, name, or workspace…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Email</TableHead>
              <TableHead>Name</TableHead>
              <TableHead>Workspace</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Last login</TableHead>
              <TableHead>Joined</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((u) => (
              <TableRow key={u.id}>
                <TableCell className="font-mono text-sm">{u.email}</TableCell>
                <TableCell className="text-sm">{u.full_name || '—'}</TableCell>
                <TableCell>
                  <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-mono">{u.org_slug}</span>
                </TableCell>
                <TableCell><Badge variant="outline" className="capitalize text-xs">{u.role}</Badge></TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {u.last_login_at ? new Date(u.last_login_at).toLocaleDateString() : '—'}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {new Date(u.created_at).toLocaleDateString()}
                </TableCell>
                <TableCell>
                  <Button variant="ghost" size="icon" asChild title="View org">
                    <Link to={`/orgs?slug=${u.org_slug}`}><ExternalLink className="size-4" /></Link>
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  )
}
