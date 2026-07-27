import {
  Box,
  Building2,
  Laptop,
  RefreshCw,
  ShieldCheck,
  Tag,
} from 'lucide-react'
import { useStudio } from '../studio-state'
import type { ReactNode } from 'react'

function StatusItem({ children }: { children: ReactNode }) {
  return <span className="status-item">{children}</span>
}

export function StatusRail() {
  const {
    project,
    blueprint,
    blueprintResult,
    result,
    dirty,
    compiling,
    compileError,
    storageStatus,
  } = useStudio()
  const units = Math.max(0, project.manifest.groups.length - 1)
  const services = project.manifest.groups.filter((group) => group.kind === 'leaf').length
  const decisions = Object.values(
    blueprint?.workbook.capability_decisions ?? {},
  )
  const capabilities = decisions.filter((decision) => decision.enabled).length
  const openDecisions = decisions.filter((decision) =>
    decision.enabled
    && (decision.completion === 'decision_required'
      || decision.completion === 'blocked'),
  ).length
  return (
    <footer className="status-rail">
      <StatusItem><Laptop size={21} /> Local only</StatusItem>
      <StatusItem><RefreshCw size={20} /> {storageStatus === 'error' ? 'Browser save failed' : storageStatus === 'saved' ? 'Saved locally' : 'Saving locally…'}</StatusItem>
      <StatusItem><Building2 size={20} /> {units} units</StatusItem>
      <StatusItem><Tag size={20} /> {services} services</StatusItem>
      <StatusItem><Box size={20} /> {capabilities} capabilities</StatusItem>
      {openDecisions > 0 ? (
        <StatusItem>
          <ShieldCheck className="status-muted" size={21} />
          {openDecisions} open decisions
        </StatusItem>
      ) : null}
      <StatusItem>
        <ShieldCheck
          className={result && blueprintResult && !dirty ? 'status-good' : 'status-muted'}
          size={21}
        />
        {compiling
          ? 'Validating…'
          : result && blueprintResult && !dirty
            ? 'Local blueprint valid'
            : compileError ?? 'Validation required'}
      </StatusItem>
    </footer>
  )
}
