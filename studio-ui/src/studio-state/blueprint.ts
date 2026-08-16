import { StudioApiError } from '../api'
import type { StudioProjectV2 } from '../types'

export function compileMessage(error: unknown): string {
  if (error instanceof DOMException && error.name === 'AbortError') return ''
  if (error instanceof StudioApiError) return `${error.path}: ${error.message}`
  return 'Loopback compiler unavailable. Exports stay disabled.'
}

export function rebaseBlueprint(
  migrated: StudioProjectV2,
  previous?: StudioProjectV2,
): StudioProjectV2 {
  if (!previous || previous.id !== migrated.id) return migrated
  const editableDecisions = new Map(
    Object.entries(previous.workbook.capability_decisions),
  )
  const capabilityDecisions = Object.fromEntries(
    Object.entries(migrated.workbook.capability_decisions).map(([id, pinned]) => {
      const editable = editableDecisions.get(id)
      return [
        id,
        editable
          ? { ...pinned, enabled: editable.enabled, completion: editable.completion }
          : pinned,
      ]
    }),
  )
  return {
    ...migrated,
    workbook: {
      ...migrated.workbook,
      organization: previous.workbook.organization,
      capability_decisions: capabilityDecisions,
    },
    extensions: previous.extensions,
  }
}
