import { useStudioProject } from '../editor/context'
import { PageHeader, SectionHeading } from '../components/ui'
import { DecisionRow } from './GovernanceDecisionRow'
import { decisionsByDomain } from './governance-domains'

export function Governance() {
  const { project, updateProject } = useStudioProject()
  const decisions = Object.entries(project.workbook.capability_decisions)
  const domains = decisionsByDomain(decisions)
  return (
    <section className="governance-screen">
      <PageHeader
        kicker="Step 06 · Capability decisions"
        title="Govern every capability decision"
        description="Every capability is recorded with its delivery boundary, risk, and prerequisites. Manual and verification choices are editable here; bundle-derived and unsupported decisions stay locked."
      />
      {[...domains].map(([domain, items]) => (
        <section className="governance-domain" aria-labelledby={`domain-${domain}`} key={domain}>
          <SectionHeading id={`domain-${domain}`}>{domain}</SectionHeading>
          {items.map(([id, decision]) => (
            <DecisionRow project={project} decision={decision} id={id} key={id} updateProject={updateProject} />
          ))}
        </section>
      ))}
      {!decisions.length ? <p className="notice error">The Blueprint has no capability decisions. It cannot demonstrate complete governance.</p> : null}
    </section>
  )
}
