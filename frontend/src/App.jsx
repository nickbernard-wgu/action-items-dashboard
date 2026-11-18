import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import './App.css'

const API_URL = import.meta.env.VITE_API_URL ?? ''

const ALL_BUCKETS = ['fresh', 'aging', 'stale', 'critical']

const BUCKET_LABEL = {
  fresh: 'Fresh',
  aging: 'Aging',
  stale: 'Stale',
  critical: 'Critical',
}

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

// ── Confirmation Modal ──────────────────────────────────────────────────────

function ConfirmModal({ item, onConfirm, onCancel, isLoading }) {
  const truncated = item.text.length > 100 ? item.text.slice(0, 100) + '…' : item.text

  return createPortal(
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="modal-heading">
      <div className="modal-box">
        <h2 id="modal-heading" className="modal-heading">Mark item complete?</h2>
        <p className="modal-body">{truncated}</p>
        <div className="modal-actions">
          <button
            className="btn-confirm"
            onClick={onConfirm}
            disabled={isLoading}
          >
            {isLoading ? 'Saving…' : 'Confirm'}
          </button>
          <button className="btn-cancel" onClick={onCancel} disabled={isLoading}>
            Cancel
          </button>
        </div>
      </div>
    </div>,
    document.body
  )
}

// ── Error Toast ─────────────────────────────────────────────────────────────

function ErrorToast({ message, onDismiss }) {
  return (
    <div className="error-toast" role="alert" aria-live="assertive">
      {message}
      <button className="toast-dismiss" onClick={onDismiss} aria-label="Dismiss">×</button>
    </div>
  )
}

// ── Action Item Card ────────────────────────────────────────────────────────

function ActionItem({ item, onMarkComplete }) {
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
      <div className="item-actions">
        <button className="btn-mark-complete" onClick={() => onMarkComplete(item)}>
          Mark Complete
        </button>
      </div>
    </div>
  )
}

// ── Owner Group ─────────────────────────────────────────────────────────────

function OwnerGroup({ owner, items, onMarkComplete }) {
  return (
    <section className="owner-group">
      <h2 className="owner-heading">
        {owner}
        <span className="owner-count">{items.length} open</span>
      </h2>
      <div className="items-list">
        {items.map((item) => (
          <ActionItem key={item.item_id} item={item} onMarkComplete={onMarkComplete} />
        ))}
      </div>
    </section>
  )
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function groupByOwner(items) {
  const map = {}
  for (const item of items) {
    const owner = item.owner || 'Unassigned'
    if (!map[owner]) map[owner] = []
    map[owner].push(item)
  }
  return Object.entries(map).sort(([a], [b]) => a.localeCompare(b))
}

function getUniqueOwners(items) {
  const owners = items.map((i) => i.owner || 'Unassigned')
  return [...new Set(owners)].sort((a, b) => a.localeCompare(b))
}

// ── App ─────────────────────────────────────────────────────────────────────

export default function App() {
  const [data, setData] = useState(null)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Filter state
  const [ownerFilter, setOwnerFilter] = useState('all')
  const [bucketFilter, setBucketFilter] = useState(new Set(ALL_BUCKETS))

  // Modal state
  const [modalItem, setModalItem] = useState(null)
  const [modalLoading, setModalLoading] = useState(false)

  // Toast state
  const [toast, setToast] = useState(null)
  const toastTimerRef = useRef(null)

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
        setItems(json.items ?? [])
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  // ── Filter logic ──────────────────────────────────────────────────────────

  const visibleItems = items.filter((item) => {
    const owner = item.owner || 'Unassigned'
    if (ownerFilter !== 'all' && owner !== ownerFilter) return false
    if (!bucketFilter.has(item.age_bucket)) return false
    return true
  })

  const toggleBucket = (bucket) => {
    setBucketFilter((prev) => {
      const next = new Set(prev)
      if (next.has(bucket)) {
        next.delete(bucket)
      } else {
        next.add(bucket)
      }
      return next
    })
  }

  const filtersActive = ownerFilter !== 'all' || bucketFilter.size < ALL_BUCKETS.length

  // ── Mark-complete handlers ────────────────────────────────────────────────

  const handleMarkComplete = (item) => {
    setModalItem(item)
  }

  const handleCancel = () => {
    setModalItem(null)
  }

  const showToast = (msg) => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
    setToast(msg)
    toastTimerRef.current = setTimeout(() => setToast(null), 4000)
  }

  const handleConfirm = async () => {
    const item = modalItem
    setModalLoading(true)

    // Optimistically remove
    setItems((prev) => prev.filter((i) => i.item_id !== item.item_id))
    setModalItem(null)
    setModalLoading(false)

    try {
      const res = await fetch(`${API_URL}/action-items/${item.item_id}/complete`, {
        method: 'POST',
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      // success: stays removed
    } catch {
      // Restore item at original position
      setItems((prev) => {
        const originalItems = data?.items ?? []
        const restored = []
        for (const orig of originalItems) {
          if (orig.item_id === item.item_id) {
            restored.push(item)
          } else if (prev.find((p) => p.item_id === orig.item_id)) {
            restored.push(orig)
          }
        }
        return restored
      })
      showToast('Failed to mark complete — please try again')
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  const uniqueOwners = getUniqueOwners(items)
  const grouped = groupByOwner(visibleItems)

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <h1>Action Items Dashboard</h1>
        <p className="last-synced">
          Last refreshed:{' '}
          <time>{data ? formatDateTime(data.last_synced) : 'Never'}</time>
        </p>
      </header>

      {!loading && !error && data && (
        <div className="filter-bar" role="search" aria-label="Filter action items">
          {/* Owner filter */}
          <label className="filter-label" htmlFor="owner-filter">
            Owner
          </label>
          <select
            id="owner-filter"
            className="owner-select"
            value={ownerFilter}
            onChange={(e) => setOwnerFilter(e.target.value)}
          >
            <option value="all">All owners</option>
            {uniqueOwners.map((o) => (
              <option key={o} value={o}>{o}</option>
            ))}
          </select>

          {/* Age-bucket filter */}
          <span className="filter-label">Age</span>
          <div className="bucket-filter" role="group" aria-label="Age bucket filter">
            {ALL_BUCKETS.map((bucket) => (
              <label key={bucket} className={`bucket-btn ${bucketFilter.has(bucket) ? 'active' : ''}`}>
                <input
                  type="checkbox"
                  className="bucket-checkbox"
                  checked={bucketFilter.has(bucket)}
                  onChange={() => toggleBucket(bucket)}
                />
                {BUCKET_LABEL[bucket]}
              </label>
            ))}
          </div>

          {/* Visible count */}
          {filtersActive && (
            <span className="filter-count">
              Showing {visibleItems.length} of {items.length} items
            </span>
          )}
        </div>
      )}

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
            {grouped.map(([owner, ownerItems]) => (
              <OwnerGroup
                key={owner}
                owner={owner}
                items={ownerItems}
                onMarkComplete={handleMarkComplete}
              />
            ))}
          </>
        )}
      </main>

      {/* Confirmation modal */}
      {modalItem && (
        <ConfirmModal
          item={modalItem}
          onConfirm={handleConfirm}
          onCancel={handleCancel}
          isLoading={modalLoading}
        />
      )}

      {/* Error toast */}
      {toast && (
        <ErrorToast message={toast} onDismiss={() => setToast(null)} />
      )}
    </div>
  )
}
