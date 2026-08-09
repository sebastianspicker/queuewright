import {
  blankProject,
  bundledCatalog,
  exampleProject,
  ownerForResource,
  resourceIds,
} from './data'
import { FEATURE_IDS } from './types'

describe('data facade', () => {
  it('exports the catalog in feature-id order with independent defaults', () => {
    expect(bundledCatalog.map((feature) => feature.id)).toEqual(FEATURE_IDS)
    expect(bundledCatalog.every((feature) => feature.defaultSettings)).toBe(true)
  })

  it('creates an isolated draft with the documented local namespace', () => {
    const project = blankProject()

    expect(project.target_schema_version).toBe('1.1')
    expect(project.profile.profile_key).toBe('queuewright_draft')
    expect(project.manifest.technical_namespace).toBe('queuewright_draft_')
    expect(project.manifest.tags).toEqual(['queuewright_draft/uat'])
  })

  it('keeps resource ids sorted and uses the original ownership rules', () => {
    const project = exampleProject()
    const ids = resourceIds(project.profile, project.manifest)

    expect(ids).toEqual([...ids].sort())
    expect(ownerForResource('object_manager_fields:unknown')).toBe('ticket_fields')
    expect(ownerForResource('tags:any/uat')).toBe('access_matrix')
  })
})
