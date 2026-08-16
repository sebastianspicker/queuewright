import { Upload } from 'lucide-react'
import { useStudio } from '../studio-state'
import type { ChangeEvent } from 'react'

export function ImportControl({ compact = false }: { compact?: boolean }) {
  const { demoMode, importFiles } = useStudio()
  const onFiles = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.files?.length) void importFiles(event.target.files)
    event.target.value = ''
  }
  return (
    <label className={compact ? 'button quiet import-control compact' : 'button quiet import-control'}>
      <Upload size={18} aria-hidden="true" />
      <span>{demoMode ? 'Import (simulated)' : 'Import'}</span>
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
