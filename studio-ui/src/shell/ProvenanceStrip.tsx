import { useStudio } from '../studio-state'

export function ProvenanceStrip() {
  const { revision, blueprintResult, blueprint } = useStudio()
  const graphHash = blueprintResult?.graph.graph_hash
  const hashLabel = graphHash?.slice(0, 12) ?? 'awaiting'
  const openDecisions = Object.values(
    blueprint?.workbook.capability_decisions ?? {},
  ).filter((decision) =>
    decision.enabled
    && (decision.completion === 'decision_required'
      || decision.completion === 'blocked'),
  ).length

  return (
    <div className="provenance" aria-label="Design provenance">
      <span className="chip local">
        <span className="dot" aria-hidden="true" />
        Local design only
      </span>
      <span className="prov-item">
        <span className="chip neutral">Not connected to a tenant</span>
      </span>
      <span className="prov-item">
        Revision <strong>{revision}</strong>
      </span>
      <span className="prov-item">
        <span className="hash">graph · {hashLabel}</span>
      </span>
      {openDecisions > 0 ? (
        <span className="prov-item">
          <span className="chip warn">
            <span className="dot" aria-hidden="true" />
            {openDecisions} {openDecisions === 1 ? 'decision' : 'decisions'} open
          </span>
        </span>
      ) : null}
      <span className="prov-spacer" />
      <span className="prov-hint">
        Drafts stay in this browser · <em>design-ready ≠ applied</em>
      </span>
    </div>
  )
}
