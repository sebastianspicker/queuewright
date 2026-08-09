import { describe, expect, it } from 'vitest'
import { exampleProject } from './data'
import { initialState, studioReducer } from './studio-state/model'

describe('studioReducer', () => {
  it('ignores compile and storage results from stale revisions', () => {
    const state = { ...initialState, revision: 4 }

    expect(studioReducer(state, {
      type: 'compile:error',
      message: 'stale',
      revision: 3,
    })).toBe(state)
    expect(studioReducer(state, { type: 'storage:success', revision: 3 })).toBe(state)
  })

  it('clears derived results when replacing the active project', () => {
    const project = exampleProject('replacement')
    const state = {
      ...initialState,
      result: { marker: true } as never,
      blueprintResult: { marker: true } as never,
      compileError: 'old compile error',
      importError: 'old import error',
    }

    const next = studioReducer(state, {
      type: 'project:replace',
      project,
      selectedGroup: 'service_general',
    })

    expect(next.project).toBe(project)
    expect(next.revision).toBe(state.revision + 1)
    expect(next.selectedGroup).toBe('service_general')
    expect(next.result).toBeUndefined()
    expect(next.blueprintResult).toBeUndefined()
    expect(next.compileError).toBeUndefined()
    expect(next.importError).toBeUndefined()
    expect(next.storageStatus).toBe('pending')
  })
})
