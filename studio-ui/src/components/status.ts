import type { useStudio } from '../editor/context'

type Studio = ReturnType<typeof useStudio>

/** Enabled capability decisions that still need an owner decision or are blocked. */
export function openDecisionCount(project: Studio['project']): number {
  return Object.values(project.workbook.capability_decisions).filter(
    (decision) => decision.enabled
      && (decision.completion === 'decision_required' || decision.completion === 'blocked'),
  ).length
}

export function isLocallyValid(studio: Pick<Studio, 'result' | 'blueprintResult' | 'dirty' | 'compiling'>): boolean {
  return Boolean(studio.result && studio.blueprintResult) && !studio.dirty && !studio.compiling
}

export function storageLabel(studio: Pick<Studio, 'demoMode' | 'hydrated' | 'storageStatus'>): string {
  if (studio.demoMode) return 'Not saved; resets on reload'
  if (!studio.hydrated || studio.storageStatus === 'loading') return 'Opening browser projects…'
  if (studio.storageStatus === 'saving' || studio.storageStatus === 'pending') return 'Saving in this browser…'
  if (studio.storageStatus === 'error') return 'Browser save failed'
  return 'Saved in this browser'
}

export function validationLabel(studio: Pick<Studio, 'demoMode' | 'compiling' | 'compileError' | 'result' | 'blueprintResult' | 'dirty'>): string {
  if (studio.demoMode) return 'Simulated only'
  if (studio.compiling) return 'Validating…'
  if (isLocallyValid(studio)) return 'Locally valid'
  return studio.compileError ?? 'Needs validation'
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`
}
