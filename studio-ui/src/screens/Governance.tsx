import { AlertTriangle, Link2 } from 'lucide-react'
import { useStudio } from '../studio-state'
import { PageHeader, SectionHeading } from '../ui'
import type {
  CapabilityCompletion,
  CapabilityDecision,
  CapabilityDelivery,
  CapabilityRisk,
} from '../types'
import {
  capabilityDomains,
  capabilityGuidance,
  completions,
  deliveryMessage,
  replaceDecision,
  title,
} from './capability-meta'

function Delivery({ value }: { value: CapabilityDelivery }) {
  return (
    <span className={`delivery-state delivery-${value}`} title={deliveryMessage(value)}>
      {title(value)}
    </span>
  )
}

function Risk({ value }: { value: CapabilityRisk }) {
  return <span className={`risk-state risk-${value}`}>{value} risk</span>
}

export function Governance() {
  const { blueprint, updateBlueprint } = useStudio()
  const decisions = blueprint ? Object.entries(blueprint.workbook.capability_decisions) : []
  const domains = new Map<string, Array<[string, CapabilityDecision]>>()
  for (const decision of decisions) {
    const domain = capabilityDomains[decision[0]] ?? 'Unclassified capability'
    const list = domains.get(domain) ?? []
    list.push(decision)
    domains.set(domain, list)
  }
  return (
    <section className="governance-screen">
      <PageHeader
        kicker="Step 06 · Capability decisions"
        title="Govern every capability decision"
        description="Every capability is recorded with its delivery boundary, risk, and prerequisites. Manual and verification choices are editable here; bundle-derived and unsupported decisions stay locked."
      />
      {!blueprint ? <p className="notice">A Blueprint V2 project is required before capability decisions can be changed.</p> : null}
      {[...domains].map(([domain, items]) => (
        <section className="governance-domain" aria-labelledby={`domain-${domain}`} key={domain}>
          <SectionHeading id={`domain-${domain}`}>{domain}</SectionHeading>
          {items.map(([id, decision]) => (
            <article className="governance-row" key={id}>
              <div className="governance-title"><strong>{title(id)}</strong><small>{capabilityGuidance[id] ?? 'Capability decision'}</small></div>
              <label className="governance-control">Included<input type="checkbox" checked={decision.enabled} disabled={decision.delivery === 'automated' || decision.delivery === 'unsupported'} title={decision.delivery === 'automated' ? 'Configure this capability in the preceding design steps.' : decision.delivery === 'unsupported' ? 'This capability remains disabled because this workflow cannot deliver it.' : undefined} onChange={(event) => updateBlueprint(replaceDecision(blueprint!, id, { enabled: event.target.checked }))} aria-label={`Include ${title(id)}`} /></label>
              <label className="governance-control">Completion<select value={decision.completion} disabled={decision.delivery === 'unsupported'} onChange={(event) => updateBlueprint(replaceDecision(blueprint!, id, { completion: event.target.value as CapabilityCompletion }))} aria-label={`${title(id)} completion`}>{completions.map((completion) => <option value={completion} key={completion}>{title(completion)}</option>)}</select></label>
              <div className="governance-evidence"><Delivery value={decision.delivery} /><Risk value={decision.risk} />{decision.dependencies.length ? <span><Link2 size={15} aria-hidden="true" /> Depends on {decision.dependencies.map(title).join(', ')}</span> : <span>No capability dependencies</span>}</div>
              {decision.delivery === 'guided_manual' || decision.delivery === 'unsupported' ? <p className="manual-boundary"><AlertTriangle size={16} aria-hidden="true" /> {decision.delivery === 'unsupported' ? 'Unsupported: retain this as a visible blocker; no workaround is applied here.' : 'Manual delivery: assign and evidence the administrator work outside this studio.'}</p> : null}
            </article>
          ))}
        </section>
      ))}
      {blueprint && !decisions.length ? <p className="notice error">The Blueprint has no capability decisions. It cannot demonstrate complete governance.</p> : null}
    </section>
  )
}
