import { createContext, useContext, useMemo, useReducer, type Context, type ReactNode } from 'react'
import type { StudioProjectV2 } from '../contracts'
import { useStudioCommands, type StudioCommands } from './commands'
import { useCompileRunner, useStudioEffects } from './effects'
import { initialState, staticDemo, studioReducer, type State } from './reducer'

interface StudioContextValue extends Omit<State, 'project'>, StudioCommands {
  project: StudioProjectV2
  bundle: StudioProjectV2['bundle']
  blueprintResult: State['result']
  demoMode: boolean
}
type ProjectContextValue = Pick<StudioContextValue, 'project' | 'updateProject' | 'editProject'>
type StructureContextValue = ProjectContextValue & Pick<StudioContextValue, 'selectedGroup' | 'selectGroup'>

// Separate contexts keep narrow consumers from re-rendering on unrelated state changes.
const StudioContext = createContext<StudioContextValue | undefined>(undefined)
const ProjectContext = createContext<ProjectContextValue | undefined>(undefined)
const StructureContext = createContext<StructureContextValue | undefined>(undefined)
const StepContext = createContext<State['step'] | undefined>(undefined)

export function StudioProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(studioReducer, initialState)
  const runCompile = useCompileRunner(dispatch)
  useStudioEffects(state, dispatch, runCompile)
  const commands = useStudioCommands(state, dispatch, runCompile)
  const value = useMemo<StudioContextValue>(() => ({
    ...state,
    ...commands,
    project: state.project,
    bundle: state.project.bundle,
    blueprintResult: state.result,
    demoMode: staticDemo,
  }), [state, commands])
  const projectValue = useMemo(() => ({
    project: state.project,
    updateProject: commands.updateProject,
    editProject: commands.editProject,
  }), [state.project, commands.updateProject, commands.editProject])
  const structureValue = useMemo(() => ({
    ...projectValue,
    selectedGroup: state.selectedGroup,
    selectGroup: commands.selectGroup,
  }), [projectValue, state.selectedGroup, commands.selectGroup])
  return (
    <StudioContext.Provider value={value}>
      <ProjectContext.Provider value={projectValue}>
        <StructureContext.Provider value={structureValue}>
          <StepContext.Provider value={state.step}>{children}</StepContext.Provider>
        </StructureContext.Provider>
      </ProjectContext.Provider>
    </StudioContext.Provider>
  )
}

function useRequiredContext<T>(context: Context<T | undefined>, hook: string): T {
  const value = useContext(context)
  if (!value) throw new Error(`${hook} must be used within StudioProvider`)
  return value
}

export function useStudio(): StudioContextValue { return useRequiredContext(StudioContext, 'useStudio') }
export function useStudioProject(): ProjectContextValue { return useRequiredContext(ProjectContext, 'useStudioProject') }
export function useStudioStructure(): StructureContextValue { return useRequiredContext(StructureContext, 'useStudioStructure') }
export function useStudioStep(): State['step'] { return useRequiredContext(StepContext, 'useStudioStep') }
