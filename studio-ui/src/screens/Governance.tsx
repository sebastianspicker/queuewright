import { useStudio } from '../studio-state'
import { PageHeader, SectionHeading } from '../ui'
import { DecisionRow } from './GovernanceDecisionRow'
import { decisionsByDomain } from './governance-domains'

export function Governance() {
  const { blueprint, updateBlueprint } = useStudio()
  const decisions = blueprint ? Object.entries(blueprint.workbook.capability_decisions) : []
  const domains = decisionsByDomain(decisions)
  return (
    <section className="governance-screen">
      <PageHeader
        kicker="Step 06 · Capability decisions"
        title="Govern every capability decision"
        description="Every capability is recorded with its delivery boundary, risk, and prerequisites. Manual and verification choices are editable here; bundle-derived and unsupported decisions stay locked."
      />
      {!blueprint ? <p className="notice">A Blueprint V2 project is required before capability decisions can be changed.</p> : null}
      {blueprint ? [...domains].map(([domain, items]) => (
        <section className="governance-domain" aria-labelledby={`domain-${domain}`} key={domain}>
          <SectionHeading id={`domain-${domain}`}>{domain}</SectionHeading>
          {items.map(([id, decision]) => (
            <DecisionRow blueprint={blueprint} decision={decision} id={id} key={id} updateBlueprint={updateBlueprint} />
          ))}
        </section>
      )) : null}
      {blueprint && !decisions.length ? <p className="notice error">The Blueprint has no capability decisions. It cannot demonstrate complete governance.</p> : null}
    </section>
  )
}
