import { useEffect, useRef, useState } from 'react'
import { storage } from '@/lib/storage'

const listeners = new Set()
let socket = null
let subscribers = 0
let reconnectTimer = null
let reconnectAttempt = 0
let manualClose = false
let currentStatus = 'idle'

function emit(event) {
  listeners.forEach((listener) => {
    try { listener(event) } catch { /* one subscriber must not break the stream */ }
  })
}

function setStatus(status) {
  currentStatus = status
  emit({ type: 'realtime.status', payload: { status } })
}

function websocketUrl() {
  const configured = import.meta.env.VITE_API_URL
  const base = configured ? new URL(configured, window.location.href) : window.location
  const protocol = base.protocol === 'https:' ? 'wss:' : 'ws:'
  const token = encodeURIComponent(storage.getItem('dw_token') || '')
  return `${protocol}//${base.host}/api/v1/realtime/ws?token=${token}`
}

function scheduleReconnect() {
  if (manualClose || subscribers === 0 || reconnectTimer) return
  const delay = Math.min(30000, 1000 * (2 ** reconnectAttempt))
  reconnectAttempt += 1
  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = null
    connect()
  }, delay)
}

function connect() {
  if (manualClose || subscribers === 0) return
  const token = storage.getItem('dw_token')
  if (!token || typeof window.WebSocket !== 'function') {
    setStatus('unsupported')
    return
  }
  if (socket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(socket.readyState)) return

  setStatus('connecting')
  try {
    socket = new WebSocket(websocketUrl())
  } catch {
    setStatus('offline')
    scheduleReconnect()
    return
  }
  socket.addEventListener('open', () => {
    if (manualClose || subscribers === 0) {
      socket.close(1000, 'no subscribers')
      return
    }
    reconnectAttempt = 0
    setStatus('connected')
  })
  socket.addEventListener('message', (message) => {
    try { emit(JSON.parse(message.data)) } catch { /* malformed server events are ignored */ }
  })
  socket.addEventListener('error', () => setStatus('offline'))
  socket.addEventListener('close', () => {
    socket = null
    if (!manualClose && subscribers > 0) {
      setStatus('reconnecting')
      scheduleReconnect()
    } else {
      setStatus('idle')
    }
  })
}

function acquire() {
  subscribers += 1
  manualClose = false
  connect()
  return () => {
    subscribers = Math.max(0, subscribers - 1)
    if (subscribers === 0) {
      manualClose = true
      if (reconnectTimer) window.clearTimeout(reconnectTimer)
      reconnectTimer = null
      if (socket?.readyState === WebSocket.OPEN) {
        socket.close(1000, 'no subscribers')
        socket = null
      }
      setStatus('idle')
    }
  }
}

/** Subscribe to org-scoped events. Polling remains the fallback if this stream is unavailable. */
export function useRealtime(onEvent) {
  const callbackRef = useRef(onEvent)
  const [status, setLocalStatus] = useState(currentStatus)
  callbackRef.current = onEvent

  useEffect(() => {
    const listener = (event) => {
      if (event.type === 'realtime.status') setLocalStatus(event.payload?.status || 'idle')
      callbackRef.current?.(event)
    }
    listeners.add(listener)
    setLocalStatus(currentStatus)
    const release = acquire()
    return () => {
      listeners.delete(listener)
      release()
    }
  }, [])

  return { status, connected: status === 'connected' }
}
