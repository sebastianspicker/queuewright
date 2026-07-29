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
  type JsonValue,
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
  settings: Record<string, JsonValue>
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
  const objectManagerFields = [
    ...manifest.object_manager.ticket_fields,
    ...manifest.object_manager.user_fields,
    ...manifest.object_manager.organization_fields,
    ...manifest.object_manager.group_fields,
  ]
  for (const field of objectManagerFields) {
    ids.push(`object_manager_fields:${field.name}`)
  }
  add('core_workflows', manifest.object_manager.core_workflows)
  add('uat_scenarios', profile.uat.scenarios)
  return ids.sort()
}

export function ownerForResource(id: string): ResourceOwner {
  const prefixOwners: Array<[string, ResourceOwner]> = [
    ['groups:', 'core'], ['organizations:', 'core'], ['roles:', 'core'],
    ['core_workflows:', 'core'], ['agents:', 'dummy_users_uat'],
    ['customers:', 'dummy_users_uat'], ['uat_scenarios:', 'access_matrix'],
    ['overviews:', 'overviews'], ['macros:', 'macros'],
    ['checklist_templates:', 'checklists'], ['triggers:', 'triggers'],
    ['jobs:', 'scheduled_reviews'], ['report_profiles:', 'report_profiles'],
  ]
  const prefixOwner = prefixOwners.find(([prefix]) => id.startsWith(prefix))?.[1]
  if (prefixOwner) return prefixOwner
  if (id.endsWith('/uat')) return 'access_matrix'
  const contentOwners: Array<[string, ResourceOwner]> = [
    ['handoff', 'cross_department_handoff'],
    ['sensitive', 'sensitive_area_handling'],
    ['information_security', 'sensitive_area_handling'],
    ['user_population', 'user_classification'],
    ['organization_class', 'organization_classification'],
    ['group_class', 'group_classification'],
  ]
  const contentOwner = contentOwners.find(([term]) => id.includes(term))?.[1]
  if (contentOwner) return contentOwner
  if (id.startsWith('object_manager_fields:')) return 'ticket_fields'
  return 'custom'
}

export function syncOwnership(
  profile: ProfileDocument,
  manifest: ManifestDocument,
  previous: Record<string, ResourceOwner> = {},
): Record<string, ResourceOwner> {
  const ownership = new Map(Object.entries(previous))
  return Object.fromEntries(
    resourceIds(profile, manifest).map((id) => [
      id,
      ownership.get(id) ?? ownerForResource(id),
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
  const firstScenario = profile.uat.scenarios.at(0)
  if (firstScenario) firstScenario.expected_tags = ['queuewright_draft/uat']
  manifest.manifest_key = 'queuewright-draft-v1'
  manifest.managed_prefix = 'qWright Draft ·'
  manifest.technical_namespace = 'queuewright_draft_'
  const namedResources = [
    ...manifest.groups,
    ...manifest.organizations,
    ...manifest.roles,
  ]
  for (const item of namedResources) {
    item.name = item.name?.replace('Example Prototype ·', 'qWright Draft ·') ?? ''
  }
  manifest.users.email_template = 'queuewright_draft.{kind}.{key}@example.invalid'
  manifest.overviews = []
  manifest.macros = []
  manifest.tags = ['queuewright_draft/uat']
  manifest.checklist_templates = []
  manifest.triggers = []
  manifest.jobs = []
  manifest.report_profiles = []
  const firstTicketField = manifest.object_manager.ticket_fields.at(0)
  if (firstTicketField) firstTicketField.name = 'queuewright_draft_service_code'
  manifest.uat.title_prefix = '[QWRIGHT-UAT]'
  return projectFrom(`studio-draft-${Date.now().toString(36)}`, profile, manifest)
}
