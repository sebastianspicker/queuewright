import capabilityCatalogJson from '../../../studio/catalog/capabilities.json'
import featureCatalogJson from '../../../studio/catalog/features.json'
import {
  FEATURE_IDS,
  type CapabilityDefinition,
  type FeatureDefinition,
  type FeatureId,
  type JsonValue,
} from '../types'

export const steps = [
  ['start', 'Start'],
  ['organization', 'Organization'],
  ['structure', 'Services'],
  ['access', 'Access'],
  ['features', 'Policies'],
  ['governance', 'Governance'],
  ['test-data', 'Readiness'],
  ['review', 'Review'],
] as const

export const bundledCapabilities = (
  capabilityCatalogJson.capabilities as CapabilityDefinition[]
).map((capability) => ({
  ...capability,
  dependencies: [...capability.dependencies],
}))

interface CatalogFeatureJson {
  id: FeatureId
  name: string
  description: string
  category: string
  dependencies: FeatureId[]
  locked_assurances: string[]
  locked: boolean
  default_enabled: boolean
  settings: Record<string, JsonValue>
}

const catalogFeatures = featureCatalogJson.features as CatalogFeatureJson[]

export const bundledCatalog: FeatureDefinition[] = FEATURE_IDS.map((id) => {
  const feature = catalogFeatures.find((item) => item.id === id)
  if (!feature) throw new Error(`Bundled feature catalog is missing ${id}`)
  return {
    id,
    name: feature.name,
    description: feature.description,
    category: feature.category,
    dependencies: [...feature.dependencies],
    lockedAssurances: [...feature.locked_assurances],
    locked: feature.locked,
    defaultEnabled: feature.default_enabled,
    defaultSettings: clone(feature.settings),
  }
})

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}
