import { Component, lazy, Suspense, type ComponentType, type ReactNode } from 'react'
import { Inspector, ProvenanceStrip, RevisionRail, StatusRail, StepRail, TopBar } from '../components'
import { Start } from '../screens/Start'
import { StudioProvider, useStudioStep } from '../editor/context'
import type { StepId } from '../contracts'
import '../styles/index.css'

const screens: Record<StepId, ComponentType> = {
  start: Start,
  organization: lazy(() => import('../screens/Organization').then((module) => ({ default: module.Organization }))),
  structure: lazy(() => import('../screens/Structure').then((module) => ({ default: module.Structure }))),
  access: lazy(() => import('../screens/Access').then((module) => ({ default: module.Access }))),
  features: lazy(() => import('../screens/Features').then((module) => ({ default: module.Features }))),
  governance: lazy(() => import('../screens/Governance').then((module) => ({ default: module.Governance }))),
  'test-data': lazy(() => import('../screens/Readiness').then((module) => ({ default: module.Readiness }))),
  review: lazy(() => import('../screens/Review').then((module) => ({ default: module.Review }))),
}

class ScreenBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() {
    return this.state.failed
      ? <section role="alert"><h1>This screen could not be loaded</h1><p>Your draft remains in this session. Choose another step, or reload Studio after checking the local service.</p></section>
      : this.props.children
  }
}

function Studio() {
  const step = useStudioStep()
  const Screen = screens[step]
  return <div className="app-shell"><TopBar /><ProvenanceStrip /><div className="workspace"><StepRail /><RevisionRail />
    <main className="canvas"><ScreenBoundary key={step}><Suspense fallback={<p role="status" aria-live="polite">Loading step…</p>}><Screen /></Suspense></ScreenBoundary></main>
    <Inspector /></div><StatusRail /></div>
}
export default function App() { return <StudioProvider><Studio /></StudioProvider> }
