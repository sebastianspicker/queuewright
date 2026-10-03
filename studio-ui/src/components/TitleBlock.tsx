import { Copy } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useStudio } from '../editor/context'
import { isLocallyValid, openDecisionCount, plural, storageLabel, validationLabel } from './status'
import { Delta } from './ui'

function Cell({ label, className, children }: { label: string; className?: string; children: ReactNode }) {
  return (
    <div className={className ? `tb-cell ${className}` : 'tb-cell'}>
      <dt className="caption">{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

/**
 * The drawing title block: every fact about this draft's identity and state,
 * in one place, with the stamp that says what it is not.
 */
export function TitleBlock() {
  const studio = useStudio()
  const { project, bundle, revision, blueprintResult, demoMode, storageStatus } = studio
  const [copied, setCopied] = useState(false)
  const copiedTimer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(copiedTimer.current), [])
  const graph = blueprintResult?.graph.graph_hash
  const groups = bundle.manifest.groups
  const units = groups.filter((group) => group.kind === 'container').length
  const services = groups.length - units
  const capabilities = Object.values(project.workbook.capability_decisions).filter((decision) => decision.enabled).length
  const open = openDecisionCount(project)
  const valid = isLocallyValid(studio)
  const copy = () => {
    if (!graph) return
    void navigator.clipboard?.writeText(graph).then(() => {
      setCopied(true)
      window.clearTimeout(copiedTimer.current)
      copiedTimer.current = window.setTimeout(() => setCopied(false), 1600)
    }).catch(() => { setCopied(false) })
  }
  return (
    <footer className="title-block" aria-label="Title block">
      <dl>
        <Cell label="Project" className="tb-project"><span className="tb-truncate">{project.name}</span></Cell>
        <Cell label="Schema" className="tb-schema"><span className="numeral tb-figure">{project.target_schema_version}</span></Cell>
        <Cell label="Revision" className="tb-revision"><span className="numeral tb-figure">{revision}</span></Cell>
        <Cell label="Graph" className="tb-graph">
          <code className="tb-hash" title={graph}>{graph ? graph.slice(0, 12) : 'not compiled'}</code>
          <button
            className="tb-copy"
            type="button"
            disabled={!graph}
            onClick={copy}
            aria-label={copied ? 'Graph identity copied' : 'Copy full graph identity'}
          >
            <Copy size={13} strokeWidth={1.75} aria-hidden="true" />
          </button>
        </Cell>
        <Cell label="Contents" className="tb-contents">
          {plural(units, 'unit')} · {plural(services, 'service')} · {plural(capabilities, 'capability', 'capabilities')}
        </Cell>
        <Cell label="Decisions" className="tb-decisions">
          {open ? <Delta count={open} label="open" /> : <span className="tb-quiet">none open</span>}
        </Cell>
        <Cell label="Storage" className={storageStatus === 'error' ? 'tb-storage is-error' : 'tb-storage'}>
          <span role="status">{storageLabel(studio)}</span>
        </Cell>
        <Cell label="Validation" className={valid && !demoMode ? 'tb-validation is-valid' : studio.compileError ? 'tb-validation is-error' : 'tb-validation'}>
          <span role="status" className="tb-truncate">{validationLabel(studio)}</span>
        </Cell>
      </dl>
      <p className="tb-stamp">
        {demoMode
          ? <><strong>Static demo</strong><span className="tb-stamp-long">Every action is simulated</span><span className="tb-stamp-short">Simulated</span></>
          : <><strong>Local design</strong><span className="tb-stamp-long">Not applied to any tenant</span><span className="tb-stamp-short">Not applied</span></>}
      </p>
    </footer>
  )
}
