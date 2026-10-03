import featureCatalogJson from '../../../queuewright/contracts/catalogs/features.json'
import {
  FEATURE_IDS,
  type CatalogFeature,
  type FeatureDefinition,
} from '../contracts'
import { featureDefinition } from '../contracts/runtime'

const catalogFeatures = featureCatalogJson.features as CatalogFeature[]

export const bundledCatalog: FeatureDefinition[] = FEATURE_IDS.map((id) => {
  const feature = catalogFeatures.find((item) => item.id === id)
  if (!feature) throw new Error(`Bundled feature catalog is missing ${id}`)
  return featureDefinition(feature)
})
