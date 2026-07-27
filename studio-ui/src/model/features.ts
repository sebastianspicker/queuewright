import { bundledCatalog } from '../data'
import type {
  FeatureDefinition,
  FeatureId,
  KeyedResource,
  StudioProject,
} from '../types'
import { HANDOFF_MODES } from './access'
import { clone, finalize } from './mutate'

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

function removeResourcesOwnedBy(project: StudioProject, owner: FeatureId): void {
  const owned = new Set(
    Object.entries(project.resource_ownership)
      .filter(([, value]) => value === owner)
      .map(([id]) => id),
  )
  const filter = <T extends { key: string }>(collection: string, items: T[]) =>
    items.filter((item) => !owned.has(`${collection}:${item.key}`))
  project.manifest.overviews = filter('overviews', project.manifest.overviews)
  project.manifest.macros = filter('macros', project.manifest.macros)
  project.manifest.checklist_templates = filter('checklist_templates', project.manifest.checklist_templates)
  project.manifest.triggers = filter('triggers', project.manifest.triggers)
  project.manifest.jobs = filter('jobs', project.manifest.jobs)
  project.manifest.report_profiles = filter('report_profiles', project.manifest.report_profiles)
  const candidateTags = new Set(
    project.manifest.tags.filter((tag) => owned.has(`tags:${tag}`)),
  )
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
  for (const collection of ['ticket_fields', 'user_fields', 'organization_fields', 'group_fields'] as const) {
    const removedFields = project.manifest.object_manager[collection].filter(
      (field) => owned.has(`object_manager_fields:${field.name}`),
    )
    for (const field of removedFields) {
      const logicalName = field.name.replace(project.manifest.technical_namespace, '')
      for (const scenario of project.profile.uat.scenarios) delete scenario[logicalName]
    }
    project.manifest.object_manager[collection] =
      project.manifest.object_manager[collection].filter(
        (field) => !owned.has(`object_manager_fields:${field.name}`),
      )
  }
  if (owner === 'cross_department_handoff') delete project.profile.uat.handoff_probe
  if (owner === 'scheduled_reviews') delete project.profile.uat.job_probe
  if (owner === 'sensitive_area_handling') {
    for (const group of project.manifest.groups) delete group.restricted
  }
  const referencedTags = new Set<string>()
  for (const resource of [
    ...project.manifest.macros,
    ...project.manifest.triggers,
    ...project.manifest.jobs,
  ]) {
    if (!Array.isArray(resource.actions)) continue
    for (const action of resource.actions) {
      if (typeof action === 'string' && action.startsWith('add_tag:')) {
        referencedTags.add(action.slice('add_tag:'.length))
      }
    }
  }
  for (const scenario of project.profile.uat.scenarios) {
    if (!Array.isArray(scenario.expected_tags)) continue
    for (const tag of scenario.expected_tags) {
      if (typeof tag === 'string') referencedTags.add(tag)
    }
  }
  project.manifest.tags = project.manifest.tags.filter(
    (tag) => !candidateTags.has(tag) || referencedTags.has(tag),
  )
  for (const [id, value] of Object.entries(project.resource_ownership)) {
    if (value !== owner) continue
    project.resource_ownership[id] = id.startsWith('groups:')
      || id.startsWith('organizations:')
      || id.startsWith('roles:')
      || id.startsWith('core_workflows:')
      ? 'core'
      : id.startsWith('uat_scenarios:')
        ? 'access_matrix'
        : 'custom'
  }
}

function addFeatureResources(project: StudioProject, feature: FeatureId): void {
  const prefix = project.manifest.managed_prefix
  const namespace = project.manifest.technical_namespace
  const ensureTag = (tag: string) => {
    if (!project.manifest.tags.includes(tag)) project.manifest.tags.push(tag)
  }
  const ensure = (items: KeyedResource[], resource: KeyedResource) => {
    if (!items.some((item) => item.key === resource.key)) items.push(resource)
  }
  const ensureField = (
    collection: 'ticket_fields' | 'user_fields' | 'organization_fields' | 'group_fields',
    suffix: string,
    options: string[],
  ) => {
    const name = `${namespace}${suffix}`
    if (!project.manifest.object_manager[collection].some((field) => field.name === name)) {
      project.manifest.object_manager[collection].push({ name, options, type: 'select' })
    }
  }

  switch (feature) {
    case 'ticket_fields': {
      const options = project.manifest.groups.flatMap((group) =>
        group.service_code ? [group.service_code] : [],
      )
      ensureField('ticket_fields', 'service_code', options)
      break
    }
    case 'user_classification':
      ensureField('user_fields', 'user_population', ['students', 'faculty', 'professional_services'])
      break
    case 'organization_classification':
      ensureField('organization_fields', 'organization_class', ['students', 'faculty', 'professional_services'])
      break
    case 'group_classification':
      ensureField('group_fields', 'group_class', ['container', 'service', 'restricted'])
      break
    case 'overviews':
      ensure(project.manifest.overviews, { key: 'my_open', name: `${prefix} Overview · My open tickets`, conditions: { group: 'H', organization: 'O', owner: 'current_user', state: 'open_like' }, roles: 'R' })
      break
    case 'macros':
      ensure(project.manifest.macros, { key: 'resolve', name: `${prefix} Macro · Resolve`, scope: 'H', actions: ['set_state_closed'] })
      break
    case 'checklists':
      ensure(project.manifest.checklist_templates, { key: 'standard_intake', name: `${prefix} Checklist · Standard intake`, active: false, items: ['Confirm owner and next step'] })
      break
    case 'triggers': {
      const uatTag = `${namespace.slice(0, -1)}/uat`
      ensureTag(uatTag)
      ensure(project.manifest.triggers, { key: 'mark_uat', name: `${prefix} Trigger · Mark UAT`, active: true, conditions: { all: ['group in H', 'organization in O'] }, actions: [`add_tag:${uatTag}`], external_effects: false })
      break
    }
    case 'scheduled_reviews': {
      const reviewTag = `${namespace.slice(0, -1)}/review`
      ensureTag(reviewTag)
      ensure(project.manifest.jobs, { key: 'weekly_review', name: `${prefix} Review · Weekly`, active: true, conditions: { all: ['group in H', 'organization in O'] }, actions: [`add_tag:${reviewTag}`], external_effects: false, forbidden_actions: forbiddenActions, schedule: '0 7 * * 1 Europe/Berlin' })
      break
    }
    case 'report_profiles':
      ensure(project.manifest.report_profiles, { key: 'volume', name: `${prefix} Report · Volume`, active: true, conditions: { group: 'H', organization: 'O' } })
      break
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
      break
    }
    case 'sensitive_area_handling': {
      const sensitiveTag = `${namespace.slice(0, -1)}/sensitive`
      ensureTag(sensitiveTag)
      ensureField('ticket_fields', 'sensitive_area', ['no', 'yes'])
      ensure(project.manifest.triggers, { key: 'mark_sensitive', name: `${prefix} Trigger · Mark sensitive area`, active: true, conditions: { all: ['group in S', 'organization in O'] }, actions: [`add_tag:${sensitiveTag}`], external_effects: false })
      const leaf = project.manifest.groups.find((group) => group.key.includes('security'))
        ?? [...project.manifest.groups].reverse().find((group) => group.kind === 'leaf')
      if (leaf) leaf.restricted = true
      break
    }
    case 'dummy_users_uat':
    case 'access_matrix':
      break
  }
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
    next.feature_state[id].enabled = true
    addFeatureResources(next, id)
  }
  const disable = (id: FeatureId) => {
    if (definitions.get(id)?.locked) return
    for (const dependent of catalog) {
      if (dependent.dependencies.includes(id) && next.feature_state[dependent.id].enabled) {
        disable(dependent.id)
      }
    }
    next.feature_state[id].enabled = false
    removeResourcesOwnedBy(next, id)
  }
  if (enabled) enable(featureId)
  else disable(featureId)
  return finalize(next, next.resource_ownership)
}
