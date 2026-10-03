import { describe, expect, it } from 'vitest'
import featureCatalogJson from '../../../queuewright/contracts/catalogs/features.json'
import { FEATURE_IDS } from '.'

describe('feature contract', () => {
  it('keeps FEATURE_IDS in step with the packaged feature catalog', () => {
    expect([...FEATURE_IDS].sort()).toEqual(featureCatalogJson.features.map((feature) => feature.id).sort())
  })
})
