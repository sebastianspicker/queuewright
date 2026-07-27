import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  ClipboardCheck,
  Workflow,
} from 'lucide-react'
import { useStudio } from '../studio-state'
import { PageHeader } from '../ui'
import { graphSummary, title } from './capability-meta'

export function Readiness() {
  const { blueprint, blueprintResult } = useStudio()
  const decisions = blueprint ? Object.entries(blueprint.workbook.capability_decisions) : []
  const synthetic = blueprint?.bundle.manifest.users
  const scenarios = blueprint?.bundle.profile.uat.scenarios ?? []
  const manual = decisions.filter(([, decision]) => decision.enabled && decision.delivery === 'guided_manual')
  const unsupported = decisions.filter(([, decision]) => decision.delivery === 'unsupported')
  const blocked = decisions.filter(([, decision]) => decision.completion === 'blocked')
  return (
    <section className="readiness-screen">
      <PageHeader
        kicker="Step 07 · Design readiness"
        title="Check readiness honestly"
        description="Readiness combines synthetic test coverage, declared decisions, and the latest local compile graph. It does not prove a tenant has been changed."
      />
      <div className="readiness-grid">
        <div className="readiness-card"><Building2 size={21} aria-hidden="true" /><h2>Safe synthetic test data</h2><p>{synthetic?.agents.length ?? 0} agents and {synthetic?.customers.length ?? 0} customers use the V1 safe synthetic bundle.</p><p>{scenarios.length} internal-only UAT scenarios; outbound communication remains disabled.</p></div>
        <div className="readiness-card"><ClipboardCheck size={21} aria-hidden="true" /><h2>Decision completion</h2><p>{decisions.filter(([, decision]) => decision.enabled && decision.completion === 'ready').length} enabled capabilities are design-ready.</p><p>{decisions.filter(([, decision]) => decision.enabled && decision.completion === 'decision_required').length} enabled decisions still require an owner decision.</p></div>
        <div className="readiness-card"><Workflow size={21} aria-hidden="true" /><h2>Graph readiness</h2>{graphSummary(blueprintResult).map(([label, value]) => <p key={label}><strong>{label}:</strong> {value}</p>)}</div>
      </div>
      <div className="readiness-limitations" aria-label="Readiness limitations">
        <h2><AlertTriangle size={20} aria-hidden="true" /> Manual and unsupported limitations</h2>
        {manual.length ? <p><strong>Manual delivery required:</strong> {manual.map(([id]) => title(id)).join(', ')}. These remain incomplete until independently performed and evidenced.</p> : <p>No enabled capabilities currently require guided manual delivery.</p>}
        {unsupported.length ? <p><strong>Unsupported:</strong> {unsupported.map(([id]) => title(id)).join(', ')}. The studio cannot deliver these capabilities.</p> : null}
        {blocked.length ? <p><strong>Blocked:</strong> {blocked.map(([id]) => title(id)).join(', ')}.</p> : null}
        {!blueprintResult ? <p><strong>Compile status:</strong> no V2 compile result is available, so graph readiness is not established.</p> : <p><CheckCircle2 size={18} aria-hidden="true" /> The graph shown is a local compile snapshot only; it is not evidence of network access, tenant connection, or applied changes.</p>}
      </div>
    </section>
  )
}
