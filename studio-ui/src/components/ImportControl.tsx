import { Upload } from 'lucide-react'
import { useStudio } from '../editor/context'
import type { ChangeEvent } from 'react'

export function ImportControl({ compact = false }: { compact?: boolean }) {
  const { demoMode, importFiles } = useStudio()
  const onFiles = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.files?.length) void importFiles(event.target.files)
    event.target.value = ''
  }
  return (
    <label className={compact ? 'button quiet import-control compact' : 'import-control start-option'} aria-disabled={demoMode || undefined}>
      {compact ? <Upload size={16} strokeWidth={1.75} aria-hidden="true" /> : <span className="start-option-mark" aria-hidden="true">C</span>}
      <span className="import-control-text">
        {compact ? (demoMode ? 'Import (simulated)' : 'Import') : <><strong>Import JSON</strong><small>{demoMode ? 'Not available in the static demo.' : 'A profile and its manifest, a V1 project, or a Blueprint V2 document. Validated before it is saved.'}</small></>}
      </span>
      <input
        type="file"
        accept="application/json,.json"
        multiple
        onChange={onFiles}
        aria-label="Import project or profile bundle"
        disabled={demoMode}
      />
    </label>
  )
}
