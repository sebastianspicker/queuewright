import {
  createContext,
  useContext,
  useMemo,
  useReducer,
  type Dispatch,
  type ReactNode,
} from 'react'
import type { StudioProject, StudioProjectV2 } from '../types'
import { useStudioCommands, type StudioCommands } from './commands'
import { useCompileRunner, useStudioEffects } from './effects'
import {
  initialState,
  staticDemo,
  studioReducer,
  type Action,
  type State,
} from './model'

interface StudioContextValue extends State, StudioCommands {
  demoMode: boolean
  dispatch: Dispatch<Action>
  updateProject(project: StudioProject, selectedGroup?: string): void
  updateBlueprint(project: StudioProjectV2): void
}

const StudioContext = createContext<StudioContextValue | undefined>(undefined)

export function StudioProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(studioReducer, initialState)
  const runCompile = useCompileRunner(dispatch)
  useStudioEffects(state, dispatch, runCompile)
  const commands = useStudioCommands(state, dispatch, runCompile)
  const value = useMemo<StudioContextValue>(() => ({
    ...state,
    ...commands,
    demoMode: staticDemo,
    dispatch,
  }), [state, commands])

  return <StudioContext.Provider value={value}>{children}</StudioContext.Provider>
}

export function useStudio(): StudioContextValue {
  const value = useContext(StudioContext)
  if (!value) throw new Error('useStudio must be used within StudioProvider')
  return value
}
