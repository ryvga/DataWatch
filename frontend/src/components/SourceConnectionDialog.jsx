import { useEffect, useMemo, useState } from 'react'
import { CheckCircle2, Database, Loader2, Send, XCircle } from 'lucide-react'
import { createSource, getConnectorTypes, testSourceConfig } from '@/api/endpoints'
import { notify } from '@/lib/notify'
import { FALLBACK_CONNECTORS, castFieldValue, defaultConfigFor, normalizeConnector } from '@/lib/connectorConfig'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

function parseJson(value, label) {
  try {
    return [JSON.parse(value || '{}'), '']
  } catch (err) {
    return [null, `${label} must be valid JSON: ${err.message}`]
  }
}

function cleanConfig(config) {
  return Object.fromEntries(
    Object.entries(config).filter(([, value]) => value !== '' && value !== null && value !== undefined)
  )
}

export default function SourceConnectionDialog({ open, onOpenChange, onCreated }) {
  const [connectors, setConnectors] = useState(FALLBACK_CONNECTORS.map(normalizeConnector))
  const [mode, setMode] = useState('fields')
  const [type, setType] = useState('postgres')
  const [name, setName] = useState('')
  const [version, setVersion] = useState('Auto-detect')
  const [fields, setFields] = useState(defaultConfigFor(connectors[0]))
  const [rawJson, setRawJson] = useState(JSON.stringify(defaultConfigFor(connectors[0]), null, 2))
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [testResult, setTestResult] = useState(null)

  useEffect(() => {
    if (!open) return
    getConnectorTypes()
      .then((response) => setConnectors(response.data.map(normalizeConnector)))
      .catch(() => setConnectors(FALLBACK_CONNECTORS.map(normalizeConnector)))
  }, [open])

  const connector = useMemo(
    () => connectors.find((item) => item.type === type) || connectors[0],
    [connectors, type]
  )

  const resetForType = (nextType) => {
    const nextConnector = connectors.find((item) => item.type === nextType) || connectors[0]
    const nextFields = defaultConfigFor(nextConnector)
    setType(nextType)
    setVersion(nextConnector.versions[0] || 'Auto-detect')
    setFields(nextFields)
    setRawJson(JSON.stringify(nextFields, null, 2))
    setTestResult(null)
    setError('')
  }

  const updateField = (field, value) => {
    setFields((prev) => {
      const next = { ...prev, [field.name]: castFieldValue(field, value) }
      if (mode === 'fields') setRawJson(JSON.stringify(cleanConfig(next), null, 2))
      return next
    })
    setTestResult(null)
  }

  const buildConfig = () => {
    if (mode === 'json') {
      const [config, parseError] = parseJson(rawJson, 'Connection JSON')
      if (parseError) return [null, parseError]
      return [cleanConfig({ ...config, database_version: version }), '']
    }
    return [cleanConfig({ ...fields, database_version: version }), '']
  }

  const runTest = async () => {
    const [connection_config, parseError] = buildConfig()
    if (parseError) {
      setError(parseError)
      return
    }
    setTesting(true)
    setError('')
    setTestResult(null)
    try {
      const response = await testSourceConfig({ type, connection_config })
      setTestResult(response.data)
      if (response.data.connected) notify.ok('Connection test passed', `${connector.label} responded in ${response.data.latency_ms}ms.`)
      else notify.err('Connection test failed', response.data.error)
    } catch (err) {
      const message = err.response?.data?.detail || 'Connection test failed'
      setError(message)
      setTestResult({ connected: false, error: message, latency_ms: 0 })
      notify.err('Connection test failed', message)
    } finally {
      setTesting(false)
    }
  }

  const submit = async (event) => {
    event.preventDefault()
    const [connection_config, parseError] = buildConfig()
    if (parseError) {
      setError(parseError)
      return
    }
    if (!testResult?.connected) {
      setError('Run a successful connection test before saving this source.')
      return
    }
    setSaving(true)
    setError('')
    try {
      const response = await createSource({ name, type, connection_config })
      onCreated(response.data)
      notify.source.connected(name)
      onOpenChange(false)
      setName('')
      resetForType('postgres')
    } catch (err) {
      const message = err.response?.data?.detail || 'Failed to create source'
      setError(message)
      notify.err(message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] overflow-hidden p-0 sm:max-w-4xl">
        <form onSubmit={submit} className="flex max-h-[92vh] flex-col">
          <DialogHeader className="border-b px-5 py-4">
            <DialogTitle>Add data source</DialogTitle>
            <DialogDescription>Configure, test, and save a warehouse connector. Credentials are encrypted per workspace.</DialogDescription>
          </DialogHeader>

          <div className="grid min-h-0 flex-1 overflow-hidden lg:grid-cols-[260px_minmax(0,1fr)]">
            <aside className="border-b bg-muted/25 p-4 lg:border-b-0 lg:border-r">
              <div className="space-y-3">
                <div className="flex flex-col gap-2">
                  <Label htmlFor="source-name">Source name</Label>
                  <Input id="source-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Production warehouse" required />
                </div>
                <div className="flex flex-col gap-2">
                  <Label>Connector</Label>
                  <Select value={type} onValueChange={resetForType}>
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        {connectors.map((item) => (
                          <SelectItem key={item.type} value={item.type}>{item.label}</SelectItem>
                        ))}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                </div>
                <div className="rounded-md border bg-card p-3 text-xs text-muted-foreground">
                  <div className="mb-1 flex items-center gap-2 font-medium text-foreground">
                    <Database className="size-3.5" />
                    {connector.label}
                  </div>
                  {connector.description}
                </div>
                <div className="flex flex-col gap-2">
                  <Label>Database version</Label>
                  <Select value={version} onValueChange={(value) => { setVersion(value); setTestResult(null) }}>
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        {connector.versions.map((item) => (
                          <SelectItem key={item} value={item}>{item}</SelectItem>
                        ))}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </aside>

            <div className="min-h-0 overflow-y-auto p-5">
              <Tabs value={mode} onValueChange={(value) => { setMode(value); setTestResult(null) }}>
                <TabsList>
                  <TabsTrigger value="fields">Form fields</TabsTrigger>
                  <TabsTrigger value="json">Advanced JSON</TabsTrigger>
                </TabsList>

                <TabsContent value="fields" className="mt-4">
                  <div className="grid gap-4 sm:grid-cols-2">
                    {connector.fields.map((field) => (
                      <div key={field.name} className={cn('flex flex-col gap-2', field.input_type === 'textarea' && 'sm:col-span-2')}>
                        <Label htmlFor={`source-${field.name}`}>
                          {field.label}
                          {field.required && <span className="text-destructive"> *</span>}
                        </Label>
                        {field.input_type === 'textarea' ? (
                          <Textarea
                            id={`source-${field.name}`}
                            className="min-h-28 font-mono text-xs"
                            value={typeof fields[field.name] === 'string' ? fields[field.name] : JSON.stringify(fields[field.name] || {}, null, 2)}
                            onChange={(event) => updateField(field, event.target.value)}
                            placeholder={field.placeholder || ''}
                            required={field.required}
                          />
                        ) : field.input_type === 'select' && field.options?.length ? (
                          <Select value={String(fields[field.name] || field.options[0])} onValueChange={(value) => updateField(field, value)}>
                            <SelectTrigger className="w-full">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectGroup>
                                {field.options.map((option) => (
                                  <SelectItem key={option} value={option}>{option}</SelectItem>
                                ))}
                              </SelectGroup>
                            </SelectContent>
                          </Select>
                        ) : (
                          <Input
                            id={`source-${field.name}`}
                            type={field.input_type === 'number' ? 'number' : field.secret ? 'password' : 'text'}
                            value={fields[field.name] ?? ''}
                            onChange={(event) => updateField(field, event.target.value)}
                            placeholder={field.placeholder || ''}
                            required={field.required}
                          />
                        )}
                      </div>
                    ))}
                  </div>
                </TabsContent>

                <TabsContent value="json" className="mt-4">
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="source-json">Connection JSON</Label>
                    <Textarea
                      id="source-json"
                      className="min-h-[360px] font-mono text-xs"
                      value={rawJson}
                      onChange={(event) => { setRawJson(event.target.value); setTestResult(null) }}
                    />
                  </div>
                </TabsContent>
              </Tabs>

              <div className="mt-4 space-y-3">
                {testResult && (
                  <Alert variant={testResult.connected ? 'default' : 'destructive'}>
                    {testResult.connected ? <CheckCircle2 className="size-4" /> : <XCircle className="size-4" />}
                    <AlertDescription>
                      {testResult.connected
                        ? `Connection passed in ${testResult.latency_ms}ms. You can save this source.`
                        : testResult.error || 'Connection failed.'}
                    </AlertDescription>
                  </Alert>
                )}
                {error && (
                  <Alert variant="destructive">
                    <XCircle className="size-4" />
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                )}
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="button" variant="outline" onClick={runTest} disabled={testing || !name.trim()}>
              {testing ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <Send data-icon="inline-start" />}
              {testing ? 'Testing...' : 'Test connection'}
            </Button>
            <Button type="submit" disabled={saving || !testResult?.connected || !name.trim()}>
              {saving ? 'Saving...' : 'Save source'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

