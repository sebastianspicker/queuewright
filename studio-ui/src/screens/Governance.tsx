import { useState } from 'react'
import { useStudioProject } from '../editor/context'
import { Delta, PageHeader, SectionHeading } from '../components/ui'
import { DecisionRow, isOpen } from './GovernanceDecisionRow'
import { decisionsByDomain } from './governance-domains'

export function Governance() {
  const { project, updateProject } = useStudioProject()
  const [openOnly, setOpenOnly] = useState(false)
  const decisions = Object.entries(project.workbook.capability_decisions)
  const open = decisions.filter(([, decision]) => isOpen(decision)).length
  const domains = decisionsByDomain(openOnly ? decisions.filter(([, decision]) => isOpen(decision)) : decisions)
  const manual = decisions.filter(([, decision]) => decision.enabled && decision.delivery === 'guided_manual').length
  const unsupported = decisions.filter(([, decision]) => decision.delivery === 'unsupported').length
  return (
    <section className="governance-screen">
      <PageHeader
        title="Governance decisions"
        description="Every capability is recorded with how it is delivered, its risk and what it depends on. Manual and verification choices are yours to make here; automated and unsupported ones are fixed by the design."
      />
      <dl className="tally" aria-label="Decision summary">
        <div className={open ? 'tally-item is-open' : 'tally-item'}>
          <dt className="caption">Open</dt>
          <dd>{open ? <Delta count={open} accessibleLabel={`${open} open`} /> : <span className="numeral">0</span>}</dd>
        </div>
        <div className="tally-item">
          <dt className="caption">Recorded</dt>
          <dd className="numeral">{decisions.length}</dd>
        </div>
        <div className="tally-item">
          <dt className="caption">Manual delivery</dt>
          <dd className="numeral">{manual}</dd>
        </div>
        <div className="tally-item">
          <dt className="caption">Unsupported</dt>
          <dd className="numeral">{unsupported}</dd>
        </div>
      </dl>
      <label className="filter-toggle">
        <input className="check" type="checkbox" checked={openOnly} onChange={(event) => setOpenOnly(event.target.checked)} />
        Show open decisions only
      </label>
      {openOnly && !open ? <p className="notice">No decisions are open. Every enabled capability is design-ready.</p> : null}
      {[...domains].map(([domain, items]) => (
        <section className="governance-domain" aria-labelledby={`domain-${domain}`} key={domain}>
          <SectionHeading id={`domain-${domain}`}>{domain}</SectionHeading>
          {items.map(([id, decision]) => (
            <DecisionRow project={project} decision={decision} id={id} key={id} updateProject={updateProject} />
          ))}
        </section>
      ))}
      {!decisions.length ? <p className="notice error" role="alert"><span><strong>No capability decisions.</strong> This Blueprint records none, so it cannot show complete governance.</span></p> : null}
    </section>
  )
}
