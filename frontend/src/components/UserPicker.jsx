import { useState, useEffect } from 'react'
import { getOrgMembers } from '../api/endpoints'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Input } from '@/components/ui/input'

export default function UserPicker({ value, onChange, placeholder = 'Select user…', excludeIds = [] }) {
  const [members, setMembers] = useState([])
  const [search, setSearch] = useState('')

  useEffect(() => {
    getOrgMembers().then(r => {
      const raw = r.data
      setMembers(Array.isArray(raw) ? raw : raw?.items || raw?.members || [])
    }).catch(() => {})
  }, [])

  const filtered = members.filter(m =>
    !excludeIds.includes(m.id) &&
    (!search || m.email.toLowerCase().includes(search.toLowerCase()) ||
     (m.full_name || '').toLowerCase().includes(search.toLowerCase()))
  )

  return (
    <Select value={value || ''} onValueChange={onChange}>
      <SelectTrigger className="w-full">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        <div className="p-2">
          <Input
            className="h-8 text-xs"
            placeholder="Search members…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onClick={(e) => e.stopPropagation()}
          />
        </div>
        <SelectGroup>
          {filtered.map(m => (
            <SelectItem key={m.id} value={m.id}>
              {m.full_name ? `${m.full_name} (${m.email})` : m.email}
            </SelectItem>
          ))}
          {filtered.length === 0 && (
            <div className="px-3 py-2 text-xs text-muted-foreground">No members found</div>
          )}
        </SelectGroup>
      </SelectContent>
    </Select>
  )
}
