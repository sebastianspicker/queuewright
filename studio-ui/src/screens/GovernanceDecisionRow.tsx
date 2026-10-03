import { AlertTriangle, Link2 } from 'lucide-react'
import { useStudio } from '../editor/context'
import { replaceDecision } from '../editor/model'
import type {
  CapabilityCompletion,
  CapabilityDecision,
  CapabilityDelivery,
  CapabilityRisk,
} from '../contracts'
import {
  capabilityGuidance,
  completions,
  deliveryMessage,
  title,
} from './capability-meta'
import { decisionPresentation } from './decision-presentation'

function Delivery({ value }: { value: CapabilityDelivery }) {
  return <span className={`delivery-state delivery-${value}`} title={deliveryMessage(value)}>{title(value)}</span>
}

function Risk({ value }: { value: CapabilityRisk }) {
  return <span className={`risk-state risk-${value}`}>{value} risk</span>
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
  return (
    <article className="governance-row" key={id}>
      <div className="governance-title"><strong>{title(id)}</strong><small>{guidanceFor(id) ?? 'Capability decision'}</small></div>
      <label className="governance-control">Included<input type="checkbox" checked={decision.enabled} disabled={deliveryIsLocked} title={deliveryHint} onChange={(event) => { updateProject(replaceDecision(project, id, { enabled: event.target.checked })) }} aria-label={`Include ${title(id)}`} /></label>
      <label className="governance-control">Completion<select value={decision.completion} disabled={decision.delivery === 'unsupported'} onChange={(event) => { updateProject(replaceDecision(project, id, { completion: event.target.value as CapabilityCompletion })) }} aria-label={`${title(id)} completion`}>{completions.map((completion) => <option value={completion} key={completion}>{title(completion)}</option>)}</select></label>
      <div className="governance-evidence"><Delivery value={decision.delivery} /><Risk value={decision.risk} />{decision.dependencies.length ? <span><Link2 size={15} aria-hidden="true" /> Depends on {decision.dependencies.map(title).join(', ')}</span> : <span>No capability dependencies</span>}</div>
      {manualBoundary ? <p className="manual-boundary"><AlertTriangle size={16} aria-hidden="true" /> {manualBoundary}</p> : null}
    </article>
  )
}
