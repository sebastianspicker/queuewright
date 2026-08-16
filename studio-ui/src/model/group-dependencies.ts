import type { GroupResource, KeyedResource, StudioProject } from '../types'
import { displayGroupName } from './group-tree'

export function nextServiceCode(project: StudioProject): string {
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

export function addLeafDependencies(
  project: StudioProject,
  group: GroupResource,
): void {
  const code = group.service_code ?? nextServiceCode(project)
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
    const labels = new Map(Object.entries(project.profile.presentation.option_labels))
    labels.set(code, label)
    project.profile.presentation.option_labels = Object.fromEntries(labels)
  }
  project.profile.uat.scenarios.push(scenario)
  project.profile.uat.access_matrix.seed_keys.push(scenario.key)
}

export function removeLeafDependencies(
  project: StudioProject,
  keys: Set<string>,
): void {
  for (const role of project.manifest.roles) {
    role.acl = Object.fromEntries(
      Object.entries(role.acl)
        .map(([permission, allowed]) => [permission, (allowed ?? []).filter((key) => !keys.has(key))])
        .filter(([, allowed]) => allowed.length > 0),
    )
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

export function customerEntryPoints(project: StudioProject): string[] {
  const value = project.feature_state.ticket_fields.settings.customer_entry_points
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

export function materializeCustomerEntryPoints(
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
