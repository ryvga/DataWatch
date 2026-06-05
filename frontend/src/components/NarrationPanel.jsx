import { useEffect, useRef, useState } from 'react'
import { BrainCircuit, Loader2, RefreshCw } from 'lucide-react'
import { getIncident, retryNarration } from '../api/endpoints'
import { notify } from '@/lib/notify'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

const CONFIDENCE_STYLES = {
  high: 'border-emerald-600/25 bg-emerald-600/10 text-emerald-700 dark:text-emerald-300',
  medium: 'border-amber-600/25 bg-amber-500/12 text-amber-700 dark:text-amber-300',
  low: 'border-stone-500/25 bg-stone-500/10 text-stone-700 dark:text-stone-300',
}

const PROBABILITY_STYLES = {
  high: 'border-red-600/25 bg-red-600/10 text-red-700 dark:text-red-300',
  medium: 'border-amber-600/25 bg-amber-500/12 text-amber-700 dark:text-amber-300',
  low: 'border-stone-500/25 bg-stone-500/10 text-stone-700 dark:text-stone-300',
}

// Stop polling after 90 seconds (30 × 3s intervals)
const MAX_POLLS = 30

function AnalysisSkeleton() {
  return (
    <div className="flex flex-col gap-3">
      <Skeleton className="h-4 w-3/4" />
      <Skeleton className="h-4 w-1/2" />
      <Skeleton className="h-4 w-5/6" />
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div className="flex flex-col gap-2">
      <h4 className="text-sm font-medium text-foreground">{title}</h4>
      {children}
    </div>
  )
}

export default function NarrationPanel({ incidentId, initialNarration }) {
  const [narration, setNarration] = useState(initialNarration)
  const [polling, setPolling] = useState(!initialNarration || !!initialNarration?.error)
  const [timedOut, setTimedOut] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const pollCount = useRef(0)

  useEffect(() => {
    if (!polling) return
    const id = setInterval(async () => {
      pollCount.current += 1
      if (pollCount.current >= MAX_POLLS) {
        clearInterval(id)
        setPolling(false)
        setTimedOut(true)
        return
      }
      try {
        const res = await getIncident(incidentId)
        const n = res.data.llm_narration
        if (n && !n.error) {
          setNarration(n)
          setPolling(false)
        } else if (n?.error) {
          // Backend returned an explicit error — stop polling
          setNarration(n)
          setPolling(false)
        }
      } catch (_) {}
    }, 3000)
    return () => clearInterval(id)
  }, [incidentId, polling])

  if (polling) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Loader2 className="size-4 animate-spin text-muted-foreground" />
            Generating incident analysis
          </CardTitle>
        </CardHeader>
        <CardContent>
          <AnalysisSkeleton />
          <p className="mt-3 text-xs text-muted-foreground">
            The AI is analysing this incident. This usually takes 10–30 seconds.
          </p>
        </CardContent>
      </Card>
    )
  }

  const handleRetry = async () => {
    setRetrying(true)
    try {
      notify.narration.retrying()
      await retryNarration(incidentId)
      setNarration(null)
      setTimedOut(false)
      pollCount.current = 0
      setPolling(true)
    } catch (_) {
      notify.narration.failed()
    } finally {
      setRetrying(false)
    }
  }

  if (timedOut || narration?.error) {
    const message = timedOut
      ? 'Analysis timed out — the LLM task is taking longer than expected.'
      : `Analysis failed: ${narration?.reason || 'unknown error'}`

    return (
      <Card>
        <CardHeader className="flex-row items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <BrainCircuit className="size-4 text-muted-foreground" />
            Incident analysis
          </CardTitle>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleRetry}
            disabled={retrying}
          >
            <RefreshCw className={cn('size-3.5 mr-1.5', retrying && 'animate-spin')} />
            {retrying ? 'Queuing…' : 'Retry analysis'}
          </Button>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          {message}
          <p className="mt-2 text-xs">
            Using model: <code className="font-mono">{import.meta.env.VITE_LLM_MODEL || 'nvidia/nemotron-3-super-120b-a12b:free'}</code>
          </p>
        </CardContent>
      </Card>
    )
  }

  if (!narration) return null

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <BrainCircuit className="size-4 text-muted-foreground" />
          Incident analysis
        </CardTitle>
        <Badge variant="outline" className={cn('capitalize', CONFIDENCE_STYLES[narration.confidence] || CONFIDENCE_STYLES.low)}>
          {narration.confidence} confidence
        </Badge>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <p className="text-sm leading-6 text-foreground">{narration.summary}</p>

        {narration.likely_causes?.length > 0 && (
          <Section title="Likely causes">
            <ul className="flex flex-col gap-2">
              {narration.likely_causes.map((cause, i) => (
                <li key={i} className="grid grid-cols-[auto_minmax(0,1fr)] gap-2 text-sm">
                  <Badge
                    variant="outline"
                    className={cn('mt-0.5 capitalize', PROBABILITY_STYLES[cause.probability] || PROBABILITY_STYLES.low)}
                  >
                    {cause.probability}
                  </Badge>
                  <span className="leading-6 text-muted-foreground">{cause.hypothesis}</span>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {narration.impact_assessment && (
          <Section title="Impact">
            <p className="text-sm leading-6 text-muted-foreground">{narration.impact_assessment}</p>
          </Section>
        )}

        {narration.recommended_actions?.length > 0 && (
          <Section title="Recommended actions">
            <ol className="list-decimal space-y-1.5 pl-5 text-sm leading-6 text-muted-foreground">
              {narration.recommended_actions.map((action, i) => (
                <li key={i}>{action}</li>
              ))}
            </ol>
          </Section>
        )}

        {narration.data_pattern_notes && (
          <Section title="Pattern notes">
            <p className="text-sm leading-6 text-muted-foreground">{narration.data_pattern_notes}</p>
          </Section>
        )}
      </CardContent>
    </Card>
  )
}
