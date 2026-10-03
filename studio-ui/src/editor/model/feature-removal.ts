import type {
  FeatureId,
  KeyedResource,
  StudioBundle,
} from '../../contracts'
import { objectFieldCollections, objectFields, replaceObjectFields } from './object-fields'

function filterOwnedResources(collection: string, items: KeyedResource[], owned: Set<string>): KeyedResource[] {
  return items.filter((item) => !owned.has(`${collection}:${item.key}`))
}

function removeOwnedCollections(project: StudioBundle, owned: Set<string>): void {
  project.manifest.overviews = filterOwnedResources('overviews', project.manifest.overviews, owned)
  project.manifest.macros = filterOwnedResources('macros', project.manifest.macros, owned)
  project.manifest.checklist_templates = filterOwnedResources('checklist_templates', project.manifest.checklist_templates, owned)
  project.manifest.triggers = filterOwnedResources('triggers', project.manifest.triggers, owned)
  project.manifest.jobs = filterOwnedResources('jobs', project.manifest.jobs, owned)
  project.manifest.report_profiles = filterOwnedResources('report_profiles', project.manifest.report_profiles, owned)
}

function actionTags(resources: KeyedResource[]): string[] {
  return resources
    .flatMap((resource) => Array.isArray(resource.actions) ? resource.actions : [])
    .filter((action): action is string => typeof action === 'string' && action.startsWith('add_tag:'))
    .map((action) => action.slice('add_tag:'.length))
}

function scenarioTags(project: StudioBundle): string[] {
  return project.profile.uat.scenarios
    .flatMap((scenario) => Array.isArray(scenario.expected_tags) ? scenario.expected_tags : [])
    .filter((tag): tag is string => typeof tag === 'string')
}

function referencedTags(project: StudioBundle): Set<string> {
  const resources = [
    ...project.manifest.macros,
    ...project.manifest.triggers,
    ...project.manifest.jobs,
  ]
  return new Set([...actionTags(resources), ...scenarioTags(project)])
}

function replacementTag(project: StudioBundle, removedTags: Set<string>): string | undefined {
  const retainedTags = project.manifest.tags.filter((tag) => !removedTags.has(tag))
  return retainedTags.find((tag) => tag.endsWith('/uat')) ?? retainedTags[0]
}

function replaceRemovedTags(project: StudioBundle, removedTags: Set<string>): void {
  const fallbackTag = replacementTag(project, removedTags)
  for (const scenario of project.profile.uat.scenarios) {
    if (!Array.isArray(scenario.expected_tags)) continue
    const remaining = scenario.expected_tags.filter(
      (tag): tag is string => typeof tag === 'string' && !removedTags.has(tag),
    )
    if (remaining.length === 0 && fallbackTag) remaining.push(fallbackTag)
    scenario.expected_tags = remaining
  }
}

function ownedResourceIds(project: StudioBundle, owner: FeatureId): Set<string> {
  return new Set(
    Object.entries(project.resource_ownership)
      .filter(([, value]) => value === owner)
      .map(([id]) => id),
  )
}

function removeOwnedFields(project: StudioBundle, owned: Set<string>): void {
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

function removeFeatureProbes(project: StudioBundle, owner: FeatureId): void {
  if (owner === 'cross_department_handoff') delete project.profile.uat.handoff_probe
  if (owner === 'scheduled_reviews') delete project.profile.uat.job_probe
  if (owner === 'sensitive_area_handling') {
    for (const group of project.manifest.groups) delete group.restricted
  }
}

export function removeResourcesOwnedBy(project: StudioBundle, owner: FeatureId): void {
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
}
