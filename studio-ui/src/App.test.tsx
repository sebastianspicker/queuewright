import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'
import { exampleProject } from './data'

const storage = vi.hoisted(() => ({
  listDrafts: vi.fn().mockResolvedValue([]),
  loadActiveDraft: vi.fn().mockResolvedValue(undefined),
  loadBlueprint: vi.fn().mockResolvedValue(undefined),
  loadDraft: vi.fn().mockResolvedValue(undefined),
  saveDraft: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('./storage', () => storage)

describe('Studio', () => {
  beforeEach(() => {
    storage.saveDraft.mockClear()
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
  })

  afterEach(() => vi.unstubAllGlobals())

  it('presents the qWright product identity', () => {
    render(<App />)
    expect(screen.getByLabelText('qWright')).toHaveTextContent('qWright')
    expect(screen.getByRole('navigation', { name: 'qWright steps' })).toBeInTheDocument()
    expect(screen.getByRole('complementary', { name: 'Local revision details' })).toBeInTheDocument()
    expect(screen.getByText('Graph ID')).toBeInTheDocument()
  })

  it('edits the real structure while unavailable exports stay disabled', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('button', { name: 'Services' }))
    expect(screen.getByRole('heading', { name: 'Build your service structure' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Add service' }))
    expect(screen.getByDisplayValue('New service')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Review' }))
    expect(screen.getByRole('button', { name: 'Project' })).toBeDisabled()
    expect(screen.getAllByText(/exports stay disabled/i).length).toBeGreaterThan(0)
  })

  it('shows the complete bundled feature catalog', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: 'Policies' }))
    expect(screen.getAllByRole('checkbox')).toHaveLength(18)
    expect(screen.getAllByText('Cross-department handoff').length).toBeGreaterThan(0)
    expect(screen.queryByText('Webhooks')).not.toBeInTheDocument()
  })

  it('validates a direct project before it can replace or persist the active draft', async () => {
    const unsafe = exampleProject()
    unsafe.id = 'unsafe-import'
    unsafe.feature_state.macros.settings = { api_token: 'synthetic-value' }
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.pathname
          : new URL(String((input as Request).url), 'http://127.0.0.1').pathname
      const body = String(
        init?.body
        ?? (typeof Request !== 'undefined' && input instanceof Request
          ? await input.clone().text()
          : ''),
      )
      if (
        path.endsWith('/api/v1/compile-project')
        && (body.includes('api_token') || body.includes('unsafe-import'))
      ) {
        return new Response(JSON.stringify({
          code: 'invalid_project',
          path: 'feature_state.macros.settings.api_token',
          message: 'sensitive setting names are forbidden',
        }), { status: 400, headers: { 'content-type': 'application/json' } })
      }
      throw new Error('offline')
    }))
    const user = userEvent.setup()
    render(<App />)
    const file = new File(
      [JSON.stringify(unsafe)],
      'unsafe.project.json',
      { type: 'application/json' },
    )

    await user.upload(
      screen.getAllByLabelText('Import project or profile bundle')[0],
      file,
    )

    expect(
      await screen.findByText(/sensitive setting names are forbidden/i),
    ).toBeInTheDocument()
    await waitFor(() => {
      expect(storage.saveDraft.mock.calls.every(([project]) =>
        project.id !== 'unsafe-import',
      )).toBe(true)
    })
  })
})
