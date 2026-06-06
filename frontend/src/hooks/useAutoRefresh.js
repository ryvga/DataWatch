import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * useAutoRefresh(callback, intervalMs, options)
 * - Runs callback() immediately on mount, then every intervalMs
 * - Pauses when tab is hidden (document.visibilityState)
 * - Returns { lastRefreshed, isRefreshing, refresh } — call refresh() to trigger immediately
 * - options.enabled (default true) — set false to pause
 */
export function useAutoRefresh(callback, intervalMs = 30000, { enabled = true } = {}) {
  const [lastRefreshed, setLastRefreshed] = useState(null)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const callbackRef = useRef(callback)
  const isRefreshingRef = useRef(false)
  callbackRef.current = callback

  const refresh = useCallback(async () => {
    if (isRefreshingRef.current) return
    isRefreshingRef.current = true
    setIsRefreshing(true)
    try {
      await callbackRef.current()
    } finally {
      isRefreshingRef.current = false
      setIsRefreshing(false)
      setLastRefreshed(new Date())
    }
  }, [])

  useEffect(() => {
    if (!enabled) return
    refresh()
    if (!intervalMs || intervalMs <= 0) return
    const id = setInterval(() => {
      if (document.visibilityState !== 'hidden') refresh()
    }, intervalMs)
    return () => clearInterval(id)
  }, [enabled, intervalMs]) // eslint-disable-line react-hooks/exhaustive-deps

  return { lastRefreshed, isRefreshing, refresh }
}
