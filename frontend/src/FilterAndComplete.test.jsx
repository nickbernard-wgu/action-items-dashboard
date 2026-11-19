import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
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

function mockFetchGet(data) {
  global.fetch = vi.fn().mockImplementation((url, opts) => {
    if (!opts || opts.method !== 'POST') {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(data),
      })
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
  })
}

function mockFetchGetWithPostResult(data, postOk = true, postStatus = 200) {
  global.fetch = vi.fn().mockImplementation((url, opts) => {
    if (opts && opts.method === 'POST') {
      if (postOk) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
      }
      return Promise.resolve({ ok: false, status: postStatus })
    }
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve(data),
    })
  })
}

function mockFetchGetWithPostPending(data) {
  let resolvePost
  const postPromise = new Promise((res) => { resolvePost = res })
  global.fetch = vi.fn().mockImplementation((url, opts) => {
    if (opts && opts.method === 'POST') {
      return postPromise
    }
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve(data),
    })
  })
  return { resolvePost }
}

afterEach(() => {
  vi.restoreAllMocks()
})

// ── Filter bar: owner filter ──────────────────────────────────────────────────

describe('owner filter', () => {
  it('selecting an owner shows only that owner group, hides others', async () => {
    const user = userEvent.setup()
    mockFetchGet(
      makeResponse([
        makeItem({ item_id: '1', owner: 'Alice', text: 'Alice task' }),
        makeItem({ item_id: '2', owner: 'Bob', text: 'Bob task' }),
      ])
    )
    render(<App />)
    await screen.findByText('Alice task')

    const select = screen.getByRole('combobox', { name: /owner/i })
    await user.selectOptions(select, 'Alice')

    expect(screen.getByText('Alice task')).toBeInTheDocument()
    expect(screen.queryByText('Bob task')).not.toBeInTheDocument()
    // Bob's heading should be gone
    const headings = screen.getAllByRole('heading', { level: 2 })
    expect(headings.some((h) => h.textContent.includes('Bob'))).toBe(false)
  })

  it('"All owners" shows all groups', async () => {
    const user = userEvent.setup()
    mockFetchGet(
      makeResponse([
        makeItem({ item_id: '1', owner: 'Alice', text: 'Alice task' }),
        makeItem({ item_id: '2', owner: 'Bob', text: 'Bob task' }),
      ])
    )
    render(<App />)
    await screen.findByText('Alice task')

    const select = screen.getByRole('combobox', { name: /owner/i })
    // First select Alice, then reset
    await user.selectOptions(select, 'Alice')
    await user.selectOptions(select, 'all')

    expect(screen.getByText('Alice task')).toBeInTheDocument()
    expect(screen.getByText('Bob task')).toBeInTheDocument()
  })
})

// ── Filter bar: age-bucket filter ────────────────────────────────────────────

describe('age-bucket filter', () => {
  it('deselecting "critical" hides critical items', async () => {
    const user = userEvent.setup()
    mockFetchGet(
      makeResponse([
        makeItem({ item_id: '1', owner: 'Alice', text: 'Normal task', age_bucket: 'fresh' }),
        makeItem({ item_id: '2', owner: 'Alice', text: 'Critical task', age_bucket: 'critical' }),
      ])
    )
    render(<App />)
    await screen.findByText('Normal task')

    const criticalCheckbox = screen.getByRole('checkbox', { name: /critical/i })
    await user.click(criticalCheckbox)

    expect(screen.getByText('Normal task')).toBeInTheDocument()
    expect(screen.queryByText('Critical task')).not.toBeInTheDocument()
  })

  it('reselecting a bucket shows those items again', async () => {
    const user = userEvent.setup()
    mockFetchGet(
      makeResponse([
        makeItem({ item_id: '1', owner: 'Alice', text: 'Stale task', age_bucket: 'stale' }),
      ])
    )
    render(<App />)
    await screen.findByText('Stale task')

    const staleCheckbox = screen.getByRole('checkbox', { name: /stale/i })
    await user.click(staleCheckbox)
    expect(screen.queryByText('Stale task')).not.toBeInTheDocument()

    await user.click(staleCheckbox)
    expect(screen.getByText('Stale task')).toBeInTheDocument()
  })
})

// ── Both filters compose ──────────────────────────────────────────────────────

describe('combined filters', () => {
  it('shows only items matching both owner and age bucket', async () => {
    const user = userEvent.setup()
    mockFetchGet(
      makeResponse([
        makeItem({ item_id: '1', owner: 'Alice', text: 'Alice fresh', age_bucket: 'fresh' }),
        makeItem({ item_id: '2', owner: 'Alice', text: 'Alice critical', age_bucket: 'critical' }),
        makeItem({ item_id: '3', owner: 'Bob', text: 'Bob fresh', age_bucket: 'fresh' }),
      ])
    )
    render(<App />)
    await screen.findByText('Alice fresh')

    // Select Alice
    const select = screen.getByRole('combobox', { name: /owner/i })
    await user.selectOptions(select, 'Alice')

    // Deselect critical
    const criticalCheckbox = screen.getByRole('checkbox', { name: /critical/i })
    await user.click(criticalCheckbox)

    // Only Alice's fresh item should show
    expect(screen.getByText('Alice fresh')).toBeInTheDocument()
    expect(screen.queryByText('Alice critical')).not.toBeInTheDocument()
    expect(screen.queryByText('Bob fresh')).not.toBeInTheDocument()
  })
})

// ── Visible/total count ───────────────────────────────────────────────────────

describe('filter count display', () => {
  it('shows visible/total count when filters are active', async () => {
    const user = userEvent.setup()
    mockFetchGet(
      makeResponse([
        makeItem({ item_id: '1', owner: 'Alice', text: 'Alice task', age_bucket: 'fresh' }),
        makeItem({ item_id: '2', owner: 'Bob', text: 'Bob task', age_bucket: 'fresh' }),
        makeItem({ item_id: '3', owner: 'Bob', text: 'Bob task 2', age_bucket: 'fresh' }),
      ])
    )
    render(<App />)
    await screen.findByText('Alice task')

    const select = screen.getByRole('combobox', { name: /owner/i })
    await user.selectOptions(select, 'Alice')

    expect(screen.getByText(/Showing 1 of 3 items/)).toBeInTheDocument()
  })

  it('does not show count when no filters are active', async () => {
    mockFetchGet(
      makeResponse([
        makeItem({ item_id: '1', owner: 'Alice', text: 'Alice task' }),
      ])
    )
    render(<App />)
    await screen.findByText('Alice task')

    expect(screen.queryByText(/Showing/)).not.toBeInTheDocument()
  })
})

// ── Mark Complete button ──────────────────────────────────────────────────────

describe('Mark Complete button', () => {
  it('is present on each item card', async () => {
    mockFetchGet(
      makeResponse([
        makeItem({ item_id: '1', owner: 'Alice', text: 'Task one' }),
        makeItem({ item_id: '2', owner: 'Alice', text: 'Task two' }),
      ])
    )
    render(<App />)
    await screen.findByText('Task one')

    const buttons = screen.getAllByRole('button', { name: /mark complete/i })
    expect(buttons).toHaveLength(2)
  })

  it('clicking opens the confirmation modal showing the item text', async () => {
    const user = userEvent.setup()
    mockFetchGet(
      makeResponse([makeItem({ item_id: '1', text: 'Fix the pipeline' })])
    )
    render(<App />)
    await screen.findByText('Fix the pipeline')

    const btn = screen.getByRole('button', { name: /mark complete/i })
    await user.click(btn)

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('Mark item complete?')).toBeInTheDocument()
    // text appears in both the card and the modal body
    expect(screen.getAllByText('Fix the pipeline')).toHaveLength(2)
  })

  it('truncates long item text in the modal to ~100 chars', async () => {
    const user = userEvent.setup()
    const longText = 'A'.repeat(120)
    mockFetchGet(makeResponse([makeItem({ item_id: '1', text: longText })]))
    render(<App />)
    // The card text shows full text; modal should show truncated
    await screen.findByRole('button', { name: /mark complete/i })
    await user.click(screen.getByRole('button', { name: /mark complete/i }))

    const dialog = screen.getByRole('dialog')
    // Modal body should have the truncated text (100 chars + ellipsis)
    const modalBody = within(dialog).getByText((content) => content.endsWith('…'))
    expect(modalBody.textContent.length).toBeLessThanOrEqual(102) // 100 chars + '…' (3 bytes but 1 char)
  })
})

// ── Modal: Cancel ────────────────────────────────────────────────────────────

describe('modal Cancel', () => {
  it('closes the modal and item remains in list', async () => {
    const user = userEvent.setup()
    mockFetchGet(makeResponse([makeItem({ item_id: '1', text: 'Fix the pipeline' })]))
    render(<App />)
    await screen.findByText('Fix the pipeline')

    await user.click(screen.getByRole('button', { name: /mark complete/i }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /cancel/i }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByText('Fix the pipeline')).toBeInTheDocument()
  })
})

// ── Modal: Confirm — optimistic removal on success ───────────────────────────

describe('modal Confirm — API success', () => {
  it('removes item optimistically; on API success item stays removed', async () => {
    const user = userEvent.setup()
    mockFetchGetWithPostResult(makeResponse([makeItem({ item_id: '1', text: 'Fix the pipeline' })]), true)
    render(<App />)
    await screen.findByText('Fix the pipeline')

    await user.click(screen.getByRole('button', { name: /mark complete/i }))
    await user.click(screen.getByRole('button', { name: /confirm/i }))

    await waitFor(() => {
      expect(screen.queryByText('Fix the pipeline')).not.toBeInTheDocument()
    })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})

// ── Modal: Confirm — restore on failure ──────────────────────────────────────

describe('modal Confirm — API failure', () => {
  it('restores item to list and shows error toast', async () => {
    const user = userEvent.setup()
    mockFetchGetWithPostResult(
      makeResponse([makeItem({ item_id: '1', text: 'Fix the pipeline' })]),
      false,
      500
    )
    render(<App />)
    await screen.findByText('Fix the pipeline')

    await user.click(screen.getByRole('button', { name: /mark complete/i }))
    await user.click(screen.getByRole('button', { name: /confirm/i }))

    // Item is restored
    await waitFor(() => {
      expect(screen.getByText('Fix the pipeline')).toBeInTheDocument()
    })

    // Toast appears
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Failed to mark complete — please try again'
    )
  })
})

// ── Confirm button disabled while in-flight ───────────────────────────────────

describe('Confirm button loading state', () => {
  it('keeps the modal open with Confirm disabled until the API call settles', async () => {
    const user = userEvent.setup()
    const responseData = makeResponse([makeItem({ item_id: '1', text: 'Fix the pipeline' })])
    const { resolvePost } = mockFetchGetWithPostPending(responseData)

    render(<App />)
    await screen.findByText('Fix the pipeline')

    await user.click(screen.getByRole('button', { name: /mark complete/i }))
    const confirmBtn = screen.getByRole('button', { name: /confirm/i })
    expect(confirmBtn).not.toBeDisabled()

    await user.click(confirmBtn)

    // In flight: modal still open, button disabled, item already removed optimistically
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /saving/i })).toBeDisabled()
    expect(screen.queryByRole('button', { name: /^mark complete$/i })).not.toBeInTheDocument()

    resolvePost({ ok: true, json: () => Promise.resolve({}) })
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
  })

  it('closes the modal after a failed call and restores the item', async () => {
    const user = userEvent.setup()
    const responseData = makeResponse([makeItem({ item_id: '1', text: 'Fix the pipeline' })])
    const { resolvePost } = mockFetchGetWithPostPending(responseData)

    render(<App />)
    await screen.findByText('Fix the pipeline')
    await user.click(screen.getByRole('button', { name: /mark complete/i }))
    await user.click(screen.getByRole('button', { name: /confirm/i }))
    resolvePost({ ok: false, status: 500 })

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
    expect(screen.getByText('Fix the pipeline')).toBeInTheDocument()
  })
})

// ── Restore uses a per-action snapshot, not the mount-time data ──────────────

describe('failure restore after an earlier successful completion', () => {
  it('restores the failed item in place and keeps the earlier completed item removed', async () => {
    const user = userEvent.setup()
    const data = makeResponse([
      makeItem({ item_id: 'a', text: 'Task A' }),
      makeItem({ item_id: 'b', text: 'Task B' }),
      makeItem({ item_id: 'c', text: 'Task C' }),
    ])
    global.fetch = vi.fn().mockImplementation((url, opts) => {
      if (opts && opts.method === 'POST') {
        return url.includes('/b/complete')
          ? Promise.resolve({ ok: false, status: 500 })
          : Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve(data) })
    })

    render(<App />)
    await screen.findByText('Task A')

    // Complete A (succeeds)
    await user.click(screen.getAllByRole('button', { name: /mark complete/i })[0])
    await user.click(screen.getByRole('button', { name: /confirm/i }))
    await waitFor(() => expect(screen.queryByText('Task A')).not.toBeInTheDocument())
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    // Complete B (fails)
    await user.click(screen.getAllByRole('button', { name: /mark complete/i })[0])
    await user.click(screen.getByRole('button', { name: /confirm/i }))

    await waitFor(() => expect(screen.getByText('Task B')).toBeInTheDocument())
    expect(screen.queryByText('Task A')).not.toBeInTheDocument()
    const texts = ['Task B', 'Task C'].map((t) => screen.getByText(t))
    expect(texts[0].compareDocumentPosition(texts[1]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
})
