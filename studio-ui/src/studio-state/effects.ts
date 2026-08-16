import { useCallback, useEffect, useRef, type Dispatch } from 'react'
import { api } from '../api'
import { saveDraft } from '../storage'
import type { StudioProject, StudioProjectV2 } from '../types'
import { compileMessage, rebaseBlueprint } from './blueprint'
import { hydrateStudio } from './hydration'
import { staticDemo, type Action, type State } from './model'

export type CompileRunner = (
  project: StudioProject,
  blueprint: StudioProjectV2 | undefined,
  revision: number,
) => void

export function useCompileRunner(dispatch: Dispatch<Action>): CompileRunner {
  const request = useRef<AbortController | undefined>(undefined)
  useEffect(() => () => request.current?.abort(), [])
  return useCallback((project, blueprint, revision) => {
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    dispatch({ type: 'compile:start', revision })
    void api.compile(project, controller.signal)
      .then(async (result) => {
        const migrated = await api.migrateProject(result.project, controller.signal)
        const candidate = rebaseBlueprint(migrated, blueprint)
        const blueprintResult = await api.compileBlueprint(candidate, controller.signal)
        dispatch({ type: 'compile:success', result, blueprintResult, revision })
      })
      .catch((error: unknown) => {
        const message = compileMessage(error)
        if (message) dispatch({ type: 'compile:error', message, revision })
      })
  }, [dispatch])
}

function useHydration(dispatch: Dispatch<Action>): void {
  useEffect(() => {
    if (staticDemo) return
    let cancelled = false
    void hydrateStudio(dispatch, () => cancelled)
    return () => { cancelled = true }
  }, [dispatch])
}

function useCatalog(dispatch: Dispatch<Action>): void {
  useEffect(() => {
    if (staticDemo) return
    const controller = new AbortController()
    void api.loadCatalog(controller.signal)
      .then((catalog) => { dispatch({ type: 'catalog', catalog }) })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          dispatch({
            type: 'catalog:error',
            message: 'Local catalog unavailable. Using the bundled catalog.',
          })
        }
      })
    return () => controller.abort()
  }, [dispatch])
}

function usePersistence(state: State, dispatch: Dispatch<Action>): void {
  useEffect(() => {
    if (staticDemo || !state.hydrated) return
    const { project, blueprint, revision } = state
    const timer = window.setTimeout(() => {
      dispatch({ type: 'storage:start', revision })
      void saveDraft(project, blueprint)
        .then(() => { dispatch({ type: 'storage:success', revision }) })
        .catch(() => { dispatch({ type: 'storage:error', revision }) })
    }, 180)
    return () => window.clearTimeout(timer)
  }, [dispatch, state.hydrated, state.project, state.blueprint, state.revision])
}

function useAutomaticCompile(state: State, runCompile: CompileRunner): void {
  useEffect(() => {
    if (staticDemo || !state.hydrated) return
    const { project, blueprint, revision } = state
    const timer = window.setTimeout(
      () => runCompile(project, blueprint, revision),
      450,
    )
    return () => window.clearTimeout(timer)
  }, [runCompile, state.hydrated, state.project, state.blueprint, state.revision])
}

export function useStudioEffects(
  state: State,
  dispatch: Dispatch<Action>,
  runCompile: CompileRunner,
): void {
  useHydration(dispatch)
  useCatalog(dispatch)
  usePersistence(state, dispatch)
  useAutomaticCompile(state, runCompile)
}
