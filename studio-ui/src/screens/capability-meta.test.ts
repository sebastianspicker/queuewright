import type { CapabilityDecision, StudioProjectV2 } from '../types'
import { replaceDecision } from './capability-meta'

function projectWithDecisions(): StudioProjectV2 {
  return {
    project_schema_version: '2.0',
    id: 'test-project',
    name: 'Test project',
    target_schema_version: '1.1',
    workbook: {
      organization: {},
      services: [],
      policies: {},
      capability_decisions: {
        prerequisite: {
          completion: 'ready',
          delivery: 'automated',
          risk: 'low',
          dependencies: [],
          enabled: false,
        },
        dependent: {
          completion: 'ready',
          delivery: 'guided_manual',
          risk: 'medium',
          dependencies: ['prerequisite'],
          enabled: true,
        },
        unsupported: {
          completion: 'ready',
          delivery: 'unsupported',
          risk: 'high',
          dependencies: [],
          enabled: false,
        },
      },
      uat: {},
    },
    extensions: {},
    bundle: {
      profile: {} as StudioProjectV2['bundle']['profile'],
      manifest: {} as StudioProjectV2['bundle']['manifest'],
      resource_ownership: {},
      feature_state: {} as StudioProjectV2['bundle']['feature_state'],
    },
  }
}

describe('capability metadata facade', () => {
  it('disables dependents and resets their completion state', () => {
    const project = projectWithDecisions()
    const next = replaceDecision(project, 'prerequisite', { enabled: false })

    expect(next).not.toBe(project)
    expect(next.workbook.capability_decisions.dependent).toMatchObject({
      enabled: false,
      completion: 'decision_required',
    })
  })

  it('enables prerequisites and keeps unsupported capabilities blocked', () => {
    const project = projectWithDecisions()
    const dependent = replaceDecision(project, 'dependent', { enabled: true })
    const unsupported = replaceDecision(project, 'unsupported', { enabled: true })

    expect(dependent.workbook.capability_decisions.prerequisite.enabled).toBe(true)
    expect(unsupported.workbook.capability_decisions.unsupported).toMatchObject({
      enabled: true,
      completion: 'blocked',
    })
  })

  it('keeps the original object for an unknown decision', () => {
    const project = projectWithDecisions()

    expect(replaceDecision(project, 'missing', { enabled: true })).toBe(project)
  })

  it('updates an own prototype-like decision without traversing inheritance', () => {
    const project = projectWithDecisions()
    const prototypeLikeDecision: CapabilityDecision = {
      completion: 'ready',
      delivery: 'automated',
      risk: 'low',
      dependencies: [],
      enabled: false,
    }
    Object.defineProperty(project.workbook.capability_decisions, '__proto__', {
      configurable: true,
      enumerable: true,
      value: prototypeLikeDecision,
      writable: true,
    })

    const next = replaceDecision(project, '__proto__', { enabled: true })
    const nextDecision = Object.getOwnPropertyDescriptor(
      next.workbook.capability_decisions,
      '__proto__',
    )?.value as CapabilityDecision

    expect(nextDecision.enabled).toBe(true)
    expect(Object.getPrototypeOf(next.workbook.capability_decisions)).toBe(Object.prototype)
  })

  it('rejects an inherited __proto__ decision', () => {
    const project = projectWithDecisions()
    const inheritedDecisions = Object.create(null) as Record<string, CapabilityDecision>
    Object.defineProperty(inheritedDecisions, '__proto__', {
      configurable: true,
      enumerable: true,
      value: {
        completion: 'ready',
        delivery: 'automated',
        risk: 'low',
        dependencies: [],
        enabled: false,
      } satisfies CapabilityDecision,
      writable: true,
    })
    project.workbook.capability_decisions = Object.create(inheritedDecisions)

    expect(replaceDecision(project, '__proto__', { enabled: true })).toBe(project)
  })
})
