export const FALLBACK_CONNECTORS = [
  {
    type: 'postgres',
    label: 'PostgreSQL',
    description: 'PostgreSQL / Aurora Postgres',
    required: ['host', 'database'],
    optional: { port: 5432, username: '', password: '' },
    versions: ['Auto-detect', 'PostgreSQL 16', 'PostgreSQL 15', 'PostgreSQL 14', 'Aurora PostgreSQL'],
  },
  {
    type: 'mysql',
    label: 'MySQL / MariaDB',
    description: 'MySQL 5.7+, MariaDB 10+',
    required: ['host', 'database'],
    optional: { port: 3306, username: 'root', password: '' },
    versions: ['Auto-detect', 'MySQL 8', 'MySQL 5.7', 'MariaDB 11', 'MariaDB 10'],
  },
  {
    type: 'bigquery',
    label: 'Google BigQuery',
    description: 'Google Cloud BigQuery',
    required: ['project_id'],
    optional: { credentials_json: null, dataset: null },
    versions: ['Auto-detect', 'Standard SQL'],
  },
  {
    type: 'duckdb',
    label: 'DuckDB',
    description: 'DuckDB in-process OLAP',
    required: [],
    optional: { path: ':memory:' },
    versions: ['Auto-detect', '0.10+', '1.x'],
  },
]

const FIELD_LABELS = {
  host: 'Host',
  port: 'Port',
  database: 'Database',
  username: 'Username',
  user: 'User',
  password: 'Password',
  project_id: 'Project ID',
  credentials_json: 'Service account JSON',
  dataset: 'Dataset',
  account: 'Account',
  warehouse: 'Warehouse',
  schema: 'Default schema',
  path: 'File path',
  uri: 'URI',
  hosts: 'Hosts',
  keyspace: 'Keyspace',
  driver: 'ODBC driver',
  server_hostname: 'Server hostname',
  http_path: 'HTTP path',
  access_token: 'Access token',
  catalog: 'Catalog',
  http_scheme: 'HTTP scheme',
}

const SECRET_FIELDS = new Set(['password', 'credentials_json', 'uri', 'access_token'])

export function normalizeConnector(connector) {
  const required = connector.required || []
  const optional = connector.optional || {}
  const fields = connector.fields?.length
    ? connector.fields
    : [
        ...required.map((name) => makeField(name, '', true)),
        ...Object.entries(optional).map(([name, value]) => makeField(name, value, false)),
      ]

  return {
    ...connector,
    fields,
    versions: connector.versions?.length ? connector.versions : ['Auto-detect'],
  }
}

function makeField(name, value, required) {
  return {
    name,
    label: FIELD_LABELS[name] || titleize(name),
    required,
    default: value,
    input_type: typeof value === 'number' ? 'number' : name.includes('json') ? 'textarea' : SECRET_FIELDS.has(name) ? 'password' : 'text',
    secret: SECRET_FIELDS.has(name),
  }
}

export function defaultConfigFor(connector) {
  return Object.fromEntries(
    connector.fields.map((field) => [
      field.name,
      field.default ?? '',
    ])
  )
}

export function castFieldValue(field, value) {
  if (field.input_type === 'number') {
    if (value === '') return ''
    const number = Number(value)
    return Number.isFinite(number) ? number : value
  }
  if (field.name.includes('json') && typeof value === 'string' && value.trim()) {
    try {
      return JSON.parse(value)
    } catch {
      return value
    }
  }
  return value
}

export function connectorLabel(type, connectors = []) {
  return connectors.find((connector) => connector.type === type)?.label || titleize(type)
}

export function titleize(value) {
  return String(value || '')
    .replace(/[_-]/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

export function extractColumnsFromDDL(ddl = '') {
  const body = ddl.slice(ddl.indexOf('(') + 1, ddl.lastIndexOf(')'))
  if (!body) return []
  return body
    .split('\n')
    .map((line) => line.trim().replace(/,$/, ''))
    .filter(Boolean)
    .map((line) => {
      const [name, ...typeParts] = line.split(/\s+/)
      return {
        name: name?.replace(/["`[\]]/g, ''),
        type: typeParts.join(' '),
      }
    })
    .filter((column) => column.name && !['constraint', 'primary', 'foreign', 'unique'].includes(column.name.toLowerCase()))
}

export function freshnessCandidates(columns) {
  const preferred = ['updated_at', 'created_at', 'modified_at', 'ingested_at', 'loaded_at', 'event_time', 'timestamp']
  return [...columns].sort((a, b) => {
    const ai = preferred.indexOf(a.name.toLowerCase())
    const bi = preferred.indexOf(b.name.toLowerCase())
    if (ai === -1 && bi === -1) return a.name.localeCompare(b.name)
    if (ai === -1) return 1
    if (bi === -1) return -1
    return ai - bi
  })
}

