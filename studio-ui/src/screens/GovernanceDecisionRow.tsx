import { useStudio } from '../editor/context'
import { replaceDecision } from '../editor/model'
import type {
  CapabilityCompletion,
  CapabilityDecision,
  CapabilityDelivery,
  CapabilityRisk,
} from '../contracts'
import { Delta } from '../components/ui'
import {
  capabilityGuidance,
  completions,
  deliveryMessage,
  title,
} from './capability-meta'
import { decisionPresentation } from './decision-presentation'

const deliveryTag: Record<CapabilityDelivery, string> = {
  automated: 'tag',
  guided_manual: 'tag is-manual',
  verify_only: 'tag is-manual is-locked',
  unsupported: 'tag is-blocked is-locked',
}

export function isOpen(decision: CapabilityDecision): boolean {
  return decision.enabled && (decision.completion === 'decision_required' || decision.completion === 'blocked')
}

function Delivery({ value }: { value: CapabilityDelivery }) {
  return <span className={deliveryTag[value]} title={deliveryMessage(value)}>{title(value)}</span>
}

function Risk({ value }: { value: CapabilityRisk }) {
  return <span className={`risk risk-${value}`}><span className="risk-bars" aria-hidden="true"><i /><i /><i /></span>{title(value)} risk</span>
}

function guidanceFor(id: string): string | undefined {
  return Object.entries(capabilityGuidance).find(([key]) => key === id)?.at(1)
}

export function DecisionRow({
  project,
  decision,
  id,
  updateProject,
}: {
  project: ReturnType<typeof useStudio>['project']
  decision: CapabilityDecision
  id: string
  updateProject: ReturnType<typeof useStudio>['updateProject']
}) {
  const { deliveryIsLocked, deliveryHint, manualBoundary } = decisionPresentation(decision.delivery)
  const open = isOpen(decision)
  const name = title(id)
  return (
    <article className={open ? 'decision is-open' : decision.enabled ? 'decision' : 'decision is-excluded'} aria-label={name}>
      <div className="decision-title">
        <h3>{open ? <Delta count={1} accessibleLabel="Open decision" /> : null}{name}</h3>
        <p>{guidanceFor(id) ?? 'Capability decision'}</p>
      </div>
      <div className="decision-controls">
        <label className="decision-include">
          <input className="check" type="checkbox" checked={decision.enabled} disabled={deliveryIsLocked} onChange={(event) => { updateProject(replaceDecision(project, id, { enabled: event.target.checked })) }} aria-label={`Include ${name}`} title={deliveryHint} />
          <span aria-hidden="true">Include</span>
        </label>
        <select className="select decision-completion" value={decision.completion} disabled={decision.delivery === 'unsupported'} onChange={(event) => { updateProject(replaceDecision(project, id, { completion: event.target.value as CapabilityCompletion })) }} aria-label={`${name} completion`}>
          {completions.map((completion) => <option value={completion} key={completion}>{title(completion)}</option>)}
        </select>
      </div>
      <div className="decision-evidence">
        <Delivery value={decision.delivery} />
        <Risk value={decision.risk} />
        <span className="decision-deps">{decision.dependencies.length ? <>Depends on {decision.dependencies.map(title).join(', ')}</> : 'No dependencies'}</span>
      </div>
      {manualBoundary ? <p className={decision.delivery === 'unsupported' ? 'decision-boundary is-blocked' : 'decision-boundary'}>{manualBoundary}</p> : null}
    </article>
  )
}
