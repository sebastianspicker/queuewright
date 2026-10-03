import { describe, expect, it } from 'vitest'
import { initialState, studioReducer } from './reducer'

describe('studioReducer', () => {
  it('ignores stale compile results', () => {
    const state = { ...initialState, revision: 2, compiling: true }
    const stale = studioReducer(state, { type: 'compile:success', revision: 1, result: { project: initialState.project, bundle: initialState.project.bundle, plan: { counts: {}, operations: [], plan_hash: 'old', safety: {} }, graph: { nodes: [], graph_hash: 'old' }, hashes: {} } })
    expect(stale).toBe(state)
  })
})

it('restarts compilation after an edit during an in-flight request', () => {
  const busy = studioReducer(initialState, { type: 'compile:start', revision: initialState.revision })
  const edited = studioReducer(busy, { type: 'project:replace', project: { ...busy.project, name: 'Edited while compiling' } })
  expect(edited.compiling).toBe(false)
  expect(edited.dirty).toBe(true)
  const stale = studioReducer(edited, { type: 'compile:error', revision: busy.revision, message: 'old failure' })
  expect(stale).toBe(edited)
})

it('merges a delayed project library without replacing an active edit', () => {
  const edited = studioReducer(initialState, { type: 'project:replace', project: { ...initialState.project, name: 'New local name' } })
  const loaded = studioReducer(edited, { type: 'projects:loaded', projects: [initialState.project] })
  expect(loaded.project).toBe(edited.project)
  expect(loaded.projects.find((project) => project.id === edited.project.id)?.name).toBe('New local name')
})


it('does not let delayed startup hydration replace an early user edit', () => {
  const edited = studioReducer(initialState, { type: 'project:replace', project: { ...initialState.project, name: 'Early edit' } })
  const hydrated = studioReducer(edited, { type: 'hydrate', active: initialState.project, projects: [] })
  expect(hydrated.project).toBe(edited.project)
  expect(hydrated.hydrated).toBe(true)
  expect(hydrated.dirty).toBe(true)
})
