import type { FeatureId, KeyedResource, StudioProject } from '../types'
import { HANDOFF_MODES } from './access'
import { addClassificationResources } from './feature-classification'
import { objectFields, type ObjectFieldCollection } from './object-field-reader'

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

function ensureTag(project: StudioProject, tag: string): void {
  if (!project.manifest.tags.includes(tag)) project.manifest.tags.push(tag)
}

function ensureResource(items: KeyedResource[], resource: KeyedResource): void {
  if (!items.some((item) => item.key === resource.key)) items.push(resource)
}

function ensureField(
  project: StudioProject,
  collection: ObjectFieldCollection,
  suffix: string,
  options: string[],
): void {
  const name = `${project.manifest.technical_namespace}${suffix}`
  const fields = objectFields(project, collection)
  if (!fields.some((field) => field.name === name)) {
    fields.push({ name, options, type: 'select' })
  }
}

function addOperationalResources(project: StudioProject, feature: FeatureId): boolean {
  const prefix = project.manifest.managed_prefix
  const namespace = project.manifest.technical_namespace
  switch (feature) {
    case 'overviews':
      ensureResource(project.manifest.overviews, { key: 'my_open', name: `${prefix} Overview · My open tickets`, conditions: { group: 'H', organization: 'O', owner: 'current_user', state: 'open_like' }, roles: 'R' })
      return true
    case 'macros':
      ensureResource(project.manifest.macros, { key: 'resolve', name: `${prefix} Macro · Resolve`, scope: 'H', actions: ['set_state_closed'] })
      return true
    case 'checklists':
      ensureResource(project.manifest.checklist_templates, { key: 'standard_intake', name: `${prefix} Checklist · Standard intake`, active: false, items: ['Confirm owner and next step'] })
      return true
    case 'triggers': {
      const uatTag = `${namespace.slice(0, -1)}/uat`
      ensureTag(project, uatTag)
      ensureResource(project.manifest.triggers, { key: 'mark_uat', name: `${prefix} Trigger · Mark UAT`, active: true, conditions: { all: ['group in H', 'organization in O'] }, actions: [`add_tag:${uatTag}`], external_effects: false })
      return true
    }
    case 'scheduled_reviews': {
      const reviewTag = `${namespace.slice(0, -1)}/review`
      ensureTag(project, reviewTag)
      ensureResource(project.manifest.jobs, { key: 'weekly_review', name: `${prefix} Review · Weekly`, active: true, conditions: { all: ['group in H', 'organization in O'] }, actions: [`add_tag:${reviewTag}`], external_effects: false, forbidden_actions: forbiddenActions, schedule: '0 7 * * 1 Europe/Berlin' })
      return true
    }
    case 'report_profiles':
      ensureResource(project.manifest.report_profiles, { key: 'volume', name: `${prefix} Report · Volume`, active: true, conditions: { group: 'H', organization: 'O' } })
      return true
    default:
      return false
  }
}

function configuredHandoffModes(project: StudioProject): string[] {
  const configured = project.feature_state.cross_department_handoff.settings.modes
  const modes = Array.isArray(configured)
    ? configured.filter((mode): mode is string =>
        typeof mode === 'string' && (HANDOFF_MODES as readonly string[]).includes(mode),
      )
    : [...HANDOFF_MODES]
  return modes.length > 0 ? modes : [...HANDOFF_MODES]
}

function addHandoffResources(project: StudioProject): void {
  const prefix = project.manifest.managed_prefix
  const namespace = project.manifest.technical_namespace
  const pending = `${namespace.slice(0, -1)}/handoff_pending`
  const recorded = `${namespace.slice(0, -1)}/handoff_recorded`
  ensureTag(project, pending)
  ensureTag(project, recorded)
  ensureField(project, 'ticket_fields', 'handoff_type', configuredHandoffModes(project))
  ensureResource(project.manifest.macros, { key: 'prepare_handoff', name: `${prefix} Macro · Prepare handoff`, scope: 'H', actions: [`add_tag:${pending}`, 'clear_owner', 'internal_note:Prepare a sanitized handoff record'] })
  ensureResource(project.manifest.triggers, { key: 'record_handoff', name: `${prefix} Trigger · Record handoff`, active: true, conditions: { all: ['group in H', 'organization in O'] }, actions: [`add_tag:${recorded}`], external_effects: false })
  const leaves = project.manifest.groups.filter((group) => group.kind === 'leaf')
  const ticket = project.profile.uat.scenarios[0]
  const agent = project.manifest.users.agents[0]
  if (leaves.length > 1 && ticket && agent) {
    project.profile.uat.handoff_probe = { ticket_key: ticket.key, agent: agent.key, source_group: leaves[0].key, target_group: leaves[1].key, pending_tag: pending, recorded_tag: recorded, expected_owner: 'unassigned' }
  }
}

function addSensitiveAreaResources(project: StudioProject): void {
  const prefix = project.manifest.managed_prefix
  const namespace = project.manifest.technical_namespace
  const sensitiveTag = `${namespace.slice(0, -1)}/sensitive`
  ensureTag(project, sensitiveTag)
  ensureField(project, 'ticket_fields', 'sensitive_area', ['no', 'yes'])
  ensureResource(project.manifest.triggers, { key: 'mark_sensitive', name: `${prefix} Trigger · Mark sensitive area`, active: true, conditions: { all: ['group in S', 'organization in O'] }, actions: [`add_tag:${sensitiveTag}`], external_effects: false })
  const leaf = project.manifest.groups.find((group) => group.key.includes('security'))
    ?? [...project.manifest.groups].reverse().find((group) => group.kind === 'leaf')
  if (leaf) leaf.restricted = true
}

function addSpecialResources(project: StudioProject, feature: FeatureId): void {
  switch (feature) {
    case 'cross_department_handoff':
      addHandoffResources(project)
      return
    case 'sensitive_area_handling':
      addSensitiveAreaResources(project)
      return
    case 'dummy_users_uat':
    case 'access_matrix':
      return
    default:
      return
  }
}

export function addFeatureResources(project: StudioProject, feature: FeatureId): void {
  if (addClassificationResources(project, feature)) return
  if (addOperationalResources(project, feature)) return
  addSpecialResources(project, feature)
}
