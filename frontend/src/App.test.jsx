import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

// ── Fixtures ──────────────────────────────────────────────────────────────────

const makeItem = (overrides = {}) => ({
  item_id: 'i1',
  status: 'open',
  text: 'Fix the pipeline',
  owner: 'Alice',
  secondary_owners: [],
  priority: '',
  due_date: '',
  blocked_by: '',
  source_page_id: 'p1',
  source_meeting_title: 'Sprint Review',
  source_meeting_url: 'https://example.com/meeting',
  date_created_iso: '2024-01-15',
  age_bucket: 'fresh',
  last_synced: '2024-02-01T10:00:00Z',
  ...overrides,
})

const makeResponse = (items, lastSynced = '2024-02-01T10:00:00Z') => ({
  items,
  last_synced: lastSynced,
})

// ── Helpers ───────────────────────────────────────────────────────────────────

function mockFetchResolves(data) {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(data),
  })
}

function mockFetchRejects(message = 'Network error') {
  global.fetch = vi.fn().mockRejectedValue(new Error(message))
}

function mockFetchPending() {
  global.fetch = vi.fn().mockReturnValue(new Promise(() => {}))
}

afterEach(() => {
  vi.restoreAllMocks()
})

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('age-bucket CSS classes', () => {
  it('applies age-aging to aging items', async () => {
    mockFetchResolves(makeResponse([makeItem({ item_id: 'a1', age_bucket: 'aging' })]))
    const { container } = render(<App />)
    await screen.findByText('Fix the pipeline')
    const card = container.querySelector('[data-age="aging"]')
    expect(card).toHaveClass('age-aging')
    expect(card).not.toHaveClass('age-stale')
    expect(card).not.toHaveClass('age-critical')
  })

  it('applies age-stale to stale items', async () => {
    mockFetchResolves(makeResponse([makeItem({ item_id: 'a2', age_bucket: 'stale' })]))
    const { container } = render(<App />)
    await screen.findByText('Fix the pipeline')
    const card = container.querySelector('[data-age="stale"]')
    expect(card).toHaveClass('age-stale')
  })

  it('applies age-critical to critical items', async () => {
    mockFetchResolves(makeResponse([makeItem({ item_id: 'a3', age_bucket: 'critical' })]))
    const { container } = render(<App />)
    await screen.findByText('Fix the pipeline')
    const card = container.querySelector('[data-age="critical"]')
    expect(card).toHaveClass('age-critical')
  })

  it('applies no age class to fresh items', async () => {
    mockFetchResolves(makeResponse([makeItem({ item_id: 'a4', age_bucket: 'fresh' })]))
    const { container } = render(<App />)
    await screen.findByText('Fix the pipeline')
    const card = container.querySelector('[data-age="fresh"]')
    expect(card).not.toHaveClass('age-aging')
    expect(card).not.toHaveClass('age-stale')
    expect(card).not.toHaveClass('age-critical')
  })
})

describe('owner groups', () => {
  it('renders each owner group with correct item counts', async () => {
    mockFetchResolves(
      makeResponse([
        makeItem({ item_id: '1', owner: 'Alice', text: 'Task A1' }),
        makeItem({ item_id: '2', owner: 'Alice', text: 'Task A2' }),
        makeItem({ item_id: '3', owner: 'Bob', text: 'Task B1' }),
      ])
    )
    render(<App />)
    await screen.findByText('Task A1')
    expect(screen.getByText(/Alice/)).toBeInTheDocument()
    expect(screen.getByText('2 open')).toBeInTheDocument()
    expect(screen.getByText(/Bob/)).toBeInTheDocument()
    expect(screen.getByText('1 open')).toBeInTheDocument()
  })

  it('sorts owner groups alphabetically', async () => {
    mockFetchResolves(
      makeResponse([
        makeItem({ item_id: '1', owner: 'Zara', text: 'Z task' }),
        makeItem({ item_id: '2', owner: 'Alice', text: 'A task' }),
      ])
    )
    render(<App />)
    await screen.findByText('Z task')
    const headings = screen.getAllByRole('heading', { level: 2 })
    expect(headings[0].textContent).toContain('Alice')
    expect(headings[1].textContent).toContain('Zara')
  })
})

describe('optional fields — render when present', () => {
  it('renders priority badge when priority is non-empty', async () => {
    mockFetchResolves(makeResponse([makeItem({ priority: 'P1' })]))
    render(<App />)
    expect(await screen.findByText('P1')).toBeInTheDocument()
  })

  it('renders due_date when present', async () => {
    mockFetchResolves(makeResponse([makeItem({ due_date: '2024-03-20' })]))
    render(<App />)
    expect(await screen.findByText(/Due:/)).toBeInTheDocument()
  })

  it('renders blocked_by when present', async () => {
    mockFetchResolves(makeResponse([makeItem({ blocked_by: 'Charlie' })]))
    render(<App />)
    expect(await screen.findByText(/Blocked by: Charlie/)).toBeInTheDocument()
  })

  it('renders secondary_owners when present', async () => {
    mockFetchResolves(makeResponse([makeItem({ secondary_owners: ['Dave', 'Eve'] })]))
    render(<App />)
    expect(await screen.findByText(/Also: Dave, Eve/)).toBeInTheDocument()
  })

  it('renders source meeting title as a link', async () => {
    mockFetchResolves(
      makeResponse([
        makeItem({
          source_meeting_title: 'Sprint Review',
          source_meeting_url: 'https://example.com/meeting',
        }),
      ])
    )
    render(<App />)
    const link = await screen.findByRole('link', { name: 'Sprint Review' })
    expect(link).toHaveAttribute('href', 'https://example.com/meeting')
    expect(link).toHaveAttribute('target', '_blank')
  })
})

describe('optional fields — absent means no empty labels', () => {
  it('does not render priority badge when priority is empty', async () => {
    mockFetchResolves(makeResponse([makeItem({ priority: '' })]))
    render(<App />)
    await screen.findByText('Fix the pipeline')
    expect(screen.queryByLabelText(/Priority/)).not.toBeInTheDocument()
  })

  it('does not render due date when due_date is empty', async () => {
    mockFetchResolves(makeResponse([makeItem({ due_date: '' })]))
    render(<App />)
    await screen.findByText('Fix the pipeline')
    expect(screen.queryByText(/Due:/)).not.toBeInTheDocument()
  })

  it('does not render blocked_by when empty', async () => {
    mockFetchResolves(makeResponse([makeItem({ blocked_by: '' })]))
    render(<App />)
    await screen.findByText('Fix the pipeline')
    expect(screen.queryByText(/Blocked by/)).not.toBeInTheDocument()
  })

  it('does not render secondary_owners when empty array', async () => {
    mockFetchResolves(makeResponse([makeItem({ secondary_owners: [] })]))
    render(<App />)
    await screen.findByText('Fix the pipeline')
    expect(screen.queryByText(/Also:/)).not.toBeInTheDocument()
  })
})

describe('loading state', () => {
  it('shows loading state while fetch is in flight', () => {
    mockFetchPending()
    render(<App />)
    expect(screen.getByRole('status', { name: /loading/i })).toBeInTheDocument()
    expect(screen.getByText(/Loading action items/i)).toBeInTheDocument()
  })

  it('removes loading state after data loads', async () => {
    mockFetchResolves(makeResponse([makeItem()]))
    render(<App />)
    await screen.findByText('Fix the pipeline')
    expect(screen.queryByRole('status', { name: /loading/i })).not.toBeInTheDocument()
  })
})

describe('last_synced timestamp', () => {
  it('renders formatted last refreshed time from last_synced', async () => {
    mockFetchResolves(makeResponse([makeItem()], '2024-02-01T10:00:00Z'))
    render(<App />)
    await screen.findByText('Fix the pipeline')
    expect(screen.getByText(/Last refreshed:/)).toBeInTheDocument()
    // Should contain "Feb" from the formatted date
    expect(screen.getByText(/Feb/)).toBeInTheDocument()
  })

  it('shows "Never" when last_synced is null', async () => {
    mockFetchResolves({ items: [], last_synced: null })
    render(<App />)
    await waitFor(() => {
      expect(screen.queryByRole('status', { name: /loading/i })).not.toBeInTheDocument()
    })
    expect(screen.getByText(/Never/)).toBeInTheDocument()
  })
})

describe('error state', () => {
  it('renders error state when fetch fails', async () => {
    mockFetchRejects('Network error')
    render(<App />)
    const alert = await screen.findByRole('alert')
    expect(alert).toBeInTheDocument()
    expect(alert).toHaveTextContent(/Failed to load action items/)
  })

  it('renders error state when server returns non-ok status', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 500 })
    render(<App />)
    const alert = await screen.findByRole('alert')
    expect(alert).toBeInTheDocument()
    expect(alert).toHaveTextContent(/HTTP 500/)
  })
})
