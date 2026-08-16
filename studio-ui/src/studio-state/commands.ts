import { useCallback, type Dispatch } from 'react'
import { api } from '../api'
import { blankProject, exampleProject } from '../data'
import { importFilesIntoStudio } from '../studio-import'
import { loadBlueprint, loadDraft } from '../storage'
import type { StudioProject, StudioProjectV2 } from '../types'
import { compileMessage, rebaseBlueprint } from './blueprint'
import type { CompileRunner } from './effects'
import { staticDemo, type Action, type State } from './model'

export interface StudioCommands {
  updateProject(project: StudioProject, selectedGroup?: string): void
  updateBlueprint(project: StudioProjectV2): void
  createNew(kind: 'blank' | 'example'): Promise<void>
  openProject(id: string): Promise<void>
  importFiles(files: FileList | File[]): Promise<void>
  validateNow(): void
}

export function useStudioCommands(
  state: State,
  dispatch: Dispatch<Action>,
  runCompile: CompileRunner,
): StudioCommands {
  const updateProject = useCallback((project: StudioProject, selectedGroup?: string) => {
    dispatch({ type: 'project:replace', project, selectedGroup })
  }, [dispatch])

  const updateBlueprint = useCallback((blueprint: StudioProjectV2) => {
    dispatch({ type: 'blueprint:replace', blueprint })
  }, [dispatch])

  const createNew = useCallback(async (kind: 'blank' | 'example') => {
    const source = kind === 'blank'
      ? blankProject()
      : exampleProject(`university-${Date.now().toString(36)}`)
    if (staticDemo) {
      dispatch({
        type: 'project:replace',
        project: source,
        selectedGroup: kind === 'blank' ? 'service_general' : 'student_services',
      })
      return
    }
    try {
      let project = await api.importBundle(source.profile, source.manifest)
      project = { ...project, id: source.id, name: source.name }
      project = (await api.compile(project)).project
      const blueprint = await api.migrateProject(project)
      dispatch({
        type: 'project:replace',
        project,
        blueprint,
        selectedGroup: kind === 'blank' ? 'service_general' : 'student_services',
      })
    } catch (error) {
      dispatch({ type: 'import:error', message: compileMessage(error) })
    }
  }, [dispatch])

  const openProject = useCallback(async (id: string) => {
    if (staticDemo) return
    const project = await loadDraft(id)
    if (!project) return
    try {
      const result = await api.compile(project)
      const storedBlueprint = await loadBlueprint(id)
      const migrated = await api.migrateProject(result.project)
      const blueprint = rebaseBlueprint(migrated, storedBlueprint)
      await api.compileBlueprint(blueprint)
      dispatch({ type: 'project:replace', project: result.project, blueprint })
    } catch (error) {
      dispatch({
        type: 'import:error',
        message: `Stored project quarantined: ${compileMessage(error)}`,
      })
    }
  }, [dispatch])

  const importFiles = useCallback(async (input: FileList | File[]) => {
    if (staticDemo) {
      dispatch({
        type: 'import:error',
        message: 'Simulated action only. Import is available in the local Studio.',
      })
      return
    }
    dispatch({ type: 'import:error', message: undefined })
    const message = await importFilesIntoStudio(input, ([project, blueprint]) => {
      dispatch({ type: 'project:replace', project, blueprint })
    })
    if (message) dispatch({ type: 'import:error', message })
  }, [dispatch])

  const validateNow = useCallback(() => {
    if (staticDemo) {
      dispatch({
        type: 'compile:error',
        message: 'Simulated action only. Authoritative validation requires the local Studio service.',
        revision: state.revision,
      })
      return
    }
    runCompile(state.project, state.blueprint, state.revision)
  }, [dispatch, runCompile, state.project, state.blueprint, state.revision])

  return { updateProject, updateBlueprint, createNew, openProject, importFiles, validateNow }
}
