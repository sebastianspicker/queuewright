import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  type Dispatch,
  type ReactNode,
} from 'react'
import { api, StudioApiError } from './api'
import { blankProject, bundledCatalog, exampleProject } from './data'
import { importFilesIntoStudio } from './studio-import'
import {
  listDrafts,
  loadActiveDraft,
  loadBlueprint,
  loadDraft,
  saveDraft,
} from './storage'
import type {
  BlueprintCompileResult,
  CompileResult,
  FeatureDefinition,
  FeatureId,
  StepId,
  StudioProject,
  StudioProjectV2,
} from './types'

type Action =
  | {
      type: 'hydrate'
      active?: StudioProject
      blueprint?: StudioProjectV2
      projects: StudioProject[]
    }
  | {
      type: 'project:replace'
      project: StudioProject
      blueprint?: StudioProjectV2
      selectedGroup?: string
    }
  | { type: 'blueprint:replace'; blueprint: StudioProjectV2 }
  | { type: 'step'; step: StepId }
  | { type: 'group:select'; id?: string }
  | { type: 'feature:select'; id?: FeatureId }
  | { type: 'catalog'; catalog: FeatureDefinition[] }
  | { type: 'catalog:error'; message: string }
  | { type: 'compile:start'; revision: number }
  | {
      type: 'compile:success'
      result: CompileResult
      blueprintResult: BlueprintCompileResult
      revision: number
    }
  | { type: 'compile:error'; message: string; revision: number }
  | { type: 'import:error'; message?: string }
  | { type: 'storage:start'; revision: number }
  | { type: 'storage:success'; revision: number }
  | { type: 'storage:error'; revision: number }

interface State {
  project: StudioProject
  projects: StudioProject[]
  catalog: FeatureDefinition[]
  step: StepId
  selectedGroup?: string
  selectedFeature?: FeatureId
  hydrated: boolean
  revision: number
  dirty: boolean
  compiling: boolean
  result?: CompileResult
  blueprint?: StudioProjectV2
  blueprintResult?: BlueprintCompileResult
  compileError?: string
  catalogError?: string
  importError?: string
  storageStatus: 'loading' | 'pending' | 'saving' | 'saved' | 'error'
}

const seed = exampleProject()
const initial: State = {
  project: seed,
  projects: [],
  catalog: bundledCatalog,
  step: 'start',
  selectedGroup: 'student_services',
  selectedFeature: 'cross_department_handoff',
  hydrated: false,
  revision: 0,
  dirty: true,
  compiling: false,
  storageStatus: 'loading',
}

function upsert(
  projects: StudioProject[],
  project: StudioProject,
): StudioProject[] {
  return [project, ...projects.filter((item) => item.id !== project.id)]
    .sort((left, right) => left.name.localeCompare(right.name))
}

export function studioReducer(state: State, action: Action): State {
  switch (action.type) {
    case 'hydrate': {
      const project = action.active ?? state.project
      return {
        ...state,
        project,
        blueprint: action.blueprint,
        projects: upsert(action.projects, project),
        hydrated: true,
        revision: state.revision + 1,
        dirty: true,
        storageStatus: 'saved',
      }
    }
    case 'project:replace':
      return {
        ...state,
        project: action.project,
        projects: upsert(state.projects, action.project),
        selectedGroup: action.selectedGroup ?? state.selectedGroup,
        revision: state.revision + 1,
        dirty: true,
        result: undefined,
        blueprint: action.blueprint
          ?? (state.blueprint?.id === action.project.id
            ? state.blueprint
            : undefined),
        blueprintResult: undefined,
        compileError: undefined,
        importError: undefined,
        storageStatus: 'pending',
      }
    case 'blueprint:replace':
      return {
        ...state,
        blueprint: action.blueprint,
        revision: state.revision + 1,
        dirty: true,
        result: undefined,
        blueprintResult: undefined,
        compileError: undefined,
        storageStatus: 'pending',
      }
    case 'step':
      return { ...state, step: action.step }
    case 'group:select':
      return { ...state, selectedGroup: action.id }
    case 'feature:select':
      return { ...state, selectedFeature: action.id }
    case 'catalog':
      return { ...state, catalog: action.catalog, catalogError: undefined }
    case 'catalog:error':
      return { ...state, catalogError: action.message }
    case 'compile:start':
      return action.revision === state.revision
        ? { ...state, compiling: true, compileError: undefined }
        : state
    case 'compile:success':
      return action.revision === state.revision
        ? {
            ...state,
            compiling: false,
            dirty: false,
            result: action.result,
            blueprint: action.blueprintResult.project,
            blueprintResult: action.blueprintResult,
            compileError: undefined,
          }
        : state
    case 'compile:error':
      return action.revision === state.revision
        ? {
            ...state,
            compiling: false,
            dirty: true,
            result: undefined,
            blueprintResult: undefined,
            compileError: action.message,
          }
        : state
    case 'import:error':
      return { ...state, importError: action.message }
    case 'storage:start':
      return action.revision === state.revision
        ? { ...state, storageStatus: 'saving' }
        : state
    case 'storage:success':
      return action.revision === state.revision
        ? { ...state, storageStatus: 'saved' }
        : state
    case 'storage:error':
      return action.revision === state.revision
        ? { ...state, storageStatus: 'error' }
        : state
  }
}

type SyncCallback<Arguments extends unknown[] = []> = (..._args: Arguments) => void
type AsyncCallback<Arguments extends unknown[]> = (..._args: Arguments) => Promise<void>

interface StudioContextValue extends State {
  dispatch: Dispatch<Action>
  updateProject: SyncCallback<[StudioProject, string?]>
  updateBlueprint: SyncCallback<[StudioProjectV2]>
  createNew: AsyncCallback<['blank' | 'example']>
  openProject: AsyncCallback<[string]>
  importFiles: AsyncCallback<[FileList | File[]]>
  validateNow: SyncCallback
}

const StudioContext = createContext<StudioContextValue | undefined>(undefined)

function compileMessage(error: unknown): string {
  if (error instanceof DOMException && error.name === 'AbortError') return ''
  if (error instanceof StudioApiError) {
    return `${error.path}: ${error.message}`
  }
  return 'Loopback compiler unavailable. Exports stay disabled.'
}


function rebaseBlueprint(
  migrated: StudioProjectV2,
  previous?: StudioProjectV2,
): StudioProjectV2 {
  if (!previous || previous.id !== migrated.id) return migrated
  const capability_decisions = Object.fromEntries(
    Object.entries(migrated.workbook.capability_decisions).map(
      ([id, pinned]) => {
        const editable = Object.entries(previous.workbook.capability_decisions).find(
          ([candidate]) => candidate === id,
        )?.[1]
        return [
          id,
          editable
            ? {
                ...pinned,
                enabled: editable.enabled,
                completion: editable.completion,
              }
            : pinned,
        ]
      },
    ),
  )
  return {
    ...migrated,
    workbook: {
      ...migrated.workbook,
      organization: previous.workbook.organization,
      capability_decisions,
    },
    extensions: previous.extensions,
  }
}

async function validateStoredProject(project?: StudioProject): Promise<StudioProject | undefined> {
  if (!project) return undefined
  try {
    return (await api.compile(project)).project
  } catch {
    return undefined
  }
}

function bundledProject(): Promise<StudioProject> {
  return api.importBundle(seed.profile, seed.manifest).catch(() => seed)
}

async function restoreBlueprint(project: StudioProject): Promise<StudioProjectV2 | undefined> {
  const stored = await loadBlueprint(project.id)
  if (!stored) return undefined
  try {
    return (await api.compileBlueprint(rebaseBlueprint(await api.migrateProject(project), stored))).project
  } catch {
    return undefined
  }
}

interface HydrationResult {
  active: StudioProject
  blueprint?: StudioProjectV2
  projects: StudioProject[]
  warning?: string
}

async function resolveHydration(
  storedActive: StudioProject | undefined,
  projects: StudioProject[],
): Promise<HydrationResult> {
  let active = await validateStoredProject(storedActive)
  let warning: string | undefined
  if (storedActive && !active) warning = 'The stored active project was quarantined because authoritative validation failed.'
  if (!active) {
    active = await bundledProject()
    if (active === seed) warning ??= 'The loopback compiler is unavailable; the bundled project is open but exports stay disabled.'
  }
  return { active, blueprint: await restoreBlueprint(active), projects, warning }
}

function applyHydration(dispatch: Dispatch<Action>, result: HydrationResult, isCancelled: () => boolean): void {
  if (isCancelled()) return
  dispatch({ type: 'hydrate', active: result.active, blueprint: result.blueprint, projects: result.projects })
  if (result.warning) dispatch({ type: 'import:error', message: result.warning })
}


function hydrateStudio(
  dispatch: Dispatch<Action>,
  isCancelled: () => boolean,
): Promise<void> {
  return Promise.all([loadActiveDraft(), listDrafts()])
    .then(([storedActive, projects]) => resolveHydration(storedActive, projects))
    .then((result) => { applyHydration(dispatch, result, isCancelled) })
    .catch(() => {
      if (!isCancelled()) dispatch({ type: 'hydrate', projects: [] })
    })
}

export function StudioProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(studioReducer, initial)
  const request = useRef<AbortController | undefined>(undefined)

  const runCompile = useCallback((
    project: StudioProject,
    blueprint: StudioProjectV2 | undefined,
    revision: number,
  ) => {
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    dispatch({ type: 'compile:start', revision })
    void api.compile(project, controller.signal)
      .then(async (result) => {
        const migrated = await api.migrateProject(result.project, controller.signal)
        const candidate = rebaseBlueprint(migrated, blueprint)
        const blueprintResult = await api.compileBlueprint(
          candidate,
          controller.signal,
        )
        dispatch({ type: 'compile:success', result, blueprintResult, revision })
      })
      .catch((error: unknown) => {
        const message = compileMessage(error)
        if (message) dispatch({ type: 'compile:error', message, revision })
      })
  }, [])

  useEffect(() => {
    let cancelled = false
    void hydrateStudio(dispatch, () => cancelled).catch(() => {
      if (!cancelled) dispatch({ type: 'hydrate', projects: [] })
    })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
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
  }, [])

  useEffect(() => {
    if (!state.hydrated) return
    const project = state.project
    const revision = state.revision
    const timer = window.setTimeout(() => {
      dispatch({ type: 'storage:start', revision })
      void saveDraft(project, state.blueprint)
        .then(() => { dispatch({ type: 'storage:success', revision }) })
        .catch(() => { dispatch({ type: 'storage:error', revision }) })
    }, 180)
    return () => window.clearTimeout(timer)
  }, [state.hydrated, state.project, state.blueprint, state.revision])

  useEffect(() => {
    if (!state.hydrated) return
    const project = state.project
    const blueprint = state.blueprint
    const revision = state.revision
    const timer = window.setTimeout(
      () => runCompile(project, blueprint, revision),
      450,
    )
    return () => window.clearTimeout(timer)
  }, [runCompile, state.hydrated, state.revision])

  useEffect(() => () => request.current?.abort(), [])

  const updateProject = useCallback(
    (project: StudioProject, selectedGroup?: string) => {
      dispatch({ type: 'project:replace', project, selectedGroup })
    },
    [],
  )

  const updateBlueprint = useCallback((blueprint: StudioProjectV2) => {
    dispatch({ type: 'blueprint:replace', blueprint })
  }, [])

  const createNew = useCallback(async (kind: 'blank' | 'example') => {
    const source = kind === 'blank'
      ? blankProject()
      : exampleProject(`university-${Date.now().toString(36)}`)
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
  }, [])

  const openProject = useCallback(async (id: string) => {
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
  }, [])

  const importFiles = useCallback(async (input: FileList | File[]) => {
    dispatch({ type: 'import:error', message: undefined })
    const message = await importFilesIntoStudio(input, (project, blueprint) => {
      dispatch({ type: 'project:replace', project, blueprint })
    })
    if (message) dispatch({ type: 'import:error', message })
  }, [])

  const validateNow = useCallback(() => {
    runCompile(state.project, state.blueprint, state.revision)
  }, [runCompile, state.project, state.blueprint, state.revision])

  const value = useMemo<StudioContextValue>(() => ({
    ...state,
    dispatch,
    updateProject,
    updateBlueprint,
    createNew,
    openProject,
    importFiles,
    validateNow,
  }), [
    state,
    updateProject,
    updateBlueprint,
    createNew,
    openProject,
    importFiles,
    validateNow,
  ])

  return (
    <StudioContext.Provider value={value}>
      {children}
    </StudioContext.Provider>
  )
}

export function useStudio(): StudioContextValue {
  const value = useContext(StudioContext)
  if (!value) throw new Error('useStudio must be used within StudioProvider')
  return value
}
