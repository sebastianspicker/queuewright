import universityManifestJson from '../../studio/templates/university/university.desired-state.json'
import universityProfileJson from '../../studio/templates/university/profile.json'
import exampleManifestJson from '../../profiles/example/desired-state.json'
import exampleProfileJson from '../../profiles/example/profile.json'
import featureCatalogJson from '../../studio/catalog/features.json'
import capabilityCatalogJson from '../../studio/catalog/capabilities.json'
import {
  FEATURE_IDS,
  type CapabilityDefinition,
  type FeatureDefinition,
  type FeatureId,
  type FeatureState,
  type ManifestDocument,
  type ProfileDocument,
  type ResourceOwner,
  type StudioProject,
} from './types'

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
  settings: Record<string, import('./types').JsonValue>
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

function initialFeatureState(
  ownership: Record<string, ResourceOwner> = {},
): Record<FeatureId, FeatureState> {
  const owners = new Set(Object.values(ownership))
  const enabled = new Set<FeatureId>(
    bundledCatalog
      .filter((feature) => feature.locked || owners.has(feature.id))
      .map((feature) => feature.id),
  )
  let changed = true
  while (changed) {
    changed = false
    for (const feature of bundledCatalog) {
      if (!enabled.has(feature.id)) continue
      for (const dependency of feature.dependencies) {
        if (enabled.has(dependency)) continue
        enabled.add(dependency)
        changed = true
      }
    }
  }
  return Object.fromEntries(
    bundledCatalog.map((feature) => [
      feature.id,
      {
        enabled: enabled.has(feature.id),
        settings: clone(feature.defaultSettings),
      },
    ]),
  ) as Record<FeatureId, FeatureState>
}

export function resourceIds(
  profile: ProfileDocument,
  manifest: ManifestDocument,
): string[] {
  const ids: string[] = []
  const add = (collection: string, items: Array<{ key: string }>) => {
    for (const item of items) ids.push(`${collection}:${item.key}`)
  }
  add('groups', manifest.groups)
  add('organizations', manifest.organizations)
  add('roles', manifest.roles)
  add('agents', manifest.users.agents)
  add('customers', manifest.users.customers)
  add('overviews', manifest.overviews)
  add('macros', manifest.macros)
  for (const tag of manifest.tags) ids.push(`tags:${tag}`)
  add('checklist_templates', manifest.checklist_templates)
  add('triggers', manifest.triggers)
  add('jobs', manifest.jobs)
  add('report_profiles', manifest.report_profiles)
  for (const collection of ['ticket_fields', 'user_fields', 'organization_fields', 'group_fields'] as const) {
    for (const field of manifest.object_manager[collection]) {
      ids.push(`object_manager_fields:${field.name}`)
    }
  }
  add('core_workflows', manifest.object_manager.core_workflows)
  add('uat_scenarios', profile.uat.scenarios)
  return ids.sort()
}

export function ownerForResource(id: string): ResourceOwner {
  if (id.startsWith('groups:') || id.startsWith('organizations:') || id.startsWith('roles:') || id.startsWith('core_workflows:')) return 'core'
  if (id.startsWith('agents:') || id.startsWith('customers:')) return 'dummy_users_uat'
  if (id.startsWith('uat_scenarios:') || id.endsWith('/uat')) return 'access_matrix'
  // Unambiguous collection prefixes before content-based matches.
  // jobs: must beat handoff substring (e.g. jobs:review_stale_handoff).
  if (id.startsWith('overviews:')) return 'overviews'
  if (id.startsWith('macros:')) return 'macros'
  if (id.startsWith('checklist_templates:')) return 'checklists'
  if (id.startsWith('triggers:')) return 'triggers'
  if (id.startsWith('jobs:')) return 'scheduled_reviews'
  if (id.startsWith('report_profiles:')) return 'report_profiles'
  // Content-based owners for fields/tags before the OM catch-all.
  if (id.includes('handoff')) return 'cross_department_handoff'
  if (id.includes('sensitive') || id.includes('information_security')) return 'sensitive_area_handling'
  if (id.includes('user_population')) return 'user_classification'
  if (id.includes('organization_class')) return 'organization_classification'
  if (id.includes('group_class')) return 'group_classification'
  if (id.startsWith('object_manager_fields:')) return 'ticket_fields'
  return 'custom'
}

export function syncOwnership(
  profile: ProfileDocument,
  manifest: ManifestDocument,
  previous: Record<string, ResourceOwner> = {},
): Record<string, ResourceOwner> {
  return Object.fromEntries(
    resourceIds(profile, manifest).map((id) => [
      id,
      previous[id] ?? ownerForResource(id),
    ]),
  )
}

function projectFrom(
  id: string,
  profile: ProfileDocument,
  manifest: ManifestDocument,
): StudioProject {
  const project: StudioProject = {
    project_schema_version: '1.0',
    id,
    name: profile.display_name,
    target_schema_version: profile.schema_version,
    profile,
    manifest,
    resource_ownership: {},
    feature_state: initialFeatureState(),
  }
  project.resource_ownership = syncOwnership(profile, manifest)
  project.feature_state = initialFeatureState(project.resource_ownership)
  return project
}

export function exampleProject(id = 'university-service-desk'): StudioProject {
  return projectFrom(
    id,
    clone(universityProfileJson) as ProfileDocument,
    clone(universityManifestJson) as ManifestDocument,
  )
}

export function blankProject(): StudioProject {
  const profile = clone(exampleProfileJson) as ProfileDocument
  const manifest = clone(exampleManifestJson) as ManifestDocument
  profile.schema_version = '1.1'
  manifest.schema_version = '1.1'
  profile.profile_key = 'queuewright_draft'
  profile.display_name = 'Untitled configuration'
  profile.manifest = 'queuewright_draft.desired-state.json'
  profile.identity.agent_login_template = 'queuewright_draft.agent.{key}'
  profile.identity.customer_login_template = 'queuewright_draft.customer.{key}'
  profile.identity.email_template = 'queuewright_draft.{kind}.{key}@example.invalid'
  profile.identity.agent_firstname = 'qWright'
  profile.identity.customer_firstname = 'qWright'
  profile.presentation.field_labels = { queuewright_draft_service_code: 'Service' }
  profile.presentation.core_workflow_names = {
    agent_create_shared: 'qWright Draft · CW · Agent create shared',
  }
  profile.uat.title_prefix = '[QWRIGHT-UAT]'
  profile.uat.scenarios[0].expected_tags = ['queuewright_draft/uat']
  manifest.manifest_key = 'queuewright-draft-v1'
  manifest.managed_prefix = 'qWright Draft ·'
  manifest.technical_namespace = 'queuewright_draft_'
  for (const collection of ['groups', 'organizations', 'roles'] as const) {
    for (const item of manifest[collection]) {
      item.name = item.name?.replace('Example Prototype ·', 'qWright Draft ·') ?? ''
    }
  }
  manifest.users.email_template = 'queuewright_draft.{kind}.{key}@example.invalid'
  manifest.overviews = []
  manifest.macros = []
  manifest.tags = ['queuewright_draft/uat']
  manifest.checklist_templates = []
  manifest.triggers = []
  manifest.jobs = []
  manifest.report_profiles = []
  manifest.object_manager.ticket_fields[0].name = 'queuewright_draft_service_code'
  manifest.uat.title_prefix = '[QWRIGHT-UAT]'
  return projectFrom(`studio-draft-${Date.now().toString(36)}`, profile, manifest)
}
