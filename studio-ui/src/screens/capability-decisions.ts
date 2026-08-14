import type {
  CapabilityDecision,
  StudioProjectV2,
} from '../types'

function copiedDecisions(
  project: StudioProjectV2,
): Record<string, CapabilityDecision> {
  return Object.fromEntries(
    Object.entries(project.workbook.capability_decisions).map(([key, decision]) => [
      key,
      { ...decision },
    ]),
  )
}

function decisionFor(
  decisions: Record<string, CapabilityDecision>,
  capabilityId: string,
): CapabilityDecision | undefined {
  return Object.hasOwn(decisions, capabilityId)
    ? decisions[capabilityId]
    : undefined
}

function disableDecision(
  decisions: Record<string, CapabilityDecision>,
  capabilityId: string,
): void {
  const decision = decisionFor(decisions, capabilityId)
  if (!decision) return
  decision.enabled = false
  decision.completion = decision.delivery === 'unsupported' ? 'blocked' : 'decision_required'
  for (const [dependentId, dependent] of Object.entries(decisions)) {
    if (dependent.dependencies.includes(capabilityId)) {
      disableDecision(decisions, dependentId)
    }
  }
}

function enableDecision(
  decisions: Record<string, CapabilityDecision>,
  capabilityId: string,
): void {
  const decision = decisionFor(decisions, capabilityId)
  if (!decision) return
  decision.enabled = true
  for (const dependency of decision.dependencies) {
    enableDecision(decisions, dependency)
  }
  if (decision.delivery === 'unsupported') decision.completion = 'blocked'
}

export function replaceDecision(
  project: StudioProjectV2,
  id: string,
  patch: Partial<Pick<CapabilityDecision, 'enabled' | 'completion'>>,
): StudioProjectV2 {
  const source = project.workbook.capability_decisions
  if (!Object.hasOwn(source, id)) return project
  const decisions = copiedDecisions(project)
  const updatedTarget = decisionFor(decisions, id)
  if (patch.enabled !== undefined) {
    if (patch.enabled) enableDecision(decisions, id)
    else disableDecision(decisions, id)
  }
  if (patch.completion !== undefined && updatedTarget) {
    updatedTarget.completion = patch.completion
  }
  return {
    ...project,
    workbook: {
      ...project.workbook,
      capability_decisions: decisions,
    },
  }
}
