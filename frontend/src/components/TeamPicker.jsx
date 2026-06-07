import { useState, useEffect } from 'react'
import { getTeams } from '../api/endpoints'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

export default function TeamPicker({ value, onChange, placeholder = 'Select team…' }) {
  const [teams, setTeams] = useState([])

  useEffect(() => {
    getTeams().then(r => setTeams(r.data || [])).catch(() => {})
  }, [])

  return (
    <Select value={value || ''} onValueChange={onChange}>
      <SelectTrigger className="w-full">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        <SelectGroup>
          {teams.map(t => (
            <SelectItem key={t.id} value={t.id}>
              <span className="flex items-center gap-2">
                {t.color && <span className="inline-block size-2.5 rounded-full shrink-0" style={{ background: t.color }} />}
                {t.name}
              </span>
            </SelectItem>
          ))}
          {teams.length === 0 && (
            <div className="px-3 py-2 text-xs text-muted-foreground">No teams yet</div>
          )}
        </SelectGroup>
      </SelectContent>
    </Select>
  )
}
