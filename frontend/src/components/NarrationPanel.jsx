import { useEffect, useState } from 'react'
import { getIncident } from '../api/endpoints'

const CONFIDENCE_COLORS = { high: 'text-green-400', medium: 'text-yellow-400', low: 'text-gray-400' }
const PROB_COLORS = { high: 'bg-red-500/15 text-red-400', medium: 'bg-orange-500/15 text-orange-400', low: 'bg-gray-500/15 text-gray-400' }

function Skeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      <div className="h-4 bg-gray-800 rounded w-3/4" />
      <div className="h-4 bg-gray-800 rounded w-1/2" />
      <div className="h-4 bg-gray-800 rounded w-5/6" />
    </div>
  )
}

export default function NarrationPanel({ incidentId, initialNarration }) {
  const [narration, setNarration] = useState(initialNarration)
  const [polling, setPolling] = useState(!initialNarration || !!initialNarration?.error)

  useEffect(() => {
    if (!polling) return
    const id = setInterval(async () => {
      try {
        const res = await getIncident(incidentId)
        const n = res.data.llm_narration
        if (n && !n.error) {
          setNarration(n)
          setPolling(false)
        }
      } catch (_) {}
    }, 3000)
    return () => clearInterval(id)
  }, [incidentId, polling])

  if (!narration || polling) {
    return (
      <div className="card space-y-4">
        <div className="flex items-center gap-2 text-gray-400 text-sm">
          <span className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
          Generating AI analysis…
        </div>
        <Skeleton />
      </div>
    )
  }

  if (narration.error) {
    return (
      <div className="card text-gray-500 text-sm">
        AI analysis unavailable — {narration.reason || 'unknown error'}
      </div>
    )
  }

  return (
    <div className="card space-y-5">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-gray-100">AI Incident Analysis</h3>
        <span className={`text-xs font-medium ${CONFIDENCE_COLORS[narration.confidence] || 'text-gray-400'}`}>
          {narration.confidence} confidence
        </span>
      </div>

      <p className="text-gray-200 text-sm leading-relaxed">{narration.summary}</p>

      {narration.likely_causes?.length > 0 && (
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Likely Causes</p>
          <ul className="space-y-2">
            {narration.likely_causes.map((c, i) => (
              <li key={i} className="flex items-start gap-2 text-sm">
                <span className={`mt-0.5 text-xs px-1.5 py-0.5 rounded font-medium ${PROB_COLORS[c.probability] || PROB_COLORS.low}`}>
                  {c.probability}
                </span>
                <span className="text-gray-300">{c.hypothesis}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {narration.impact_assessment && (
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">Impact</p>
          <p className="text-sm text-gray-300">{narration.impact_assessment}</p>
        </div>
      )}

      {narration.recommended_actions?.length > 0 && (
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Recommended Actions</p>
          <ol className="space-y-1.5 list-decimal list-inside">
            {narration.recommended_actions.map((a, i) => (
              <li key={i} className="text-sm text-gray-300">{a}</li>
            ))}
          </ol>
        </div>
      )}

      {narration.data_pattern_notes && (
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">Pattern Notes</p>
          <p className="text-sm text-gray-400 italic">{narration.data_pattern_notes}</p>
        </div>
      )}
    </div>
  )
}
