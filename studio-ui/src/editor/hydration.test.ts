import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  compile: vi.fn(),
  loadActiveDraft: vi.fn(),
  migrateLegacyDrafts: vi.fn(),
}))

vi.mock('../api/client', () => ({ api: { compile: mocks.compile } }))
vi.mock('../persistence/drafts', () => ({
  loadActiveDraft: mocks.loadActiveDraft,
  migrateLegacyDrafts: mocks.migrateLegacyDrafts,
}))

import { staticDemoProject } from '../data'
import { hydrateStudio } from './hydration'
import { shouldScheduleAutomaticCompile } from './effects'
import type { BlueprintCompileResult, StudioProjectV2 } from '../contracts'

function compileResult(project: StudioProjectV2): BlueprintCompileResult {
  return { project, bundle: project.bundle, graph: { nodes: [], graph_hash: 'hydrated' }, plan: { counts: {}, operations: [], plan_hash: 'hydrated', safety: {} }, hashes: {} }
}
import { seedProject, studioReducer, initialState, type Action } from './reducer'

describe('first-run hydration', () => {
  beforeEach(() => {
    mocks.compile.mockReset()
    mocks.loadActiveDraft.mockReset()
    mocks.migrateLegacyDrafts.mockReset()
    mocks.loadActiveDraft.mockResolvedValue(undefined)
    mocks.migrateLegacyDrafts.mockResolvedValue([])
  })

  it('compiles the bundled seed and hydrates the server-canonical V2 result', async () => {
    const canonical = { ...staticDemoProject(), id: 'canonical-first-run' }
    mocks.compile.mockResolvedValue(compileResult(canonical))
    const dispatch = vi.fn<(action: Action) => void>()

    await hydrateStudio(dispatch, () => false)

    expect(mocks.compile).toHaveBeenCalledTimes(1)
    expect(mocks.compile).toHaveBeenCalledWith(seedProject)
    expect(dispatch).toHaveBeenCalledWith({ type: 'hydrate', active: canonical, projects: [], result: compileResult(canonical) })
    expect(dispatch).not.toHaveBeenCalledWith(expect.objectContaining({ type: 'import:error' }))
    const hydrated = dispatch.mock.calls.reduce((state, [action]) => studioReducer(state, action), initialState)
    expect(hydrated.result).toEqual(compileResult(canonical))
    expect(hydrated.dirty).toBe(false)
    expect(shouldScheduleAutomaticCompile({ ...hydrated, demoMode: false })).toBe(false)
  })

  it('reports compiler unavailability only when canonicalizing the seed fails', async () => {
    mocks.compile.mockRejectedValue(new Error('loopback offline'))
    const dispatch = vi.fn<(action: Action) => void>()

    await hydrateStudio(dispatch, () => false)

    expect(mocks.compile).toHaveBeenCalledWith(seedProject)
    expect(dispatch).toHaveBeenNthCalledWith(1, { type: 'hydrate', active: seedProject, projects: [] })
    const hydrated = dispatch.mock.calls.reduce((state, [action]) => studioReducer(state, action), initialState)
    expect(hydrated.dirty).toBe(true)
    expect(hydrated.result).toBeUndefined()
    expect(dispatch).toHaveBeenNthCalledWith(2, {
      type: 'import:error',
      message: 'The loopback compiler is unavailable; the bundled project is open but exports stay disabled.',
    })
  })
})

describe('active-first background hydration', () => {
  beforeEach(() => {
    mocks.compile.mockReset()
    mocks.loadActiveDraft.mockReset()
    mocks.migrateLegacyDrafts.mockReset()
  })

  it('opens a valid active project before unrelated migrations finish or fail', async () => {
    const active = staticDemoProject()
    mocks.loadActiveDraft.mockResolvedValue(active)
    mocks.compile.mockResolvedValue(compileResult(active))
    let rejectMigration!: (error: Error) => void
    mocks.migrateLegacyDrafts.mockReturnValue(new Promise((_, reject) => { rejectMigration = reject }))
    const dispatch = vi.fn<(action: Action) => void>()
    const hydration = hydrateStudio(dispatch, () => false)
    await vi.waitFor(() => expect(dispatch).toHaveBeenCalledWith({ type: 'hydrate', active, projects: [], result: compileResult(active) }))
    rejectMigration(new Error('legacy store failure'))
    await hydration
    expect(dispatch.mock.calls.filter(([action]) => action.type === 'hydrate')).toHaveLength(1)
    expect(dispatch).toHaveBeenLastCalledWith(expect.objectContaining({ type: 'import:error' }))
  })

  it('does not dispatch or launch migrations after cancellation during active compilation', async () => {
    const active = staticDemoProject()
    mocks.loadActiveDraft.mockResolvedValue(active)
    let finish!: (result: { project: typeof active }) => void
    mocks.compile.mockReturnValue(new Promise((resolve) => { finish = resolve }))
    let cancelled = false
    const dispatch = vi.fn<(action: Action) => void>()
    const hydration = hydrateStudio(dispatch, () => cancelled)
    await vi.waitFor(() => expect(mocks.compile).toHaveBeenCalledTimes(1))
    cancelled = true
    finish({ project: active })
    await hydration
    expect(dispatch).not.toHaveBeenCalled()
    expect(mocks.migrateLegacyDrafts).not.toHaveBeenCalled()
  })

  it('gives recovery seeds a different key so autosave cannot overwrite quarantined active data', async () => {
    mocks.loadActiveDraft.mockResolvedValue({ project_schema_version: '2.0', id: seedProject.id })
    mocks.compile.mockRejectedValue(new Error('invalid stored data'))
    mocks.migrateLegacyDrafts.mockResolvedValue([])
    const dispatch = vi.fn<(action: Action) => void>()
    await hydrateStudio(dispatch, () => false)
    const action = dispatch.mock.calls[0]?.[0]
    expect(action?.type).toBe('hydrate')
    if (action?.type === 'hydrate') {
      expect(action.active?.id).not.toBe(seedProject.id)
      expect(action.active?.id).toMatch(/^[a-z][a-z0-9_-]*$/)
    }
  })
})
