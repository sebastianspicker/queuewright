import { Component, lazy, Suspense, type ComponentType, type ReactNode } from 'react'
import { Inspector, SheetIndex, SheetNotesPanel, TitleBlock, TopBar } from '../components'
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
      ? <section className="sheet-failure" role="alert"><h1>This sheet could not be opened</h1><p>Your draft is still held in this session. Choose another sheet, or check that the local service is running and reload Studio.</p></section>
      : this.props.children
  }
}

function Studio() {
  const step = useStudioStep()
  const Screen = screens[step]
  return <div className="app-shell" data-step={step}><TopBar /><div className="workspace"><SheetIndex />
    <main className="canvas" id="sheet"><ScreenBoundary key={step}><Suspense fallback={<p className="sheet-loading" role="status">Opening sheet…</p>}><Screen /></Suspense></ScreenBoundary><div className="sheet-notes-inline"><SheetNotesPanel /></div></main>
    <Inspector /></div><TitleBlock /></div>
}
export default function App() { return <StudioProvider><Studio /></StudioProvider> }
