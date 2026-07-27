import type {
  GroupResource,
  KeyedResource,
  StudioProject,
} from '../types'
import { mutateProject } from './mutate'

function uniqueKey(project: StudioProject, stem: string): string {
  const keys = new Set(project.manifest.groups.map((group) => group.key))
  let index = 1
  let candidate = stem
  while (keys.has(candidate)) {
    index += 1
    candidate = `${stem}_${index}`
  }
  return candidate
}

export function displayGroupName(
  project: StudioProject,
  group: GroupResource,
): string {
  return group.name
    .slice(project.manifest.managed_prefix.length)
    .replace(/^\s+/, '')
}

export function childrenOf(
  project: StudioProject,
  parent?: string,
): GroupResource[] {
  return project.manifest.groups.filter((group) => group.parent === parent)
}

export function rootGroup(project: StudioProject): GroupResource | undefined {
  return project.manifest.groups.find(
    (group) => group.kind === 'container' && group.parent === undefined,
  )
}

export function isDescendant(
  project: StudioProject,
  candidate: string,
  ancestor: string,
): boolean {
  let current = project.manifest.groups.find((group) => group.key === candidate)
  const seen = new Set<string>()
  while (current?.parent) {
    if (current.parent === ancestor) return true
    if (seen.has(current.parent)) return true
    seen.add(current.parent)
    current = project.manifest.groups.find(
      (group) => group.key === current?.parent,
    )
  }
  return false
}

function serviceCode(project: StudioProject): string {
  const existing = new Set(
    project.manifest.groups.flatMap((group) =>
      group.service_code ? [group.service_code] : [],
    ),
  )
  let index = existing.size + 1
  let candidate = `NEW.SERVICE${index}`
  while (existing.has(candidate)) {
    index += 1
    candidate = `NEW.SERVICE${index}`
  }
  return candidate
}

function addLeafDependencies(
  project: StudioProject,
  group: GroupResource,
): void {
  const code = group.service_code ?? serviceCode(project)
  group.service_code = code
  const label = displayGroupName(project, group)
  project.manifest.roles.push({
    key: group.key,
    name: `${project.manifest.managed_prefix} Role · ${label}`,
    acl: { full: [group.key] },
  })
  project.manifest.users.agents.push({ key: group.key, role: group.key })
  const customer = project.manifest.users.customers[0]
  const uatTag = project.manifest.tags.find((tag) => tag.endsWith('/uat'))
    ?? project.manifest.tags[0]
  const number = Math.max(
    0,
    ...project.profile.uat.scenarios.map((scenario) =>
      typeof scenario.number === 'number' ? scenario.number : 0,
    ),
  ) + 1
  const scenario: KeyedResource = {
    key: `seed_${group.key}`,
    number,
    kind: 'seed',
    group: group.key,
    customer: customer?.key ?? '',
    agent: group.key,
    label: `${label} request`,
    expected_tags: [uatTag],
  }
  const serviceField = project.manifest.object_manager.ticket_fields.find(
    (field) => field.name.endsWith('_service_code'),
  )
  if (serviceField) {
    serviceField.options.push(code)
    scenario.service_code = code
    project.profile.presentation.option_labels[code] = label
  }
  project.profile.uat.scenarios.push(scenario)
  project.profile.uat.access_matrix.seed_keys.push(scenario.key)
}

function removeLeafDependencies(project: StudioProject, keys: Set<string>): void {
  for (const role of project.manifest.roles) {
    for (const permission of Object.keys(role.acl)) {
      role.acl[permission] = role.acl[permission].filter((key) => !keys.has(key))
      if (role.acl[permission].length === 0) delete role.acl[permission]
    }
  }
  const removedRoles = new Set(
    project.manifest.roles
      .filter((role) => Object.keys(role.acl).length === 0)
      .map((role) => role.key),
  )
  project.manifest.roles = project.manifest.roles.filter(
    (role) => !removedRoles.has(role.key),
  )
  const removedAgents = new Set(
    project.manifest.users.agents
      .filter((agent) => removedRoles.has(agent.role))
      .map((agent) => agent.key),
  )
  project.manifest.users.agents = project.manifest.users.agents.filter(
    (agent) => !removedRoles.has(agent.role),
  )
  const removedScenarios = new Set(
    project.profile.uat.scenarios
      .filter((scenario) =>
        keys.has(String(scenario.group))
        || removedAgents.has(String(scenario.agent)),
      )
      .map((scenario) => scenario.key),
  )
  project.profile.uat.scenarios = project.profile.uat.scenarios.filter(
    (scenario) => !removedScenarios.has(scenario.key),
  )
  project.profile.uat.access_matrix.seed_keys =
    project.profile.uat.access_matrix.seed_keys.filter(
      (key) => !removedScenarios.has(key),
    )
  const handoff = project.profile.uat.handoff_probe
  if (
    handoff
    && (keys.has(String(handoff.source_group))
      || keys.has(String(handoff.target_group))
      || removedAgents.has(String(handoff.agent))
      || removedScenarios.has(String(handoff.ticket_key)))
  ) {
    delete project.profile.uat.handoff_probe
  }
  const jobProbe = project.profile.uat.job_probe
  if (jobProbe && removedScenarios.has(String(jobProbe.ticket_key))) {
    delete project.profile.uat.job_probe
  }
  materializeCustomerEntryPoints(
    project,
    customerEntryPoints(project).filter((key) => !keys.has(key)),
  )
  const serviceCodes = new Set(
    project.manifest.groups.flatMap((group) =>
      group.kind === 'leaf' && group.service_code ? [group.service_code] : [],
    ),
  )
  const serviceField = project.manifest.object_manager.ticket_fields.find(
    (field) => field.name.endsWith('_service_code'),
  )
  if (serviceField) serviceField.options = [...serviceCodes]
}

export function addGroup(
  source: StudioProject,
  kind: 'container' | 'leaf',
  selectedKey?: string,
): { project: StudioProject; key: string } {
  if (kind === 'container' && source.target_schema_version === '1.0') {
    return { project: source, key: '' }
  }
  let createdKey = ''
  const project = mutateProject(source, (draft) => {
    const selected = draft.manifest.groups.find(
      (group) => group.key === selectedKey,
    )
    const parent = selected?.kind === 'container'
      ? selected.key
      : selected?.parent ?? rootGroup(draft)?.key
    createdKey = uniqueKey(draft, kind === 'container' ? 'new_unit' : 'new_service')
    const group: GroupResource = {
      active: true,
      key: createdKey,
      kind,
      name: `${draft.manifest.managed_prefix} ${kind === 'container' ? 'New unit' : 'New service'}`,
      ...(parent ? { parent } : {}),
      ...(kind === 'leaf' ? { service_code: serviceCode(draft) } : {}),
    }
    draft.manifest.groups.push(group)
    if (kind === 'leaf') addLeafDependencies(draft, group)
  })
  return { project, key: createdKey }
}

export function renameGroup(
  source: StudioProject,
  key: string,
  name: string,
): StudioProject {
  return mutateProject(source, (project) => {
    const group = project.manifest.groups.find((item) => item.key === key)
    if (!group) return
    group.name = `${project.manifest.managed_prefix} ${name.trim() || 'Untitled'}`
    const role = project.manifest.roles.find((item) => item.key === key)
    if (role) role.name = `${project.manifest.managed_prefix} Role · ${name.trim() || 'Untitled'}`
  })
}

export function moveGroup(
  source: StudioProject,
  key: string,
  parent: string,
): StudioProject {
  const group = source.manifest.groups.find((item) => item.key === key)
  const parentGroup = source.manifest.groups.find((item) => item.key === parent)
  if (
    !group
    || !parentGroup
    || group.parent === undefined
    || parentGroup.kind !== 'container'
    || key === parent
    || isDescendant(source, parent, key)
  ) return source
  return mutateProject(source, (project) => {
    const target = project.manifest.groups.find((item) => item.key === key)
    if (target) target.parent = parent
  })
}

export function reorderGroup(
  source: StudioProject,
  activeKey: string,
  overKey: string,
): StudioProject {
  const from = source.manifest.groups.findIndex((group) => group.key === activeKey)
  const to = source.manifest.groups.findIndex((group) => group.key === overKey)
  if (from < 0 || to < 0 || from === to) return source
  return mutateProject(source, (project) => {
    const groups = [...project.manifest.groups]
    const [moved] = groups.splice(from, 1)
    if (moved) groups.splice(to, 0, moved)
    project.manifest.groups = groups
  })
}

export function setGroupKind(
  source: StudioProject,
  key: string,
  kind: 'container' | 'leaf',
): StudioProject {
  const current = source.manifest.groups.find((group) => group.key === key)
  if (!current || current.kind === kind || current.parent === undefined) return source
  if (kind === 'container' && source.target_schema_version === '1.0') return source
  if (kind === 'leaf' && childrenOf(source, key).length > 0) return source
  return mutateProject(source, (project) => {
    const group = project.manifest.groups.find((item) => item.key === key)
    if (!group) return
    if (kind === 'container') {
      group.kind = 'container'
      delete group.service_code
      delete group.restricted
      removeLeafDependencies(project, new Set([key]))
    } else {
      group.kind = 'leaf'
      group.service_code = serviceCode(project)
      addLeafDependencies(project, group)
    }
  })
}

export function removeGroup(
  source: StudioProject,
  key: string,
): StudioProject {
  const target = source.manifest.groups.find((group) => group.key === key)
  if (!target || target.parent === undefined) return source
  const removed = new Set([key])
  let grew = true
  while (grew) {
    grew = false
    for (const group of source.manifest.groups) {
      if (group.parent && removed.has(group.parent) && !removed.has(group.key)) {
        removed.add(group.key)
        grew = true
      }
    }
  }
  return mutateProject(source, (project) => {
    project.manifest.groups = project.manifest.groups.filter(
      (group) => !removed.has(group.key),
    )
    removeLeafDependencies(project, removed)
  })
}

export function setRestricted(
  source: StudioProject,
  key: string,
  restricted: boolean,
): StudioProject {
  return mutateProject(source, (project) => {
    const group = project.manifest.groups.find((item) => item.key === key)
    if (!group || group.kind !== 'leaf') return
    if (restricted) group.restricted = true
    else delete group.restricted
  })
}

export function customerEntryPoints(project: StudioProject): string[] {
  const value = project.feature_state.ticket_fields.settings.customer_entry_points
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

export function setCustomerEntryPoint(
  source: StudioProject,
  key: string,
  enabled: boolean,
): StudioProject {
  return mutateProject(source, (project) => {
    const group = project.manifest.groups.find((item) => item.key === key)
    if (!group || group.kind !== 'leaf') return
    const entries = new Set(customerEntryPoints(project))
    if (enabled) entries.add(key)
    else entries.delete(key)
    materializeCustomerEntryPoints(project, [...entries])
  })
}

function materializeCustomerEntryPoints(
  project: StudioProject,
  requested: string[],
): void {
  const leaves = new Set(
    project.manifest.groups
      .filter((group) => group.kind === 'leaf')
      .map((group) => group.key),
  )
  const entries = [...new Set(requested)]
    .filter((key) => leaves.has(key))
    .sort()
  project.feature_state.ticket_fields.settings.customer_entry_points = entries
  const workflows = project.manifest.object_manager.core_workflows.filter(
    (workflow) => workflow.key !== 'customer_create_entry_points',
  )
  if (entries.length > 0) {
    workflows.push({
      key: 'customer_create_entry_points',
      context: 'customer_create',
      match: `authenticated customer and group in [${entries.join(',')}]`,
      actions: 'allow ticket creation only for selected managed services',
    })
  }
  project.manifest.object_manager.core_workflows = workflows
}
