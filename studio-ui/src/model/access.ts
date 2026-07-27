import type {
  Permission,
  RoleResource,
  StudioProject,
} from '../types'
import { mutateProject } from './mutate'

export const HANDOFF_MODES = [
  'consultation',
  'transfer',
  'sanitized_child',
  'split_work',
] as const

export function setHandoffModes(
  source: StudioProject,
  requested: string[],
): StudioProject {
  const allowed = new Set<string>(HANDOFF_MODES)
  const modes = [...new Set(requested)].filter((mode) => allowed.has(mode))
  if (modes.length === 0) return source
  return mutateProject(source, (project) => {
    project.feature_state.cross_department_handoff.settings.modes = modes
    const field = project.manifest.object_manager.ticket_fields.find(
      (item) => item.name.endsWith('_handoff_type'),
    )
    if (field) field.options = modes
  })
}

export function permissionFor(role: RoleResource, group: string): Permission {
  if (role.acl.full?.includes(group)) return 'work'
  if (role.acl.create?.includes(group)) return 'create'
  if (
    role.acl.read?.includes(group)
    || role.acl.read_change_overview?.includes(group)
  ) return 'read'
  return 'none'
}

export function setPermission(
  source: StudioProject,
  roleKey: string,
  groupKey: string,
  permission: Permission,
): StudioProject {
  return mutateProject(source, (project) => {
    const role = project.manifest.roles.find((item) => item.key === roleKey)
    if (!role) return
    for (const acl of Object.values(role.acl)) {
      const index = acl.indexOf(groupKey)
      if (index >= 0) acl.splice(index, 1)
    }
    for (const key of Object.keys(role.acl)) {
      if (role.acl[key].length === 0) delete role.acl[key]
    }
    const aclKey = permission === 'work' ? 'full' : permission
    if (aclKey !== 'none') {
      role.acl[aclKey] = [...(role.acl[aclKey] ?? []), groupKey].sort()
    }
  })
}
