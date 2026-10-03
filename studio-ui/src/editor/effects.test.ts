import { describe, expect, it } from 'vitest'
import { staticDemoProject } from '../data'
import { shouldScheduleAutomaticCompile } from './effects'
import { initialState, studioReducer } from './reducer'

const compileResult = {
  project: staticDemoProject(),
  bundle: staticDemoProject().bundle,
  plan: { counts: {}, operations: [], plan_hash: 'current', safety: {} },
  graph: { nodes: [], graph_hash: 'current' },
  hashes: {},
}

describe('automatic compile scheduling', () => {
  it('requires a hydrated, dirty, idle normal-mode draft', () => {
    expect(shouldScheduleAutomaticCompile({ demoMode: false, hydrated: true, dirty: true, compiling: false, compileError: undefined })).toBe(true)
    expect(shouldScheduleAutomaticCompile({ demoMode: true, hydrated: true, dirty: true, compiling: false, compileError: undefined })).toBe(false)
    expect(shouldScheduleAutomaticCompile({ demoMode: false, hydrated: false, dirty: true, compiling: false, compileError: undefined })).toBe(false)
    expect(shouldScheduleAutomaticCompile({ demoMode: false, hydrated: true, dirty: false, compiling: false, compileError: undefined })).toBe(false)
    expect(shouldScheduleAutomaticCompile({ demoMode: false, hydrated: true, dirty: true, compiling: true, compileError: undefined })).toBe(false)
    expect(shouldScheduleAutomaticCompile({ demoMode: false, hydrated: true, dirty: true, compiling: false, compileError: 'invalid draft' })).toBe(false)
  })

  it('stops after success and becomes eligible once a later edit advances the revision', () => {
    const pending = { ...initialState, hydrated: true, dirty: true, compiling: true, revision: 4 }
    const successful = studioReducer(pending, { type: 'compile:success', result: compileResult, revision: 4 })
    expect(successful.dirty).toBe(false)
    expect(shouldScheduleAutomaticCompile({ demoMode: false, ...successful })).toBe(false)

    const edited = studioReducer(successful, { type: 'project:replace', project: staticDemoProject() })
    expect(edited.revision).toBe(5)
    expect(edited.dirty).toBe(true)
    expect(shouldScheduleAutomaticCompile({ demoMode: false, ...edited })).toBe(true)
  })

  it('does not retry a failed revision automatically but allows a later edit', () => {
    const pending = { ...initialState, hydrated: true, dirty: true, compiling: true, revision: 9 }
    const failed = studioReducer(pending, { type: 'compile:error', message: 'invalid draft', revision: 9 })
    expect(failed).toMatchObject({ dirty: true, compiling: false, compileError: 'invalid draft' })
    expect(shouldScheduleAutomaticCompile({ demoMode: false, ...failed })).toBe(false)

    const edited = studioReducer(failed, { type: 'project:replace', project: staticDemoProject() })
    expect(edited).toMatchObject({ revision: 10, dirty: true, compileError: undefined })
    expect(shouldScheduleAutomaticCompile({ demoMode: false, ...edited })).toBe(true)
  })
})
