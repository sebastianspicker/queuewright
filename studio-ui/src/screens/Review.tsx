import { Download } from 'lucide-react'
import { LOCAL_SERVICE_UNREACHABLE, useStudio } from '../editor/context'
import { isLocallyValid, openDecisionCount, plural } from '../components/status'
import { Delta, PageHeader, SectionHeading } from '../components/ui'
import { download } from './download'

function issueText(issue: string | { code: string; path: string; message: string }): string {
  return typeof issue === 'string' ? issue : `${issue.path}: ${issue.message}`
}

const artifactKinds = [
  ['Blueprint', 'blueprint-v2', 'The canonical, editable Blueprint V2 document.'],
  ['Project', 'project-bundle', 'Profile and manifest together, as compiled.'],
  ['Profile', 'profile', 'Identity, presentation and UAT settings.'],
  ['Desired state', 'desired-state', 'Groups, roles, organizations and objects.'],
  ['Inert plan', 'plan', 'Ordered symbolic operations. Nothing executes them.'],
  ['Configuration graph', 'configuration-graph', 'Nodes, dependencies and delivery per node.'],
] as const

export function Review() {
  const studio = useStudio()
  const {
    project,
    result,
    blueprintResult,
    compileError,
    compiling,
    validateNow,
    demoMode,
    revision,
  } = studio
  const ready = isLocallyValid(studio)
  const decisions = Object.values(project.workbook.capability_decisions)
  const unresolved = openDecisionCount(project)
  const key = project.bundle.profile.profile_key
  const values: unknown[] = [
    blueprintResult?.project,
    blueprintResult?.bundle,
    blueprintResult?.bundle.profile,
    blueprintResult?.bundle.manifest,
    blueprintResult?.plan,
    blueprintResult?.graph,
  ]
  const issues = result?.issues ?? []
  const state = demoMode ? 'demo' : ready ? 'valid' : compiling ? 'pending' : compileError ? 'error' : 'stale'
  const verdict = {
    demo: ['Simulated', 'The static demo cannot compile or export. Run Studio locally to validate this design.'],
    valid: ['Locally valid', `Revision ${revision} compiled locally. Its artifacts are ready to download for review.`],
    pending: ['Validating…', 'The local compiler is checking this revision.'],
    error: compileError === LOCAL_SERVICE_UNREACHABLE
      ? ['Not validated', 'Studio cannot reach its local service at 127.0.0.1:8765. Start it with python3 -m queuewright studio, then validate again.']
      : ['Validation failed', compileError ?? ''],
    stale: ['Needs validation', 'This revision has edits that have not been compiled. Exports stay disabled until it validates.'],
  }[state]
  return (
    <section className="review-screen">
      <PageHeader
        title="Review and export"
        description="Validate the current revision, then take its artifacts to review. Only the latest successful local compile can be exported."
        action={
          <button className="button primary" type="button" onClick={validateNow} disabled={compiling}>
            {demoMode ? 'Simulate validation' : ready ? 'Validate again' : 'Validate design'}
          </button>
        }
      />
      <div className={`verdict is-${state}`}>
        <p className="verdict-state">{verdict[0]}</p>
        <p className="verdict-text">{verdict[1]}</p>
      </div>
      {issues.length ? (
        <section aria-labelledby="issues-heading" className="issues">
          <SectionHeading id="issues-heading" aside={<span className="caption section-count">{issues.length}</span>}>Compiler issues</SectionHeading>
          <ul>{issues.map((issue) => <li key={issueText(issue)}><code>{issueText(issue)}</code></li>)}</ul>
        </section>
      ) : null}

      <section aria-labelledby="artifacts-heading">
        <SectionHeading id="artifacts-heading" aside={<span className="caption section-count">6 files · JSON</span>}>Artifacts</SectionHeading>
        <ul className="artifacts">
          {artifactKinds.map(([label, suffix, description], index) => (
            <li className="artifact" key={label}>
              <span className="artifact-text">
                <strong>{label}</strong>
                <code>{key}.{suffix}.json</code>
                <small>{description}</small>
              </span>
              <button
                className={index === 0 ? 'button primary' : 'button'}
                type="button"
                disabled={demoMode || !ready}
                onClick={() => download(`${key}.${suffix}.json`, values[index])}
                aria-label={`Download ${label}${demoMode ? ' (simulated)' : ''}`}
              >
                <Download size={16} strokeWidth={1.75} aria-hidden="true" /> Download
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="coverage-heading" className="coverage">
        <SectionHeading id="coverage-heading">Coverage</SectionHeading>
        <dl className="coverage-list">
          <div><dt>Capabilities accounted for</dt><dd className="numeral">{decisions.length}</dd></div>
          <div><dt>Enabled decisions unresolved</dt><dd>{unresolved ? <Delta count={unresolved} accessibleLabel={plural(unresolved, 'open decision')} /> : <span className="numeral">0</span>}</dd></div>
          <div><dt>Graph nodes</dt><dd className="numeral">{blueprintResult?.graph.nodes.length ?? 0}</dd></div>
          <div><dt>Inert plan operations</dt><dd className="numeral">{result?.plan.operations.length ?? 0}</dd></div>
          <div className="is-wide"><dt>Graph SHA-256</dt><dd><code className="hash-full">{blueprintResult?.hashes.graph ?? 'not compiled'}</code></dd></div>
        </dl>
        <p className="notice">Export confirms deterministic local artifacts only. Manual, unsupported and tenant-verification work stays recorded in the Blueprint; nothing here has network or apply capability.</p>
      </section>

      <details className="json-preview">
        <summary>Blueprint V2 as JSON</summary>
        <pre>{JSON.stringify(blueprintResult?.project ?? project, null, 2)}</pre>
      </details>
    </section>
  )
}
