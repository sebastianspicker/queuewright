import { AlertTriangle, Link2 } from 'lucide-react'
import { useStudio } from '../studio-state'
import type {
  CapabilityCompletion,
  CapabilityDecision,
  CapabilityDelivery,
  CapabilityRisk,
} from '../types'
import {
  capabilityGuidance,
  completions,
  deliveryMessage,
  replaceDecision,
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
  blueprint,
  decision,
  id,
  updateBlueprint,
}: {
  blueprint: NonNullable<ReturnType<typeof useStudio>['blueprint']>
  decision: CapabilityDecision
  id: string
  updateBlueprint: ReturnType<typeof useStudio>['updateBlueprint']
}) {
  const { deliveryIsLocked, deliveryHint, manualBoundary } = decisionPresentation(decision.delivery)
  return (
    <article className="governance-row" key={id}>
      <div className="governance-title"><strong>{title(id)}</strong><small>{guidanceFor(id) ?? 'Capability decision'}</small></div>
      <label className="governance-control">Included<input type="checkbox" checked={decision.enabled} disabled={deliveryIsLocked} title={deliveryHint} onChange={(event) => { updateBlueprint(replaceDecision(blueprint, id, { enabled: event.target.checked })) }} aria-label={`Include ${title(id)}`} /></label>
      <label className="governance-control">Completion<select value={decision.completion} disabled={decision.delivery === 'unsupported'} onChange={(event) => { updateBlueprint(replaceDecision(blueprint, id, { completion: event.target.value as CapabilityCompletion })) }} aria-label={`${title(id)} completion`}>{completions.map((completion) => <option value={completion} key={completion}>{title(completion)}</option>)}</select></label>
      <div className="governance-evidence"><Delivery value={decision.delivery} /><Risk value={decision.risk} />{decision.dependencies.length ? <span><Link2 size={15} aria-hidden="true" /> Depends on {decision.dependencies.map(title).join(', ')}</span> : <span>No capability dependencies</span>}</div>
      {manualBoundary ? <p className="manual-boundary"><AlertTriangle size={16} aria-hidden="true" /> {manualBoundary}</p> : null}
    </article>
  )
}
