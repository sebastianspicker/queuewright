import { bundledCatalog } from '../data'
import type {
  FeatureDefinition,
  FeatureId,
  KeyedResource,
  ResourceOwner,
  StudioProject,
} from '../types'
import { HANDOFF_MODES } from './access'
import { clone, finalize } from './mutate'

type ObjectFieldCollection = 'ticket_fields' | 'user_fields' | 'organization_fields' | 'group_fields'

const forbiddenActions = [
  'ai',
  'close',
  'delete',
  'group_move',
  'mail',
  'owner_change',
  'public_article',
  'webhook',
]

function ownedResourceIds(project: StudioProject, owner: FeatureId): Set<string> {
  return new Set(
    Object.entries(project.resource_ownership)
      .filter(([, value]) => value === owner)
      .map(([id]) => id),
  )
}

function filterOwnedResources(collection: string, items: KeyedResource[], owned: Set<string>): KeyedResource[] {
  return items.filter((item) => !owned.has(`${collection}:${item.key}`))
}

function objectFields(project: StudioProject, collection: ObjectFieldCollection) {
  switch (collection) {
    case 'ticket_fields': return project.manifest.object_manager.ticket_fields
    case 'user_fields': return project.manifest.object_manager.user_fields
    case 'organization_fields': return project.manifest.object_manager.organization_fields
    case 'group_fields': return project.manifest.object_manager.group_fields
  }
}

function replaceObjectFields(project: StudioProject, collection: ObjectFieldCollection, fields: ReturnType<typeof objectFields>): void {
  switch (collection) {
    case 'ticket_fields': project.manifest.object_manager.ticket_fields = fields; return
    case 'user_fields': project.manifest.object_manager.user_fields = fields; return
    case 'organization_fields': project.manifest.object_manager.organization_fields = fields; return
    case 'group_fields': project.manifest.object_manager.group_fields = fields; return
  }
}

function removeOwnedCollections(project: StudioProject, owned: Set<string>): void {
  project.manifest.overviews = filterOwnedResources('overviews', project.manifest.overviews, owned)
  project.manifest.macros = filterOwnedResources('macros', project.manifest.macros, owned)
  project.manifest.checklist_templates = filterOwnedResources('checklist_templates', project.manifest.checklist_templates, owned)
  project.manifest.triggers = filterOwnedResources('triggers', project.manifest.triggers, owned)
  project.manifest.jobs = filterOwnedResources('jobs', project.manifest.jobs, owned)
  project.manifest.report_profiles = filterOwnedResources('report_profiles', project.manifest.report_profiles, owned)
}

function replaceRemovedTags(project: StudioProject, candidateTags: Set<string>): void {
  const fallbackTag = project.manifest.tags.find(
    (tag) => !candidateTags.has(tag) && tag.endsWith('/uat'),
  ) ?? project.manifest.tags.find((tag) => !candidateTags.has(tag))
  for (const scenario of project.profile.uat.scenarios) {
    if (!Array.isArray(scenario.expected_tags)) continue
    const remaining = scenario.expected_tags.filter(
      (tag): tag is string => typeof tag === 'string' && !candidateTags.has(tag),
    )
    if (remaining.length === 0 && fallbackTag) remaining.push(fallbackTag)
    scenario.expected_tags = remaining
  }
}

function removeOwnedFields(project: StudioProject, owned: Set<string>): void {
  const removedLogicalNames = new Set<string>()
  for (const collection of ['ticket_fields', 'user_fields', 'organization_fields', 'group_fields'] as const) {
    const removedFields = objectFields(project, collection).filter(
      (field) => owned.has(`object_manager_fields:${field.name}`),
    )
    for (const field of removedFields) removedLogicalNames.add(field.name.replace(project.manifest.technical_namespace, ''))
    replaceObjectFields(project, collection, objectFields(project, collection).filter(
      (field) => !owned.has(`object_manager_fields:${field.name}`),
    ))
  }
  project.profile.uat.scenarios = project.profile.uat.scenarios.map((scenario) =>
    Object.fromEntries(Object.entries(scenario).filter(([key]) => !removedLogicalNames.has(key))) as KeyedResource,
  )
}

function removeFeatureProbes(project: StudioProject, owner: FeatureId): void {
  if (owner === 'cross_department_handoff') delete project.profile.uat.handoff_probe
  if (owner === 'scheduled_reviews') delete project.profile.uat.job_probe
  if (owner === 'sensitive_area_handling') {
    for (const group of project.manifest.groups) delete group.restricted
  }
}

function referencedTags(project: StudioProject): Set<string> {
  const tags = new Set<string>()
  for (const resource of [...project.manifest.macros, ...project.manifest.triggers, ...project.manifest.jobs]) {
    if (!Array.isArray(resource.actions)) continue
    for (const action of resource.actions) {
      if (typeof action === 'string' && action.startsWith('add_tag:')) tags.add(action.slice('add_tag:'.length))
    }
  }
  for (const scenario of project.profile.uat.scenarios) {
    if (!Array.isArray(scenario.expected_tags)) continue
    for (const tag of scenario.expected_tags) if (typeof tag === 'string') tags.add(tag)
  }
  return tags
}

function ownershipAfterFeatureRemoval(id: string): ResourceOwner {
  return id.startsWith('groups:')
      || id.startsWith('organizations:')
      || id.startsWith('roles:')
      || id.startsWith('core_workflows:')
      ? 'core'
      : id.startsWith('uat_scenarios:')
        ? 'access_matrix'
        : 'custom'
}

function restoreOwnership(project: StudioProject, owner: FeatureId): void {
  project.resource_ownership = Object.fromEntries(
    Object.entries(project.resource_ownership).map(([id, value]) => value === owner ? [id, ownershipAfterFeatureRemoval(id)] : [id, value]),
  )
}

function removeResourcesOwnedBy(project: StudioProject, owner: FeatureId): void {
  const owned = ownedResourceIds(project, owner)
  removeOwnedCollections(project, owned)
  const candidateTags = new Set(
    project.manifest.tags.filter((tag) => owned.has(`tags:${tag}`)),
  )
  replaceRemovedTags(project, candidateTags)
  removeOwnedFields(project, owned)
  removeFeatureProbes(project, owner)
  const retainedTags = referencedTags(project)
  project.manifest.tags = project.manifest.tags.filter(
    (tag) => !candidateTags.has(tag) || retainedTags.has(tag),
  )
  restoreOwnership(project, owner)
}

function addClassificationResources(project: StudioProject, feature: FeatureId): boolean {
  const namespace = project.manifest.technical_namespace
  const ensureField = (
    collection: ObjectFieldCollection,
    suffix: string,
    options: string[],
  ) => {
    const name = `${namespace}${suffix}`
    const fields = objectFields(project, collection)
    if (!fields.some((field) => field.name === name)) fields.push({ name, options, type: 'select' })
  }

  switch (feature) {
    case 'ticket_fields': {
      const options = project.manifest.groups.flatMap((group) =>
        group.service_code ? [group.service_code] : [],
      )
      ensureField('ticket_fields', 'service_code', options)
      return true
    }
    case 'user_classification':
      ensureField('user_fields', 'user_population', ['students', 'faculty', 'professional_services'])
      return true
    case 'organization_classification':
      ensureField('organization_fields', 'organization_class', ['students', 'faculty', 'professional_services'])
      return true
    case 'group_classification':
      ensureField('group_fields', 'group_class', ['container', 'service', 'restricted'])
      return true
    default:
      return false
  }
}

function addOperationalResources(project: StudioProject, feature: FeatureId): boolean {
  const prefix = project.manifest.managed_prefix
  const namespace = project.manifest.technical_namespace
  const ensureTag = (tag: string) => {
    if (!project.manifest.tags.includes(tag)) project.manifest.tags.push(tag)
  }
  const ensure = (items: KeyedResource[], resource: KeyedResource) => {
    if (!items.some((item) => item.key === resource.key)) items.push(resource)
  }
  switch (feature) {
    case 'overviews':
      ensure(project.manifest.overviews, { key: 'my_open', name: `${prefix} Overview · My open tickets`, conditions: { group: 'H', organization: 'O', owner: 'current_user', state: 'open_like' }, roles: 'R' })
      return true
    case 'macros':
      ensure(project.manifest.macros, { key: 'resolve', name: `${prefix} Macro · Resolve`, scope: 'H', actions: ['set_state_closed'] })
      return true
    case 'checklists':
      ensure(project.manifest.checklist_templates, { key: 'standard_intake', name: `${prefix} Checklist · Standard intake`, active: false, items: ['Confirm owner and next step'] })
      return true
    case 'triggers': {
      const uatTag = `${namespace.slice(0, -1)}/uat`
      ensureTag(uatTag)
      ensure(project.manifest.triggers, { key: 'mark_uat', name: `${prefix} Trigger · Mark UAT`, active: true, conditions: { all: ['group in H', 'organization in O'] }, actions: [`add_tag:${uatTag}`], external_effects: false })
      return true
    }
    case 'scheduled_reviews': {
      const reviewTag = `${namespace.slice(0, -1)}/review`
      ensureTag(reviewTag)
      ensure(project.manifest.jobs, { key: 'weekly_review', name: `${prefix} Review · Weekly`, active: true, conditions: { all: ['group in H', 'organization in O'] }, actions: [`add_tag:${reviewTag}`], external_effects: false, forbidden_actions: forbiddenActions, schedule: '0 7 * * 1 Europe/Berlin' })
      return true
    }
    case 'report_profiles':
      ensure(project.manifest.report_profiles, { key: 'volume', name: `${prefix} Report · Volume`, active: true, conditions: { group: 'H', organization: 'O' } })
      return true
    default:
      return false
  }
}

function addSpecialResources(project: StudioProject, feature: FeatureId): void {
  const prefix = project.manifest.managed_prefix
  const namespace = project.manifest.technical_namespace
  const ensureTag = (tag: string) => {
    if (!project.manifest.tags.includes(tag)) project.manifest.tags.push(tag)
  }
  const ensure = (items: KeyedResource[], resource: KeyedResource) => {
    if (!items.some((item) => item.key === resource.key)) items.push(resource)
  }
  const ensureField = (
    collection: ObjectFieldCollection,
    suffix: string,
    options: string[],
  ) => {
    const name = `${namespace}${suffix}`
    const fields = objectFields(project, collection)
    if (!fields.some((field) => field.name === name)) fields.push({ name, options, type: 'select' })
  }
  switch (feature) {
    case 'cross_department_handoff': {
      const pending = `${namespace.slice(0, -1)}/handoff_pending`
      const recorded = `${namespace.slice(0, -1)}/handoff_recorded`
      ensureTag(pending)
      ensureTag(recorded)
      const configured = project.feature_state.cross_department_handoff.settings.modes
      const modes = Array.isArray(configured)
        ? configured.filter((mode): mode is string =>
            typeof mode === 'string' && (HANDOFF_MODES as readonly string[]).includes(mode),
          )
        : [...HANDOFF_MODES]
      ensureField('ticket_fields', 'handoff_type', modes.length > 0 ? modes : [...HANDOFF_MODES])
      ensure(project.manifest.macros, { key: 'prepare_handoff', name: `${prefix} Macro · Prepare handoff`, scope: 'H', actions: [`add_tag:${pending}`, 'clear_owner', 'internal_note:Prepare a sanitized handoff record'] })
      ensure(project.manifest.triggers, { key: 'record_handoff', name: `${prefix} Trigger · Record handoff`, active: true, conditions: { all: ['group in H', 'organization in O'] }, actions: [`add_tag:${recorded}`], external_effects: false })
      const leaves = project.manifest.groups.filter((group) => group.kind === 'leaf')
      const ticket = project.profile.uat.scenarios[0]
      const agent = project.manifest.users.agents[0]
      if (leaves.length > 1 && ticket && agent) {
        project.profile.uat.handoff_probe = { ticket_key: ticket.key, agent: agent.key, source_group: leaves[0].key, target_group: leaves[1].key, pending_tag: pending, recorded_tag: recorded, expected_owner: 'unassigned' }
      }
      return
    }
    case 'sensitive_area_handling': {
      const sensitiveTag = `${namespace.slice(0, -1)}/sensitive`
      ensureTag(sensitiveTag)
      ensureField('ticket_fields', 'sensitive_area', ['no', 'yes'])
      ensure(project.manifest.triggers, { key: 'mark_sensitive', name: `${prefix} Trigger · Mark sensitive area`, active: true, conditions: { all: ['group in S', 'organization in O'] }, actions: [`add_tag:${sensitiveTag}`], external_effects: false })
      const leaf = project.manifest.groups.find((group) => group.key.includes('security'))
        ?? [...project.manifest.groups].reverse().find((group) => group.kind === 'leaf')
      if (leaf) leaf.restricted = true
      return
    }
    case 'dummy_users_uat':
    case 'access_matrix':
      return
    default:
      return
  }
}

function addFeatureResources(project: StudioProject, feature: FeatureId): void {
  if (addClassificationResources(project, feature)) return
  if (addOperationalResources(project, feature)) return
  addSpecialResources(project, feature)
}

function featureStateFor(project: StudioProject, id: FeatureId) {
  return new Map<FeatureId, StudioProject['feature_state'][FeatureId]>(
    Object.entries(project.feature_state) as Array<[FeatureId, StudioProject['feature_state'][FeatureId]]>,
  ).get(id)
}

export function toggleFeature(
  source: StudioProject,
  featureId: FeatureId,
  enabled: boolean,
  catalog: FeatureDefinition[] = bundledCatalog,
): StudioProject {
  const definitions = new Map(catalog.map((feature) => [feature.id, feature]))
  const next = clone(source)
  const enable = (id: FeatureId) => {
    for (const dependency of definitions.get(id)?.dependencies ?? []) enable(dependency)
    const state = featureStateFor(next, id)
    if (!state) return
    state.enabled = true
    addFeatureResources(next, id)
  }
  const disable = (id: FeatureId) => {
    if (definitions.get(id)?.locked) return
    for (const dependent of catalog) {
      if (dependent.dependencies.includes(id) && featureStateFor(next, dependent.id)?.enabled) {
        disable(dependent.id)
      }
    }
    const state = featureStateFor(next, id)
    if (!state) return
    state.enabled = false
    removeResourcesOwnedBy(next, id)
  }
  if (enabled) enable(featureId)
  else disable(featureId)
  return finalize(next, next.resource_ownership)
}
