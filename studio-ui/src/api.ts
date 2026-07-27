import { FEATURE_IDS } from './types'
import type {
  ApiError,
  BlueprintCompileResult,
  CatalogResponse,
  CompileResult,
  FeatureDefinition,
  FeatureId,
  ManifestDocument,
  ProfileDocument,
  StudioApi,
  StudioProject,
  StudioProjectV2,
} from './types'

export class StudioApiError extends Error {
  readonly code: string
  readonly path: string
  readonly status: number

  constructor(status: number, error: ApiError) {
    super(error.message)
    this.name = 'StudioApiError'
    this.status = status
    this.code = error.code
    this.path = error.path
  }
}

function isFeatureId(value: string): value is FeatureId {
  return (FEATURE_IDS as readonly string[]).includes(value)
}

async function json<T>(response: Response): Promise<T> {
  const body = (await response.json()) as T | ApiError
  if (!response.ok) {
    const error = body as ApiError
    throw new StudioApiError(response.status, {
      code: error.code ?? 'request_failed',
      path: error.path ?? 'request',
      message: error.message ?? `Local qWright request failed (${response.status})`,
    })
  }
  return body as T
}

export const api: StudioApi = {
  async loadCatalog(signal?: AbortSignal): Promise<FeatureDefinition[]> {
    const response = await fetch('/api/v1/catalog', { signal })
    const catalog = await json<CatalogResponse>(response)
    return catalog.features.flatMap((feature) =>
      isFeatureId(feature.id)
        ? [{
            id: feature.id,
            name: feature.name,
            description: feature.description,
            category: feature.category,
            dependencies: feature.dependencies,
            lockedAssurances: feature.locked_assurances,
            locked: feature.locked,
            defaultEnabled: feature.default_enabled,
            defaultSettings: feature.settings,
          }]
        : [],
    )
  },

  async importBundle(
    profile: ProfileDocument,
    manifest: ManifestDocument,
    signal?: AbortSignal,
  ): Promise<StudioProject> {
    const response = await fetch('/api/v1/import-bundle', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ profile, manifest }),
      signal,
    })
    const imported = await json<{ project: StudioProject }>(response)
    return imported.project
  },

  async compile(
    project: StudioProject,
    signal?: AbortSignal,
  ): Promise<CompileResult> {
    const response = await fetch('/api/v1/compile-project', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ project }),
      signal,
    })
    return json<CompileResult>(response)
  },

  async migrateProject(
    project: StudioProject,
    signal?: AbortSignal,
  ): Promise<StudioProjectV2> {
    const response = await fetch('/api/v2/migrate-project', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ project }),
      signal,
    })
    const migrated = await json<{ project: StudioProjectV2 }>(response)
    return migrated.project
  },

  async compileBlueprint(
    project: StudioProjectV2,
    signal?: AbortSignal,
  ): Promise<BlueprintCompileResult> {
    const response = await fetch('/api/v2/compile-project', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ project }),
      signal,
    })
    return json<BlueprintCompileResult>(response)
  },
}
