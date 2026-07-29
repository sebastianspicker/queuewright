import {
  Download,
  ShieldCheck,
} from 'lucide-react'
import { useStudio } from '../studio-state'
import { PageHeader } from '../ui'
import { download } from './download'

function issueText(issue: string | { code: string; path: string; message: string }): string {
  return typeof issue === 'string' ? issue : `${issue.path}: ${issue.message}`
}

export function Review() {
  const {
    project,
    result,
    blueprint,
    blueprintResult,
    dirty,
    compileError,
    compiling,
    validateNow,
  } = useStudio()
  const ready = Boolean(result && blueprintResult) && !dirty && !compiling
  const decisions = Object.values(
    blueprint?.workbook.capability_decisions ?? {},
  )
  const unresolved = decisions.filter((decision) =>
    decision.enabled
    && (decision.completion === 'decision_required'
      || decision.completion === 'blocked'),
  ).length
  const artifacts: Array<[string, unknown]> = result
    ? [
        [
          `${project.profile.profile_key}.blueprint-v2.json`,
          blueprintResult?.project,
        ],
        [result.artifact_filenames.at(0) ?? '', result.project],
        [result.artifact_filenames.at(1) ?? '', result.profile],
        [result.artifact_filenames.at(2) ?? '', result.manifest],
        [result.artifact_filenames.at(3) ?? '', result.plan],
        [
          `${project.profile.profile_key}.configuration-graph.json`,
          blueprintResult?.graph,
        ],
      ]
    : []
  return (
    <section className="review-screen">
      <PageHeader
        title="Review and export"
        description="Only the latest authoritative local compilation can be downloaded."
        action={
          <button className="button primary" type="button" onClick={validateNow} disabled={compiling}>
            <ShieldCheck size={18} /> Validate design
          </button>
        }
      />
      <div className="review-grid">
        <div>
          <h2>Validation</h2>
          <p className={ready ? 'valid' : 'invalid'}>
            {ready
              ? 'Blueprint validated for local export'
              : compiling
                ? 'Validating…'
                : compileError ?? 'Edits are awaiting validation'}
          </p>
          {result?.issues.map((issue) => <p key={issueText(issue)}>{issueText(issue)}</p>)}
        </div>
        <div>
          <h2>Coverage</h2>
          <p>{decisions.length} capabilities accounted for</p>
          <p>{unresolved} enabled decisions unresolved</p>
          <p>{blueprintResult?.graph.nodes.length ?? 0} graph nodes</p>
        </div>
        <div>
          <h2>Symbolic plan</h2>
          <p>{result?.plan.operations.length ?? 0} inert operations</p>
          <p>No network or tenant apply capability</p>
          <p className="hash">SHA-256 {blueprintResult?.hashes.graph ?? 'awaiting compiler'}</p>
        </div>
      </div>
      <p className="notice">
        Export readiness confirms deterministic local artifacts only. Until
        validation succeeds, exports stay disabled. Manual, unsupported, and
        tenant verification work remains visible in the blueprint.
      </p>
      <details className="json-preview">
        <summary>Blueprint V2 JSON preview</summary>
        <pre>{JSON.stringify(blueprintResult?.project ?? blueprint, null, 2)}</pre>
      </details>
      <div className="export-list">
        {(['Blueprint', 'Project', 'Profile', 'Desired state', 'Inert plan', 'Configuration graph'] as const).map((label, index) => (
          <button
            className={index === 0 ? 'button primary' : 'button quiet'}
            type="button"
            disabled={!ready}
            onClick={() => {
              const artifact = artifacts.at(index)
              if (artifact) download(artifact[0], artifact[1])
            }}
            key={label}
          >
            <Download size={17} /> {label}
          </button>
        ))}
      </div>
    </section>
  )
}
