import { Copy } from 'lucide-react'
import { useStudio } from '../studio-state'

export function RevisionRail() {
  const { revision, blueprintResult } = useStudio()
  const graphIdentity = blueprintResult?.graph.graph_hash
  const graphLabel = graphIdentity?.slice(0, 12) ?? 'Awaiting local compile'
  const copyGraphIdentity = () => {
    if (graphIdentity) void navigator.clipboard?.writeText(graphIdentity)
  }
  return (
    <aside className="revision-rail" aria-label="Local revision details">
      <div className="revision-block">
        <span className="revision-label">Local revision</span>
        <strong>{revision}</strong>
      </div>
      <span className="revision-rule" aria-hidden="true" />
      <div className="revision-block graph-identity">
        <span className="revision-label">Graph ID</span>
        <code className="hash">{graphLabel}</code>
        <button
          className="revision-copy"
          type="button"
          aria-label="Copy graph identity"
          disabled={!graphIdentity}
          onClick={copyGraphIdentity}
        >
          <Copy size={15} />
        </button>
      </div>
    </aside>
  )
}
