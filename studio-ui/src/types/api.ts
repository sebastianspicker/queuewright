import type { BlueprintCompileResult, StudioProjectV2, SymbolicPlan, CompileSummary } from './blueprint'
import type { FeatureId, JsonValue } from './features'
import type { ManifestDocument, ProfileDocument, StudioProject } from './project'

export interface CompileResult {
  artifact_filenames: [string, string, string, string]
  hashes: Record<'manifest' | 'plan' | 'profile' | 'project', string>
  issues: Array<{ code: string; path: string; message: string } | string>
  manifest: ManifestDocument
  plan: SymbolicPlan
  profile: ProfileDocument
  project: StudioProject
  summary: CompileSummary
}

export interface CatalogResponse {
  schema_version: '1.0'
  features: Array<{
    id: FeatureId
    name: string
    description: string
    category: string
    dependencies: FeatureId[]
    locked_assurances: string[]
    locked: boolean
    default_enabled: boolean
    settings: Record<string, JsonValue>
  }>
}

export interface ApiError {
  code: string
  path: string
  message: string
}

export interface StudioApi {
  loadCatalog(signal?: AbortSignal): Promise<import('./features').FeatureDefinition[]>
  importBundle(
    profile: ProfileDocument,
    manifest: ManifestDocument,
    signal?: AbortSignal,
  ): Promise<StudioProject>
  compile(project: StudioProject, signal?: AbortSignal): Promise<CompileResult>
  migrateProject(
    project: StudioProject,
    signal?: AbortSignal,
  ): Promise<StudioProjectV2>
  compileBlueprint(
    project: StudioProjectV2,
    signal?: AbortSignal,
  ): Promise<BlueprintCompileResult>
}
