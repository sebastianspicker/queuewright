import type { StepId } from '../contracts'

export const steps = [
  ['start', 'Start'],
  ['organization', 'Organization'],
  ['structure', 'Services'],
  ['access', 'Access'],
  ['features', 'Policies'],
  ['governance', 'Governance'],
  ['test-data', 'Readiness'],
  ['review', 'Review'],
] as const

export const phases: Array<{ label: string; steps: StepId[] }> = [
  { label: 'Frame', steps: ['start', 'organization'] },
  { label: 'Design', steps: ['structure', 'access', 'features'] },
  { label: 'Assure', steps: ['governance', 'test-data', 'review'] },
]

export interface Sheet {
  id: StepId
  label: string
  number: string
  index: number
  phase: string
}

export const sheetCount = String(steps.length).padStart(2, '0')

export function sheetFor(id: StepId): Sheet {
  const index = Math.max(0, steps.findIndex(([candidate]) => candidate === id))
  return {
    id,
    label: steps[index][1],
    number: String(index + 1).padStart(2, '0'),
    index,
    phase: phases.find((phase) => phase.steps.includes(id))?.label ?? '',
  }
}
