import type { FeatureDefinition, FeatureId, StudioProjectV2 } from '../../contracts'
import { cloneJson } from '../../contracts/runtime'
import { removeResourcesOwnedBy } from './feature-removal'
import { addFeatureResources } from './feature-resources'
import { finalize, mutateProject } from './mutate'

function featureStateFor(project: StudioProjectV2, id: FeatureId) {
  return new Map<FeatureId, StudioProjectV2['bundle']['feature_state'][FeatureId]>(
    Object.entries(project.bundle.feature_state) as Array<[FeatureId, StudioProjectV2['bundle']['feature_state'][FeatureId]]>,
  ).get(id)
}

export function toggleFeature(
  source: StudioProjectV2,
  featureId: FeatureId,
  enabled: boolean,
  catalog: FeatureDefinition[],
): StudioProjectV2 {
  const definitions = new Map(catalog.map((feature) => [feature.id, feature]))
  const next = cloneJson(source)
  const enable = (id: FeatureId) => {
    for (const dependency of definitions.get(id)?.dependencies ?? []) enable(dependency)
    const state = featureStateFor(next, id)
    if (!state) return
    state.enabled = true
    addFeatureResources(next.bundle, id)
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
    removeResourcesOwnedBy(next.bundle, id)
  }
  if (enabled) enable(featureId)
  else disable(featureId)
  return finalize(next)
}

/** Restore every feature to its catalog default settings and enabled state. */
export function resetFeatures(source: StudioProjectV2, catalog: FeatureDefinition[]): StudioProjectV2 {
  let next = mutateProject(source, (draft) => {
    for (const feature of catalog) {
      draft.bundle.feature_state[feature.id].settings = cloneJson(feature.defaultSettings)
    }
  })
  for (const feature of catalog) {
    next = toggleFeature(next, feature.id, feature.defaultEnabled || feature.locked, catalog)
  }
  return next
}
