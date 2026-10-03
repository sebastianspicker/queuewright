import { useStudio } from '../editor/context'
import { PageHeader, SectionHeading } from '../components/ui'
import { title } from './capability-meta'

function Figure({ value, label }: { value: number | string; label: string }) {
  return (
    <div className="figure">
      <dt>{label}</dt>
      <dd className="numeral">{value}</dd>
    </div>
  )
}

function Names({ ids }: { ids: string[] }) {
  return <ul className="name-list">{ids.map((id) => <li key={id}>{title(id)}</li>)}</ul>
}

export function Readiness() {
  const { project, blueprintResult } = useStudio()
  const decisions = Object.entries(project.workbook.capability_decisions)
  const synthetic = project.bundle.manifest.users
  const scenarios = project.bundle.profile.uat.scenarios
  const enabled = decisions.filter(([, decision]) => decision.enabled)
  const ready = enabled.filter(([, decision]) => decision.completion === 'ready').length
  const awaiting = enabled.filter(([, decision]) => decision.completion === 'decision_required').length
  const manual = decisions.filter(([, decision]) => decision.enabled && decision.delivery === 'guided_manual').map(([id]) => id)
  const unsupported = decisions.filter(([, decision]) => decision.delivery === 'unsupported').map(([id]) => id)
  const blocked = decisions.filter(([, decision]) => decision.completion === 'blocked').map(([id]) => id)
  const nodes = blueprintResult?.graph.nodes ?? []
  const count = (delivery: string) => nodes.filter((node) => node.delivery === delivery).length
  return (
    <section className="readiness-screen">
      <PageHeader
        title="Readiness"
        description="What the design is ready for, and what it is not. Readiness combines synthetic test coverage, the decisions on sheet 06 and the latest local compile. It never shows that a tenant has changed."
      />

      <div className="readiness-columns">
        <section aria-labelledby="ready-decisions">
          <SectionHeading id="ready-decisions">Decisions</SectionHeading>
          <dl className="figures">
            <Figure value={ready} label="enabled and design-ready" />
            <Figure value={awaiting} label="still need an owner decision" />
          </dl>
        </section>
        <section aria-labelledby="ready-synthetic">
          <SectionHeading id="ready-synthetic">Synthetic test data</SectionHeading>
          <dl className="figures">
            <Figure value={synthetic?.agents.length ?? 0} label="agents" />
            <Figure value={synthetic?.customers.length ?? 0} label="customers" />
            <Figure value={scenarios.length} label="internal UAT scenarios" />
          </dl>
          <p className="column-note">Outbound communication stays disabled.</p>
        </section>
        <section aria-labelledby="ready-graph">
          <SectionHeading id="ready-graph">Configuration graph</SectionHeading>
          {blueprintResult ? (
            <>
              <dl className="figures">
                <Figure value={nodes.length} label="nodes" />
                <Figure value={count('automated')} label="automated" />
                <Figure value={count('guided_manual')} label="manual" />
                <Figure value={count('unsupported')} label="unsupported" />
              </dl>
              <p className="column-note"><span className="caption">Identity</span> <code className="hash-full">{blueprintResult.graph.graph_hash}</code></p>
            </>
          ) : (
            <p className="column-note is-pending">Not compiled yet. Validate the design to build the graph.</p>
          )}
        </section>
      </div>

      <section className="limits" aria-labelledby="limits-heading">
        <SectionHeading id="limits-heading">Not delivered by Studio</SectionHeading>
        <div className="limit-row">
          <h3><span className="tag is-manual">Manual</span></h3>
          {manual.length ? <div><Names ids={manual} /><p>Incomplete until an administrator performs them and keeps the evidence.</p></div> : <p>No enabled capability needs guided manual delivery.</p>}
        </div>
        <div className="limit-row">
          <h3><span className="tag is-blocked is-locked">Unsupported</span></h3>
          {unsupported.length ? <div><Names ids={unsupported} /><p>This workflow cannot deliver these. They stay visible as blockers.</p></div> : <p>None.</p>}
        </div>
        <div className="limit-row">
          <h3><span className="tag is-blocked">Blocked</span></h3>
          {blocked.length ? <div><Names ids={blocked} /></div> : <p>None.</p>}
        </div>
      </section>
      <p className="notice">
        {blueprintResult
          ? <span>The graph is a <strong>local compile snapshot</strong>. It is not evidence of network access, a tenant connection or applied changes.</span>
          : <span><strong>Graph readiness is not established:</strong> there is no local V2 compile result yet.</span>}
      </p>
    </section>
  )
}
