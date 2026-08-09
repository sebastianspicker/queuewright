import type {
  FeatureId,
  FeatureState,
  JsonValue,
  ResourceOwner,
  SchemaVersion,
} from './features'
import type { ManifestDocument, ProfileDocument } from './project'

export type CapabilityDelivery =
  | 'automated'
  | 'guided_manual'
  | 'verify_only'
  | 'unsupported'

export type CapabilityCompletion =
  | 'decision_required'
  | 'ready'
  | 'applied'
  | 'verified'
  | 'blocked'

export type CapabilityRisk = 'low' | 'medium' | 'high' | 'critical'

export interface CapabilityDefinition {
  id: string
  domain: string
  delivery: CapabilityDelivery
  default_completion: CapabilityCompletion
  risk: CapabilityRisk
  dependencies: string[]
}

export interface CapabilityDecision {
  completion: CapabilityCompletion
  delivery: CapabilityDelivery
  risk: CapabilityRisk
  dependencies: string[]
  enabled: boolean
}

export interface StudioBundle {
  profile: ProfileDocument
  manifest: ManifestDocument
  resource_ownership: Record<string, ResourceOwner>
  feature_state: Record<FeatureId, FeatureState>
}

export interface BlueprintWorkbook {
  organization: Record<string, JsonValue>
  services: Array<Record<string, JsonValue>>
  policies: Record<string, JsonValue>
  capability_decisions: Record<string, CapabilityDecision>
  uat: Record<string, JsonValue>
}

export interface StudioProjectV2 {
  project_schema_version: '2.0'
  id: string
  name: string
  target_schema_version: SchemaVersion
  workbook: BlueprintWorkbook
  extensions: Record<string, JsonValue>
  bundle: StudioBundle
}

export interface ConfigurationGraphNode {
  id: string
  resource_kind: string
  logical_key: string
  desired: JsonValue
  dependencies: string[]
  delivery: CapabilityDelivery
  risk: CapabilityRisk
  owner: string
  verification: JsonValue
  rollback: JsonValue
}

export interface ConfigurationGraph {
  nodes: ConfigurationGraphNode[]
  graph_hash: string
}

export interface BlueprintCompileResult {
  project: StudioProjectV2
  bundle: StudioBundle
  plan: SymbolicPlan
  graph: ConfigurationGraph
  hashes: Record<string, string>
}

export interface CompileSummary {
  counts: Record<string, number>
  display_name: string
  manifest_key: string
  profile_hash: string
  profile_key: string
  source_hash: string
}

export interface SymbolicPlan {
  counts: Record<string, number>
  operations: Array<Record<string, JsonValue>>
  plan_hash: string
  safety: Record<string, JsonValue>
  [key: string]: JsonValue | Array<Record<string, JsonValue>>
}
