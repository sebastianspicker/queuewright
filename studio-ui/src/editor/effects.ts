import { useCallback, useEffect, useRef, type Dispatch } from 'react'
import { api } from '../api/client'
import { saveDraft } from '../persistence/drafts'
import type { StudioProjectV2 } from '../contracts'
import { hydrateStudio } from './hydration'
import { staticDemo, type Action, type State } from './reducer'

export const LOCAL_SERVICE_UNREACHABLE = 'Local service unreachable'

export type CompileRunner = (project: StudioProjectV2, revision: number) => void
export function compileMessage(error: unknown): string {
  if (error instanceof DOMException && error.name === 'AbortError') return ''
  // A TypeError here means the loopback API is not listening.
  if (error instanceof TypeError) return LOCAL_SERVICE_UNREACHABLE
  if (error instanceof Error) return error.message
  return 'Loopback compiler unavailable. Exports stay disabled.'
}

export function useCompileRunner(dispatch: Dispatch<Action>): CompileRunner {
  const request = useRef<AbortController | undefined>(undefined)
  useEffect(() => () => request.current?.abort(), [])
  return useCallback((project, revision) => {
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    dispatch({ type: 'compile:start', revision })
    void api.compile(project, controller.signal)
      .then((result) => { if (request.current === controller && !controller.signal.aborted) dispatch({ type: 'compile:success', result, revision }) })
      .catch((error: unknown) => { const message = compileMessage(error); if (request.current === controller && !controller.signal.aborted && message) dispatch({ type: 'compile:error', message, revision }) })
  }, [dispatch])
}

function useHydration(dispatch: Dispatch<Action>): void {
  useEffect(() => { if (staticDemo) return; let cancelled = false; void hydrateStudio(dispatch, () => cancelled); return () => { cancelled = true } }, [dispatch])
}
function useCatalog(dispatch: Dispatch<Action>): void {
  useEffect(() => {
    if (staticDemo) return
    const controller = new AbortController()
    void api.loadCatalog(controller.signal).then((catalog) => dispatch({ type: 'catalog', catalog })).catch((error: unknown) => {
      if (!(error instanceof DOMException && error.name === 'AbortError')) dispatch({ type: 'catalog:error', message: 'Local catalog unavailable. Using the bundled catalog.' })
    })
    return () => controller.abort()
  }, [dispatch])
}
function usePersistence(state: State, dispatch: Dispatch<Action>): void {
  useEffect(() => {
    if (staticDemo || !state.hydrated) return
    const { project, revision } = state
    const timer = window.setTimeout(() => { dispatch({ type: 'storage:start', revision }); void saveDraft(project).then(() => dispatch({ type: 'storage:success', revision })).catch(() => dispatch({ type: 'storage:error', revision })) }, 180)
    return () => window.clearTimeout(timer)
  }, [dispatch, state.hydrated, state.project, state.revision])
}

export function shouldScheduleAutomaticCompile({
  demoMode,
  hydrated,
  dirty,
  compiling,
  compileError,
}: Pick<State, 'hydrated' | 'dirty' | 'compiling' | 'compileError'> & { demoMode: boolean }): boolean {
  return !demoMode && hydrated && dirty && !compiling && !compileError
}

function useAutomaticCompile(state: State, runCompile: CompileRunner): void {
  useEffect(() => {
    if (!shouldScheduleAutomaticCompile({
      demoMode: staticDemo,
      hydrated: state.hydrated,
      dirty: state.dirty,
      compiling: state.compiling,
      compileError: state.compileError,
    })) return
    const { project, revision } = state
    const timer = window.setTimeout(() => runCompile(project, revision), 450)
    return () => window.clearTimeout(timer)
  }, [runCompile, state.compiling, state.dirty, state.hydrated, state.project, state.revision])
}
export function useStudioEffects(state: State, dispatch: Dispatch<Action>, runCompile: CompileRunner): void { useHydration(dispatch); useCatalog(dispatch); usePersistence(state, dispatch); useAutomaticCompile(state, runCompile) }
