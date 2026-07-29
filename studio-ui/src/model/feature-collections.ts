import type { KeyedResource, StudioProject } from '../types'

function filterOwnedResources(collection: string, items: KeyedResource[], owned: Set<string>): KeyedResource[] {
  return items.filter((item) => !owned.has(`${collection}:${item.key}`))
}

export function removeOwnedCollections(project: StudioProject, owned: Set<string>): void {
  project.manifest.overviews = filterOwnedResources('overviews', project.manifest.overviews, owned)
  project.manifest.macros = filterOwnedResources('macros', project.manifest.macros, owned)
  project.manifest.checklist_templates = filterOwnedResources('checklist_templates', project.manifest.checklist_templates, owned)
  project.manifest.triggers = filterOwnedResources('triggers', project.manifest.triggers, owned)
  project.manifest.jobs = filterOwnedResources('jobs', project.manifest.jobs, owned)
  project.manifest.report_profiles = filterOwnedResources('report_profiles', project.manifest.report_profiles, owned)
}
