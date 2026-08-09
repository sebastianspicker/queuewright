import { bundledCatalog, exampleProject } from '../data'
import type {
  BlueprintCompileResult,
  CompileResult,
  FeatureDefinition,
  FeatureId,
  StepId,
  StudioProject,
  StudioProjectV2,
} from '../types'

export type Action =
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

type CompileAction = Extract<Action, { type: `compile:${string}` }>
type StorageAction = Extract<Action, { type: `storage:${string}` }>

export interface State {
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

export const seedProject = exampleProject()
export const staticDemo = import.meta.env.VITE_STATIC_DEMO === 'true'

export const initialState: State = {
  project: seedProject,
  projects: staticDemo ? [seedProject] : [],
  catalog: bundledCatalog,
  step: 'start',
  selectedGroup: 'student_services',
  selectedFeature: 'cross_department_handoff',
  hydrated: staticDemo,
  revision: 0,
  dirty: true,
  compiling: false,
  storageStatus: staticDemo ? 'saved' : 'loading',
}

function upsert(
  projects: StudioProject[],
  project: StudioProject,
): StudioProject[] {
  return [project, ...projects.filter((item) => item.id !== project.id)]
    .sort((left, right) => left.name.localeCompare(right.name))
}

function replaceProject(state: State, action: Extract<Action, { type: 'project:replace' }>): State {
  return {
    ...state,
    project: action.project,
    projects: upsert(state.projects, action.project),
    selectedGroup: action.selectedGroup ?? state.selectedGroup,
    revision: state.revision + 1,
    dirty: true,
    result: undefined,
    blueprint: action.blueprint
      ?? (state.blueprint?.id === action.project.id ? state.blueprint : undefined),
    blueprintResult: undefined,
    compileError: undefined,
    importError: undefined,
    storageStatus: 'pending',
  }
}

function isCompileAction(action: Action): action is CompileAction {
  return action.type.startsWith('compile:')
}

function applyCompileAction(state: State, action: CompileAction): State {
  if (action.revision !== state.revision) return state
  if (action.type === 'compile:start') {
    return { ...state, compiling: true, compileError: undefined }
  }
  if (action.type === 'compile:error') {
    return {
      ...state,
      compiling: false,
      dirty: true,
      result: undefined,
      blueprintResult: undefined,
      compileError: action.message,
    }
  }
  return {
    ...state,
    compiling: false,
    dirty: false,
    result: action.result,
    blueprint: action.blueprintResult.project,
    blueprintResult: action.blueprintResult,
    compileError: undefined,
  }
}

function isStorageAction(action: Action): action is StorageAction {
  return action.type.startsWith('storage:')
}

function applyStorageAction(state: State, action: StorageAction): State {
  if (action.revision !== state.revision) return state
  const status = action.type === 'storage:start'
    ? 'saving'
    : action.type === 'storage:success' ? 'saved' : 'error'
  return { ...state, storageStatus: status }
}

export function studioReducer(state: State, action: Action): State {
  if (isCompileAction(action)) return applyCompileAction(state, action)
  if (isStorageAction(action)) return applyStorageAction(state, action)

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
      return replaceProject(state, action)
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
    case 'import:error':
      return { ...state, importError: action.message }
    default:
      return state
  }
}
