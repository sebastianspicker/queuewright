import { bundledCatalog } from '../data'
import type { FeatureDefinition, FeatureId, StudioProject } from '../types'
import { removeResourcesOwnedBy } from './feature-removal'
import { addFeatureResources } from './feature-resources'
import { clone, finalize } from './mutate'

function featureStateFor(project: StudioProject, id: FeatureId) {
  return new Map<FeatureId, StudioProject['feature_state'][FeatureId]>(
    Object.entries(project.feature_state) as Array<[FeatureId, StudioProject['feature_state'][FeatureId]]>,
  ).get(id)
}

export function toggleFeature(
  source: StudioProject,
  featureId: FeatureId,
  enabled: boolean,
  catalog: FeatureDefinition[] = bundledCatalog,
): StudioProject {
  const definitions = new Map(catalog.map((feature) => [feature.id, feature]))
  const next = clone(source)
  const enable = (id: FeatureId) => {
    for (const dependency of definitions.get(id)?.dependencies ?? []) enable(dependency)
    const state = featureStateFor(next, id)
    if (!state) return
    state.enabled = true
    addFeatureResources(next, id)
  }
  const disable = (id: FeatureId) => {
    if (definitions.get(id)?.locked) return
    for (const dependent of catalog) {
      if (dependent.dependencies.includes(id) && featureStateFor(next, dependent.id)?.enabled) {
        disable(dependent.id)
      }
    }
    const state = featureStateFor(next, id)
    if (!state) return
    state.enabled = false
    removeResourcesOwnedBy(next, id)
  }
  if (enabled) enable(featureId)
  else disable(featureId)
  return finalize(next, next.resource_ownership)
}
