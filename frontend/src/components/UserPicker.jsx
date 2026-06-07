import { useState } from 'react'

export default function UserPicker({ value, onChange, placeholder = 'Select user…', excludeIds = [], members = [] }) {
  const [search, setSearch] = useState('')

  const filtered = members.filter(m =>
    !excludeIds.includes(m.id) &&
    (!search ||
      (m.email || '').toLowerCase().includes(search.toLowerCase()) ||
      (m.full_name || '').toLowerCase().includes(search.toLowerCase()))
  )

  return (
    <div className="relative">
      <input
        type="text"
        className="input text-sm w-full"
        placeholder={search || (value ? members.find(m => m.id === value)?.full_name || members.find(m => m.id === value)?.email || placeholder : placeholder)}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        onFocus={() => {}}
      />
      {search && (
        <div className="absolute z-10 w-full mt-1 bg-gray-800 border border-gray-700 rounded-lg shadow-lg max-h-48 overflow-y-auto">
          {filtered.length === 0 ? (
            <div className="px-3 py-2 text-xs text-gray-500">No results</div>
          ) : (
            filtered.map(m => (
              <button
                key={m.id}
                type="button"
                className="w-full text-left px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 transition-colors"
                onClick={() => { onChange(m.id); setSearch('') }}
              >
                {m.full_name ? `${m.full_name} (${m.email})` : m.email}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}
