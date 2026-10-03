import { useCallback, useEffect, useMemo, type Dispatch } from 'react'
import { api } from '../api/client'
import { blankBundle, exampleBundle, staticDemoProject } from '../data'
import { loadDraft } from '../persistence/drafts'
import { isV2Project } from '../contracts/runtime'
import type { FeatureId, StepId, StudioProjectV2 } from '../contracts'
import { importFilesIntoStudio } from './import'
import type { CompileRunner } from './effects'
import { compileMessage } from './effects'
import { staticDemo, type Action, type State } from './reducer'

export interface StudioCommands {
  editProject(edit: (project: StudioProjectV2) => StudioProjectV2): void
  updateProject(project: StudioProjectV2, selectedGroup?: string): void
  createNew(kind: 'blank' | 'example'): Promise<void>
  openProject(id: string): Promise<void>
  importFiles(files: FileList | File[]): Promise<void>
  validateNow(): void
  goToStep(step: StepId): void
  selectGroup(id?: string): void
  selectFeature(id?: FeatureId): void
}

interface CommandResult { project: StudioProjectV2; selectedGroup?: string }

/** Owns the lifetime of project-changing requests; the reducer also rejects
 * completions superseded by direct edits or a newer request. */
export function createProjectCommandRunner(dispatch: Dispatch<Action>) {
  let generation = 0
  let current: AbortController | undefined
  const cancel = () => { current?.abort(); current = undefined }
  return {
    cancel,
    async run(task: (signal: AbortSignal) => Promise<CommandResult>, errorPrefix = ''): Promise<void> {
      cancel()
      const controller = new AbortController()
      current = controller
      const id = ++generation
      dispatch({ type: 'command:start', id })
      try {
        const result = await task(controller.signal)
        if (current === controller && !controller.signal.aborted) dispatch({ type: 'command:success', id, ...result })
      } catch (error) {
        if (current === controller && !controller.signal.aborted) dispatch({ type: 'command:error', id, message: `${errorPrefix}${compileMessage(error)}` })
      } finally { if (current === controller) current = undefined }
    },
  }
}

export function useStudioCommands(state: State, dispatch: Dispatch<Action>, runCompile: CompileRunner): StudioCommands {
  const requests = useMemo(() => createProjectCommandRunner(dispatch), [dispatch])
  useEffect(() => requests.cancel, [requests])
  const editProject = useCallback((edit: (project: StudioProjectV2) => StudioProjectV2) => { requests.cancel(); dispatch({ type: 'project:edit', edit }) }, [dispatch, requests])
  const updateProject = useCallback((project: StudioProjectV2, selectedGroup?: string) => {
    requests.cancel()
    dispatch({ type: 'project:replace', project, selectedGroup })
  }, [dispatch, requests])
  const createNew = useCallback(async (kind: 'blank' | 'example') => {
    if (staticDemo) {
      dispatch({ type: 'project:replace', project: staticDemoProject(kind), selectedGroup: kind === 'blank' ? 'service_general' : 'student_services' })
      return
    }
    const source = kind === 'blank' ? blankBundle() : exampleBundle()
    await requests.run(async (signal) => {
      const result = await api.compile(source, signal)
      return { project: result.project, selectedGroup: kind === 'blank' ? 'service_general' : 'student_services' }
    })
  }, [dispatch, requests])
  const openProject = useCallback(async (id: string) => {
    if (staticDemo) return
    await requests.run(async (signal) => {
      const draft = await loadDraft(id)
      signal.throwIfAborted()
      if (!isV2Project(draft)) throw new Error('Stored project is not a canonical V2 record.')
      const result = await api.compile(draft, signal)
      return { project: result.project }
    }, 'Stored project quarantined: ')
  }, [requests])
  const importFiles = useCallback(async (input: FileList | File[]) => {
    if (staticDemo) { dispatch({ type: 'import:error', message: 'Simulated action only. Import is available in the local Studio.' }); return }
    dispatch({ type: 'import:error', message: undefined })
    await requests.run(async () => ({ project: await importFilesIntoStudio(input) }))
  }, [dispatch, requests])
  const validateNow = useCallback(() => {
    if (staticDemo) { dispatch({ type: 'compile:error', message: 'Simulated action only. Authoritative validation requires the local Studio service.', revision: state.revision }); return }
    runCompile(state.project, state.revision)
  }, [dispatch, runCompile, state.project, state.revision])
  const goToStep = useCallback((step: StepId) => dispatch({ type: 'step', step }), [dispatch])
  const selectGroup = useCallback((id?: string) => dispatch({ type: 'group:select', id }), [dispatch])
  const selectFeature = useCallback((id?: FeatureId) => dispatch({ type: 'feature:select', id }), [dispatch])
  return { editProject, updateProject, createNew, openProject, importFiles, validateNow, goToStep, selectGroup, selectFeature }
}
