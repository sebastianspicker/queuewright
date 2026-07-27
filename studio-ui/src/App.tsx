import {
  Inspector,
  ProvenanceStrip,
  RevisionRail,
  StatusRail,
  StepRail,
  TopBar,
} from './shell'
import {
  Access,
  Features,
  Governance,
  Organization,
  Readiness,
  Review,
  Start,
  Structure,
} from './screens'
import { StudioProvider, useStudio } from './studio-state'
import type { ComponentType } from 'react'
import type { StepId } from './types'
import './styles/index.css'

const screens: Record<StepId, ComponentType> = {
  start: Start,
  organization: Organization,
  structure: Structure,
  access: Access,
  features: Features,
  governance: Governance,
  'test-data': Readiness,
  review: Review,
}

function Studio() {
  const { step } = useStudio()
  const Screen = screens[step]
  return (
    <div className="app-shell">
      <TopBar />
      <ProvenanceStrip />
      <div className="workspace">
        <StepRail />
        <RevisionRail />
        <main className="canvas"><Screen /></main>
        <Inspector />
      </div>
      <StatusRail />
    </div>
  )
}

export default function App() {
  return <StudioProvider><Studio /></StudioProvider>
}
