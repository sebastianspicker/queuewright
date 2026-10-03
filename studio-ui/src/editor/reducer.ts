import { bundledCatalog, staticDemoProject } from '../data'
import type { BlueprintCompileResult, FeatureDefinition, FeatureId, StepId, StudioProjectV2 } from '../contracts'

export type Action =
  | { type: 'hydrate'; active?: StudioProjectV2; projects: StudioProjectV2[]; result?: BlueprintCompileResult }
  | { type: 'command:start'; id: number }
  | { type: 'command:success'; id: number; project: StudioProjectV2; selectedGroup?: string }
  | { type: 'command:error'; id: number; message: string }
  | { type: 'project:edit'; edit: (project: StudioProjectV2) => StudioProjectV2 }
  | { type: 'projects:loaded'; projects: StudioProjectV2[] }
  | { type: 'project:replace'; project: StudioProjectV2; selectedGroup?: string }
  | { type: 'step'; step: StepId }
  | { type: 'group:select'; id?: string }
  | { type: 'feature:select'; id?: FeatureId }
  | { type: 'catalog'; catalog: FeatureDefinition[] }
  | { type: 'catalog:error'; message: string }
  | { type: 'compile:start'; revision: number }
  | { type: 'compile:success'; result: BlueprintCompileResult; revision: number }
  | { type: 'compile:error'; message: string; revision: number }
  | { type: 'import:error'; message?: string }
  | { type: 'storage:start'; revision: number }
  | { type: 'storage:success'; revision: number }
  | { type: 'storage:error'; revision: number }

export interface State {
  project: StudioProjectV2
  projects: StudioProjectV2[]
  catalog: FeatureDefinition[]
  step: StepId
  selectedGroup?: string
  selectedFeature?: FeatureId
  pendingCommand?: number
  hydrated: boolean
  revision: number
  dirty: boolean
  compiling: boolean
  result?: BlueprintCompileResult
  compileError?: string
  catalogError?: string
  importError?: string
  storageStatus: 'loading' | 'pending' | 'saving' | 'saved' | 'error'
}

export const seedProject = staticDemoProject()
export const staticDemo = import.meta.env.VITE_STATIC_DEMO === 'true'
export const initialState: State = {
  project: seedProject, projects: staticDemo ? [seedProject] : [], catalog: bundledCatalog,
  step: 'start', selectedGroup: 'student_services', selectedFeature: 'cross_department_handoff',
  hydrated: staticDemo, revision: 0, dirty: true, compiling: false,
  storageStatus: staticDemo ? 'saved' : 'loading',
}

function upsert(projects: StudioProjectV2[], project: StudioProjectV2): StudioProjectV2[] {
  return [project, ...projects.filter((item) => item.id !== project.id)]
    .sort((left, right) => left.name.localeCompare(right.name))
}

function replaceProject(state: State, project: StudioProjectV2, selectedGroup?: string): State {
  return { ...state, project, projects: upsert(state.projects, project),
    selectedGroup: selectedGroup ?? state.selectedGroup, revision: state.revision + 1,
    dirty: true, compiling: false, result: undefined, compileError: undefined, importError: undefined,
    storageStatus: 'pending', pendingCommand: undefined }
}

export function studioReducer(state: State, action: Action): State {
  switch (action.type) {
    case 'compile:start': return action.revision === state.revision ? { ...state, compiling: true, compileError: undefined } : state
    case 'compile:success': return action.revision === state.revision ? {
      ...state, project: action.result.project, projects: upsert(state.projects, action.result.project),
      compiling: false, dirty: false, result: action.result, compileError: undefined,
    } : state
    case 'compile:error': return action.revision === state.revision ? {
      ...state, compiling: false, dirty: true, result: undefined, compileError: action.message,
    } : state
    case 'storage:start': return action.revision === state.revision ? { ...state, storageStatus: 'saving' } : state
    case 'storage:success': return action.revision === state.revision ? { ...state, storageStatus: 'saved' } : state
    case 'storage:error': return action.revision === state.revision ? { ...state, storageStatus: 'error' } : state
    case 'command:start': return { ...state, pendingCommand: action.id }
    case 'command:success': return state.pendingCommand === action.id ? replaceProject(state, action.project, action.selectedGroup) : state
    case 'command:error': return state.pendingCommand === action.id ? { ...state, pendingCommand: undefined, importError: action.message } : state
    case 'hydrate': return state.revision > 0 || state.pendingCommand !== undefined
      ? { ...state, hydrated: true, storageStatus: state.storageStatus === 'loading' ? 'pending' : state.storageStatus }
      : { ...state, project: action.active ?? state.project,
      projects: upsert(action.projects, action.active ?? state.project), hydrated: true,
      revision: state.revision + 1, dirty: !action.result, result: action.result, compiling: false, compileError: undefined, storageStatus: 'saved', pendingCommand: undefined }
    case 'projects:loaded': return { ...state, projects: upsert(
      [...action.projects.filter((project) => !state.projects.some((current) => current.id === project.id)), ...state.projects], state.project) }
    case 'project:edit': return replaceProject(state, action.edit(state.project))
    case 'project:replace': return replaceProject(state, action.project, action.selectedGroup)
    case 'step': return { ...state, step: action.step }
    case 'group:select': return { ...state, selectedGroup: action.id }
    case 'feature:select': return { ...state, selectedFeature: action.id }
    case 'catalog': return { ...state, catalog: action.catalog, catalogError: undefined }
    case 'catalog:error': return { ...state, catalogError: action.message }
    case 'import:error': return { ...state, importError: action.message }
  }
}
