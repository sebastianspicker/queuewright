import { describe, expect, it, vi } from 'vitest'
import { staticDemoProject } from '../data'
import { createProjectCommandRunner } from './commands'

describe('static demo project creation', () => {
  it('uses a schema-realistic backend-generated V2 fixture without the compile API', () => {
    const project = staticDemoProject('blank')
    expect(project).toMatchObject({
      project_schema_version: '2.0',
      workbook: {
        services: expect.arrayContaining([expect.objectContaining({ key: 'service_general' })]),
        policies: expect.objectContaining({ feature_selection: expect.any(Object) }),
        uat: expect.objectContaining({ scenarios: expect.any(Array) }),
      },
    })
    expect(project.workbook.capability_decisions['service-topology']).toMatchObject({
      delivery: expect.any(String), risk: expect.any(String), dependencies: expect.any(Array),
    })
  })
})


import { initialState, studioReducer } from './reducer'
import type { Action, State } from './reducer'
import type { StudioProjectV2 } from '../contracts'

function deferredProject() {
  let resolve!: (value: { project: StudioProjectV2 }) => void
  let reject!: (error: Error) => void
  const promise = new Promise<{ project: StudioProjectV2 }>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
function commandHarness() {
  let state: State = initialState
  const dispatch = vi.fn((action: Action) => { state = studioReducer(state, action) })
  return { dispatch, requests: createProjectCommandRunner(dispatch), state: () => state }
}

describe('asynchronous project command ordering', () => {
  it('keeps the latest selection when an earlier open finishes later despite cancellation', async () => {
    const harness = commandHarness()
    const first = deferredProject()
    const second = deferredProject()
    let firstSignal!: AbortSignal
    const firstRun = harness.requests.run((signal) => { firstSignal = signal; return first.promise })
    const secondRun = harness.requests.run(() => second.promise)
    const latest = { ...initialState.project, id: 'latest-selection' }
    second.resolve({ project: latest })
    await secondRun
    first.resolve({ project: { ...initialState.project, id: 'old-selection' } })
    await firstRun
    expect(firstSignal.aborted).toBe(true)
    expect(harness.state().project).toBe(latest)
  })

  it('rejects completion after a direct edit even without an abort signal being honored', async () => {
    const harness = commandHarness()
    const request = deferredProject()
    const running = harness.requests.run(() => request.promise)
    harness.dispatch({ type: 'project:edit', edit: (project) => ({ ...project, name: 'New edit' }) })
    request.resolve({ project: { ...initialState.project, name: 'Old command' } })
    await running
    expect(harness.state().project.name).toBe('New edit')
  })

  it('does not surface errors from commands superseded by newer edits', async () => {
    const harness = commandHarness()
    const request = deferredProject()
    const running = harness.requests.run(() => request.promise, 'Stored project quarantined: ')
    harness.dispatch({ type: 'project:replace', project: { ...initialState.project, name: 'User edit' } })
    request.reject(new Error('old failure'))
    await running
    expect(harness.state().importError).toBeUndefined()
  })

  it('cancels pending import/create work on teardown without dispatching its result', async () => {
    const harness = commandHarness()
    const request = deferredProject()
    const running = harness.requests.run(() => request.promise)
    harness.requests.cancel()
    harness.dispatch.mockClear()
    request.resolve({ project: initialState.project })
    await running
    expect(harness.dispatch).not.toHaveBeenCalled()
  })
})
