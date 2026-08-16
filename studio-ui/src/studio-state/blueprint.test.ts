import type { CapabilityDecision, StudioProjectV2 } from '../types'
import { rebaseBlueprint } from './blueprint'

function decision(overrides: Partial<CapabilityDecision> = {}): CapabilityDecision {
  return {
    completion: 'ready',
    delivery: 'automated',
    risk: 'low',
    dependencies: [],
    enabled: true,
    ...overrides,
  }
}

function project(
  decisions: Record<string, CapabilityDecision>,
  organization: StudioProjectV2['workbook']['organization'],
  extensions: StudioProjectV2['extensions'],
): StudioProjectV2 {
  return {
    project_schema_version: '2.0',
    id: 'test-project',
    name: 'Test project',
    target_schema_version: '1.1',
    workbook: {
      organization,
      services: [],
      policies: {},
      capability_decisions: decisions,
      uat: {},
    },
    extensions,
    bundle: {
      profile: {} as StudioProjectV2['bundle']['profile'],
      manifest: {} as StudioProjectV2['bundle']['manifest'],
      resource_ownership: {},
      feature_state: {} as StudioProjectV2['bundle']['feature_state'],
    },
  }
}

describe('rebaseBlueprint', () => {
  it('preserves editable fields for own capability decisions', () => {
    const migrated = project(
      { known: decision({ enabled: true, completion: 'ready', risk: 'high' }) },
      {},
      {},
    )
    const previous = project(
      { known: decision({ enabled: false, completion: 'blocked', risk: 'low' }) },
      {},
      {},
    )

    const rebased = rebaseBlueprint(migrated, previous)

    expect(rebased.workbook.capability_decisions.known).toMatchObject({
      enabled: false,
      completion: 'blocked',
      risk: 'high',
    })
  })

  it('does not rebase from inherited capability decisions', () => {
    const previousDecisions = Object.create({
      inherited: decision({ enabled: false, completion: 'blocked' }),
    }) as Record<string, CapabilityDecision>
    const migrated = project(
      { inherited: decision({ enabled: true, completion: 'ready' }) },
      { source: 'migrated' },
      { source: 'migrated' },
    )
    const previous = project(
      previousDecisions,
      { source: 'previous' },
      { source: 'previous' },
    )

    const rebased = rebaseBlueprint(migrated, previous)

    expect(rebased.workbook.capability_decisions.inherited).toMatchObject({
      enabled: true,
      completion: 'ready',
    })
    expect(rebased.workbook.organization).toEqual({ source: 'previous' })
    expect(rebased.extensions).toEqual({ source: 'previous' })
  })

  it('rebases an own __proto__ decision without changing the result prototype', () => {
    const migratedDecisions = {} as Record<string, CapabilityDecision>
    const previousDecisions = {} as Record<string, CapabilityDecision>
    Object.defineProperty(migratedDecisions, '__proto__', {
      configurable: true,
      enumerable: true,
      value: decision({ enabled: true, completion: 'ready' }),
      writable: true,
    })
    Object.defineProperty(previousDecisions, '__proto__', {
      configurable: true,
      enumerable: true,
      value: decision({ enabled: false, completion: 'blocked' }),
      writable: true,
    })
    const migrated = project(migratedDecisions, {}, {})
    const previous = project(previousDecisions, {}, {})

    const rebased = rebaseBlueprint(migrated, previous)
    const rebasedDecision = Object.getOwnPropertyDescriptor(
      rebased.workbook.capability_decisions,
      '__proto__',
    )?.value as CapabilityDecision

    expect(rebasedDecision).toMatchObject({ enabled: false, completion: 'blocked' })
    expect(Object.getPrototypeOf(rebased.workbook.capability_decisions)).toBe(Object.prototype)
  })
})
