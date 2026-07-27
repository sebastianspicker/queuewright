export type StepId =
  | 'start'
  | 'organization'
  | 'structure'
  | 'access'
  | 'features'
  | 'governance'
  | 'test-data'
  | 'review'

export type Permission = 'none' | 'read' | 'create' | 'work'
export type SchemaVersion = '1.0' | '1.1'
export type JsonPrimitive = string | number | boolean | null
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue }

export const FEATURE_IDS = [
  'ticket_fields',
  'user_classification',
  'organization_classification',
  'group_classification',
  'overviews',
  'macros',
  'checklists',
  'triggers',
  'scheduled_reviews',
  'report_profiles',
  'cross_department_handoff',
  'sensitive_area_handling',
  'dummy_users_uat',
  'access_matrix',
] as const

export type FeatureId = (typeof FEATURE_IDS)[number]
export type ResourceOwner = 'core' | 'custom' | FeatureId

export interface FeatureDefinition {
  id: FeatureId
  name: string
  description: string
  category: string
  dependencies: FeatureId[]
  lockedAssurances: string[]
  locked: boolean
  defaultEnabled: boolean
  defaultSettings: Record<string, JsonValue>
}

export interface FeatureState {
  enabled: boolean
  settings: Record<string, JsonValue>
}

export interface GroupResource {
  active: true
  key: string
  kind: 'container' | 'leaf'
  name: string
  parent?: string
  restricted?: boolean
  service_code?: string
}

export interface OrganizationResource {
  active: true
  class: string
  domain_assignment: false
  key: string
  name: string
  shared: false
}

export interface RoleResource {
  key: string
  name: string
  acl: Record<string, string[]>
}

export interface ObjectFieldResource {
  name: string
  options: string[]
  type: 'select' | 'tree_select'
  api_only?: boolean
  required_by_workflow?: boolean
}

export interface KeyedResource {
  key: string
  name?: string
  [key: string]: JsonValue | undefined
}

export interface ProfileDocument {
  schema_version: SchemaVersion
  profile_key: string
  display_name: string
  offline_only: true
  manifest: string
  identity: Record<string, JsonValue>
  presentation: {
    field_labels: Record<string, string>
    option_labels: Record<string, string>
    core_workflow_names: Record<string, string>
    object_manager_positions: Record<string, { start: number; step: number }>
  }
  uat: {
    title_prefix: string
    article_visibility: 'internal'
    retention: 'close_and_retain'
    outbound_communication: false
    defaults: Record<string, string | null>
    scenarios: KeyedResource[]
    access_matrix: { seed_keys: string[] }
    handoff_probe?: Record<string, JsonValue>
    job_probe?: Record<string, JsonValue>
  }
}

export interface ManifestDocument {
  schema_version: SchemaVersion
  manifest_key: string
  managed_prefix: string
  technical_namespace: string
  safety_contract: Record<string, JsonValue>
  reference_sets: { H: string; O: string; R: string; S: string[] }
  groups: GroupResource[]
  organizations: OrganizationResource[]
  roles: RoleResource[]
  users: {
    agents: Array<{ key: string; role: string }>
    customers: Array<{ key: string; organization: string }>
    email_template: string
    agent_constraints: Record<string, JsonValue>
    customer_constraints: Record<string, JsonValue>
  }
  overviews: KeyedResource[]
  macros: KeyedResource[]
  tags: string[]
  checklist_templates: KeyedResource[]
  triggers: KeyedResource[]
  jobs: KeyedResource[]
  report_profiles: KeyedResource[]
  object_manager: {
    ticket_fields: ObjectFieldResource[]
    user_fields: ObjectFieldResource[]
    organization_fields: ObjectFieldResource[]
    group_fields: ObjectFieldResource[]
    core_workflows: KeyedResource[]
    tenant_default: Record<string, JsonValue>
    [key: string]: JsonValue | ObjectFieldResource[] | KeyedResource[]
  }
  uat: {
    ticket_count: number
    title_prefix: string
    article_visibility: 'internal'
    retention: 'close_and_retain'
    outbound_communication: false
  }
}

export interface StudioProject {
  project_schema_version: '1.0'
  id: string
  name: string
  target_schema_version: SchemaVersion
  profile: ProfileDocument
  manifest: ManifestDocument
  resource_ownership: Record<string, ResourceOwner>
  feature_state: Record<FeatureId, FeatureState>
}

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
  loadCatalog(signal?: AbortSignal): Promise<FeatureDefinition[]>
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
