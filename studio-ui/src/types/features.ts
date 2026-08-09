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
