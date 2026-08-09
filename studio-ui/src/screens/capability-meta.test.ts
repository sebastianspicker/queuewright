import type { StudioProjectV2 } from '../types'
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
})
