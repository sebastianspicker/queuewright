import type { CatalogFeature, FeatureDefinition, StudioProjectV1, StudioProjectV2 } from '.'

export function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

export function isV1Project(value: unknown): value is StudioProjectV1 {
  return typeof value === 'object' && value !== null
    && (value as { project_schema_version?: unknown }).project_schema_version === '1.0'
}

export function isV2Project(value: unknown): value is StudioProjectV2 {
  return typeof value === 'object' && value !== null
    && (value as { project_schema_version?: unknown }).project_schema_version === '2.0'
}

/** Map a snake_case catalog entry (API response or bundled JSON) to the editor's definition. */
export function featureDefinition(feature: CatalogFeature): FeatureDefinition {
  return {
    id: feature.id, name: feature.name, description: feature.description,
    category: feature.category, dependencies: [...feature.dependencies],
    lockedAssurances: [...feature.locked_assurances], locked: feature.locked,
    defaultEnabled: feature.default_enabled, defaultSettings: cloneJson(feature.settings),
  }
}
