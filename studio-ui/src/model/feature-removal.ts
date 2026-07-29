import type {
  FeatureId,
  KeyedResource,
  ResourceOwner,
  StudioProject,
} from '../types'
import { removeOwnedCollections } from './feature-collections'
import { referencedTags } from './feature-tags'
import { replaceRemovedTags } from './feature-tag-removal'
import { objectFields, type ObjectFieldCollection } from './object-field-reader'
import { replaceObjectFields } from './object-field-writer'
const objectFieldCollections: ObjectFieldCollection[] = [
  'ticket_fields',
  'user_fields',
  'organization_fields',
  'group_fields',
]

function ownedResourceIds(project: StudioProject, owner: FeatureId): Set<string> {
  return new Set(
    Object.entries(project.resource_ownership)
      .filter(([, value]) => value === owner)
      .map(([id]) => id),
  )
}

function removeOwnedFields(project: StudioProject, owned: Set<string>): void {
  const removedLogicalNames = new Set(objectFieldCollections.flatMap((collection) =>
    objectFields(project, collection)
      .filter((field) => owned.has(`object_manager_fields:${field.name}`))
      .map((field) => field.name.replace(project.manifest.technical_namespace, '')),
  ))
  for (const collection of objectFieldCollections) {
    replaceObjectFields(project, collection, objectFields(project, collection).filter(
      (field) => !owned.has(`object_manager_fields:${field.name}`),
    ))
  }
  project.profile.uat.scenarios = project.profile.uat.scenarios.map((scenario) =>
    Object.fromEntries(Object.entries(scenario).filter(([key]) => !removedLogicalNames.has(key))) as KeyedResource,
  )
}

function removeFeatureProbes(project: StudioProject, owner: FeatureId): void {
  if (owner === 'cross_department_handoff') delete project.profile.uat.handoff_probe
  if (owner === 'scheduled_reviews') delete project.profile.uat.job_probe
  if (owner === 'sensitive_area_handling') {
    for (const group of project.manifest.groups) delete group.restricted
  }
}

function ownershipAfterFeatureRemoval(id: string): ResourceOwner {
  if (['groups:', 'organizations:', 'roles:', 'core_workflows:'].some((prefix) => id.startsWith(prefix))) return 'core'
  return id.startsWith('uat_scenarios:') ? 'access_matrix' : 'custom'
}

function restoreOwnership(project: StudioProject, owner: FeatureId): void {
  project.resource_ownership = Object.fromEntries(
    Object.entries(project.resource_ownership).map(([id, value]) => value === owner ? [id, ownershipAfterFeatureRemoval(id)] : [id, value]),
  )
}

export function removeResourcesOwnedBy(project: StudioProject, owner: FeatureId): void {
  const owned = ownedResourceIds(project, owner)
  removeOwnedCollections(project, owned)
  const candidateTags = new Set(project.manifest.tags.filter((tag) => owned.has(`tags:${tag}`)))
  replaceRemovedTags(project, candidateTags)
  removeOwnedFields(project, owned)
  removeFeatureProbes(project, owner)
  const retainedTags = referencedTags(project)
  project.manifest.tags = project.manifest.tags.filter(
    (tag) => !candidateTags.has(tag) || retainedTags.has(tag),
  )
  restoreOwnership(project, owner)
}
