import type {
  FeatureId,
  FeatureState,
  JsonValue,
  ResourceOwner,
  SchemaVersion,
} from './features'

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
  acl: Partial<Record<string, string[]>>
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
