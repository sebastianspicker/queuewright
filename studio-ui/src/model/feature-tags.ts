import type { KeyedResource, StudioProject } from '../types'

function actionTags(resources: KeyedResource[]): string[] {
  return resources
    .flatMap((resource) => Array.isArray(resource.actions) ? resource.actions : [])
    .filter((action): action is string => typeof action === 'string' && action.startsWith('add_tag:'))
    .map((action) => action.slice('add_tag:'.length))
}

function scenarioTags(project: StudioProject): string[] {
  return project.profile.uat.scenarios
    .flatMap((scenario) => Array.isArray(scenario.expected_tags) ? scenario.expected_tags : [])
    .filter((tag): tag is string => typeof tag === 'string')
}

export function referencedTags(project: StudioProject): Set<string> {
  const resources = [
    ...project.manifest.macros,
    ...project.manifest.triggers,
    ...project.manifest.jobs,
  ]
  return new Set([...actionTags(resources), ...scenarioTags(project)])
}
