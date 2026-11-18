import { useEffect, useState } from 'react'
import './App.css'

const API_URL = import.meta.env.VITE_API_URL ?? ''

function formatDate(isoDate) {
  if (!isoDate) return ''
  const [year, month, day] = isoDate.split('-')
  const d = new Date(Number(year), Number(month) - 1, Number(day))
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatDateTime(iso) {
  if (!iso) return 'Never'
  const d = new Date(iso)
  return d.toLocaleString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: 'numeric', minute: '2-digit',
  })
}

const AGE_CLASS = {
  fresh: '',
  aging: 'age-aging',
  stale: 'age-stale',
  critical: 'age-critical',
}

const PRIORITY_COLOR = {
  P1: '#dc2626',
  P2: '#ea580c',
  P3: '#ca8a04',
  P4: '#16a34a',
}

function PriorityBadge({ priority }) {
  if (!priority) return null
  const color = PRIORITY_COLOR[priority] ?? '#6b7280'
  return (
    <span
      className="priority-badge"
      style={{ backgroundColor: color }}
      aria-label={`Priority ${priority}`}
    >
      {priority}
    </span>
  )
}

function ActionItem({ item }) {
  const ageClass = AGE_CLASS[item.age_bucket] ?? ''
  return (
    <div className={`action-item ${ageClass}`} data-age={item.age_bucket}>
      <div className="item-header">
        <span className="item-text">{item.text}</span>
        <PriorityBadge priority={item.priority} />
      </div>
      <div className="item-meta">
        {item.due_date && (
          <span className="meta-field due-date">
            Due: {formatDate(item.due_date)}
          </span>
        )}
        {item.blocked_by && (
          <span className="meta-field blocked-by">
            🚫 Blocked by: {item.blocked_by}
          </span>
        )}
        {item.secondary_owners && item.secondary_owners.length > 0 && (
          <span className="meta-field secondary-owners">
            Also: {item.secondary_owners.join(', ')}
          </span>
        )}
        <span className="meta-field created-date">
          Created: {formatDate(item.date_created_iso)}
        </span>
        {item.source_meeting_title && (
          <a
            className="meta-field source-link"
            href={item.source_meeting_url || '#'}
            target="_blank"
            rel="noopener noreferrer"
          >
            {item.source_meeting_title}
          </a>
        )}
      </div>
    </div>
  )
}

function OwnerGroup({ owner, items }) {
  return (
    <section className="owner-group">
      <h2 className="owner-heading">
        {owner}
        <span className="owner-count">{items.length} open</span>
      </h2>
      <div className="items-list">
        {items.map((item) => (
          <ActionItem key={item.item_id} item={item} />
        ))}
      </div>
    </section>
  )
}

function groupByOwner(items) {
  const map = {}
  for (const item of items) {
    const owner = item.owner || 'Unassigned'
    if (!map[owner]) map[owner] = []
    map[owner].push(item)
  }
  return Object.entries(map).sort(([a], [b]) => a.localeCompare(b))
}

export default function App() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetch(`${API_URL}/action-items`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then((json) => {
        setData(json)
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <h1>Action Items Dashboard</h1>
        <p className="last-synced">
          Last refreshed:{' '}
          <time>{data ? formatDateTime(data.last_synced) : 'Never'}</time>
        </p>
      </header>

      <main className="dashboard-main">
        {loading && (
          <div className="loading-state" role="status" aria-label="Loading">
            <div className="spinner" aria-hidden="true" />
            <p>Loading action items…</p>
          </div>
        )}

        {!loading && error && (
          <div className="error-state" role="alert">
            <p>Failed to load action items: {error}</p>
          </div>
        )}

        {!loading && !error && data && (
          <>
            {groupByOwner(data.items).map(([owner, items]) => (
              <OwnerGroup key={owner} owner={owner} items={items} />
            ))}
          </>
        )}
      </main>
    </div>
  )
}
