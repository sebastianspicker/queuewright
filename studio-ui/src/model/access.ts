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

export function removeGroupPermission(role: RoleResource, groupKey: string): void {
  for (const acl of Object.values(role.acl)) {
    if (!acl) continue
    const index = acl.indexOf(groupKey)
    if (index >= 0) acl.splice(index, 1)
  }
  role.acl = Object.fromEntries(
    Object.entries(role.acl).filter(([, groups]) => groups && groups.length > 0),
  )
}

export function permissionFor(role: RoleResource, group: string): Permission {
  if (role.acl.full?.includes(group)) return 'work'
  if (role.acl.create?.includes(group)) return 'create'
  if (role.acl.read?.includes(group) || role.acl.read_change_overview?.includes(group)) {
    return 'read'
  }
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
    removeGroupPermission(role, groupKey)
    addGroupPermission(role, groupKey, permission)
  })
}

function appendFull(role: RoleResource, groupKey: string): void {
  role.acl.full = [...(role.acl.full ?? []), groupKey].sort()
}

function appendCreate(role: RoleResource, groupKey: string): void {
  role.acl.create = [...(role.acl.create ?? []), groupKey].sort()
}

function appendRead(role: RoleResource, groupKey: string): void {
  role.acl.read = [...(role.acl.read ?? []), groupKey].sort()
}

export function addGroupPermission(role: RoleResource, groupKey: string, permission: Permission): void {
  const updates = new Map<Permission, typeof appendFull>([
    ['work', appendFull],
    ['create', appendCreate],
    ['read', appendRead],
  ])
  updates.get(permission)?.(role, groupKey)
}
