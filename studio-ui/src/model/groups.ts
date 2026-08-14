import type { GroupResource, StudioProject } from '../types'
import { mutateProject } from './mutate'
import {
  addLeafDependencies,
  customerEntryPoints,
  materializeCustomerEntryPoints,
  nextServiceCode,
  removeLeafDependencies,
} from './group-dependencies'
import {
  canMoveGroup,
  childrenOf,
  displayGroupName,
  groupAndDescendantKeys,
  isDescendant,
  rootGroup,
  uniqueGroupKey,
} from './group-tree'

export { childrenOf, displayGroupName, isDescendant, rootGroup }

export function addGroup(
  source: StudioProject,
  kind: 'container' | 'leaf',
  selectedKey?: string,
): { project: StudioProject; key: string } {
  if (kind === 'container' && source.target_schema_version === '1.0') {
    return { project: source, key: '' }
  }
  let createdGroupId: string | undefined
  const project = mutateProject(source, (draft) => {
    const selected = draft.manifest.groups.find(
      (group) => group.key === selectedKey,
    )
    const parent = selected?.kind === 'container'
      ? selected.key
      : selected?.parent ?? rootGroup(draft)?.key
    createdGroupId = uniqueGroupKey(draft, kind === 'container' ? 'new_unit' : 'new_service')
    const group: GroupResource = {
      active: true,
      key: createdGroupId,
      kind,
      name: `${draft.manifest.managed_prefix} ${kind === 'container' ? 'New unit' : 'New service'}`,
      ...(parent ? { parent } : {}),
      ...(kind === 'leaf' ? { service_code: nextServiceCode(draft) } : {}),
    }
    draft.manifest.groups.push(group)
    if (kind === 'leaf') addLeafDependencies(draft, group)
  })
  return { project, key: createdGroupId ?? String() }
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
  if (!canMoveGroup(source, key, parent)) return source
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
      group.service_code = nextServiceCode(project)
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
  const removed = groupAndDescendantKeys(source, key)
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

export { customerEntryPoints }

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
