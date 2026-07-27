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
  ManifestDocument,
  ProfileDocument,
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

interface StudioContextValue extends State {
  dispatch: Dispatch<Action>
  updateProject(project: StudioProject, selectedGroup?: string): void
  updateBlueprint(project: StudioProjectV2): void
  createNew(kind: 'blank' | 'example'): Promise<void>
  openProject(id: string): Promise<void>
  importFiles(files: FileList | File[]): Promise<void>
  validateNow(): void
}

const StudioContext = createContext<StudioContextValue | undefined>(undefined)

function compileMessage(error: unknown): string {
  if (error instanceof DOMException && error.name === 'AbortError') return ''
  if (error instanceof StudioApiError) {
    return `${error.path}: ${error.message}`
  }
  return 'Loopback compiler unavailable. Exports stay disabled.'
}

async function readImportFile(file: Blob): Promise<string> {
  if (typeof file.text === 'function') {
    return file.text()
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result ?? ''))
    reader.onerror = () => reject(reader.error ?? new Error('Unable to read import file'))
    reader.readAsText(file)
  })
}

function looksLikeProject(value: unknown): value is StudioProject {
  return typeof value === 'object'
    && value !== null
    && (value as { project_schema_version?: unknown }).project_schema_version === '1.0'
}

function looksLikeBlueprint(value: unknown): value is StudioProjectV2 {
  return typeof value === 'object'
    && value !== null
    && (value as { project_schema_version?: unknown }).project_schema_version === '2.0'
}

function projectFromBlueprint(blueprint: StudioProjectV2): StudioProject {
  return {
    project_schema_version: '1.0',
    id: blueprint.id,
    name: blueprint.name,
    target_schema_version: blueprint.target_schema_version,
    ...blueprint.bundle,
  }
}

function rebaseBlueprint(
  migrated: StudioProjectV2,
  previous?: StudioProjectV2,
): StudioProjectV2 {
  if (!previous || previous.id !== migrated.id) return migrated
  const capability_decisions = Object.fromEntries(
    Object.entries(migrated.workbook.capability_decisions).map(
      ([id, pinned]) => {
        const editable = previous.workbook.capability_decisions[id]
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

function looksLikeProfile(value: unknown): value is ProfileDocument {
  return typeof value === 'object'
    && value !== null
    && typeof (value as { profile_key?: unknown }).profile_key === 'string'
}

function looksLikeManifest(value: unknown): value is ManifestDocument {
  return typeof value === 'object'
    && value !== null
    && typeof (value as { manifest_key?: unknown }).manifest_key === 'string'
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
    void Promise.all([loadActiveDraft(), listDrafts()])
      .then(async ([storedActive, projects]) => {
        let active: StudioProject | undefined
        let warning: string | undefined
        if (storedActive) {
          try {
            active = (await api.compile(storedActive)).project
          } catch {
            warning = 'The stored active project was quarantined because authoritative validation failed.'
          }
        }
        if (!active) {
          try {
            active = await api.importBundle(seed.profile, seed.manifest)
          } catch {
            active = seed
            warning ??= 'The loopback compiler is unavailable; the bundled project is open but exports stay disabled.'
          }
        }
        let blueprint: StudioProjectV2 | undefined
        const storedBlueprint = active
          ? await loadBlueprint(active.id)
          : undefined
        if (active && storedBlueprint) {
          try {
            const migrated = await api.migrateProject(active)
            const candidate = rebaseBlueprint(migrated, storedBlueprint)
            blueprint = (await api.compileBlueprint(candidate)).project
          } catch {
            warning = 'The stored Blueprint V2 workbook was quarantined because authoritative validation failed.'
          }
        }
        if (cancelled) return
        dispatch({ type: 'hydrate', active, blueprint, projects })
        if (warning) dispatch({ type: 'import:error', message: warning })
      })
      .catch(() => {
        if (!cancelled) dispatch({ type: 'hydrate', projects: [] })
      })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    void api.loadCatalog(controller.signal)
      .then((catalog) => dispatch({ type: 'catalog', catalog }))
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
        .then(() => dispatch({ type: 'storage:success', revision }))
        .catch(() => dispatch({ type: 'storage:error', revision }))
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
    const files = [...input]
    if (files.length < 1 || files.length > 2) {
      dispatch({ type: 'import:error', message: 'Choose one project or bundle file, or a profile and manifest pair.' })
      return
    }
    if (files.some((file) => file.size > 2 * 1024 * 1024)) {
      dispatch({ type: 'import:error', message: 'Each import file must be 2 MiB or smaller.' })
      return
    }
    try {
      const values = await Promise.all(files.map(async (file) =>
        JSON.parse(await readImportFile(file)) as unknown,
      ))
      const importedBlueprint = values.find(looksLikeBlueprint)
      if (importedBlueprint) {
        const blueprintResult = await api.compileBlueprint(importedBlueprint)
        const project = projectFromBlueprint(blueprintResult.project)
        const result = await api.compile(project)
        dispatch({
          type: 'project:replace',
          project: result.project,
          blueprint: blueprintResult.project,
        })
        return
      }
      const direct = values.find(looksLikeProject)
      if (direct) {
        const result = await api.compile(direct)
        const blueprint = await api.migrateProject(result.project)
        dispatch({ type: 'project:replace', project: result.project, blueprint })
        return
      }
      const bundle = values.find((value) =>
        typeof value === 'object'
        && value !== null
        && looksLikeProfile((value as { profile?: unknown }).profile)
        && looksLikeManifest((value as { manifest?: unknown }).manifest),
      ) as { profile: ProfileDocument; manifest: ManifestDocument } | undefined
      const profile = bundle?.profile ?? values.find(looksLikeProfile)
      const manifest = bundle?.manifest ?? values.find(looksLikeManifest)
      if (!profile || !manifest) {
        throw new Error('A profile and desired-state manifest are both required.')
      }
      const project = await api.importBundle(profile, manifest)
      const result = await api.compile(project)
      const blueprint = await api.migrateProject(result.project)
      dispatch({ type: 'project:replace', project: result.project, blueprint })
    } catch (error) {
      dispatch({
        type: 'import:error',
        message: error instanceof Error ? error.message : 'The selected JSON could not be imported.',
      })
    }
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
