import type { GroupResource, StudioProjectV2 } from '../../contracts'
import { finalize, mutateProject } from './mutate'
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

export { displayGroupName, isDescendant }

export function addGroup(
  source: StudioProjectV2,
  kind: 'container' | 'leaf',
  selectedKey?: string,
): { project: StudioProjectV2; key: string } {
  if (kind === 'container' && source.target_schema_version === '1.0') {
    return { project: source, key: '' }
  }
  let createdGroupId: string | undefined
  const project = mutateProject(source, (draft) => {
    const { bundle } = draft
    const selected = bundle.manifest.groups.find(
      (group) => group.key === selectedKey,
    )
    const parent = selected?.kind === 'container'
      ? selected.key
      : selected?.parent ?? rootGroup(bundle)?.key
    createdGroupId = uniqueGroupKey(bundle, kind === 'container' ? 'new_unit' : 'new_service')
    const group: GroupResource = {
      active: true,
      key: createdGroupId,
      kind,
      name: `${bundle.manifest.managed_prefix} ${kind === 'container' ? 'New unit' : 'New service'}`,
      ...(parent ? { parent } : {}),
      ...(kind === 'leaf' ? { service_code: nextServiceCode(bundle) } : {}),
    }
    bundle.manifest.groups.push(group)
    if (kind === 'leaf') addLeafDependencies(bundle, group)
  })
  return { project, key: createdGroupId ?? String() }
}

export function renameGroup(
  source: StudioProjectV2,
  key: string,
  name: string,
): StudioProjectV2 {
  const { bundle } = source
  const label = name.trim() || 'Untitled'
  if (!bundle.manifest.groups.some((group) => group.key === key)) return source
  return { ...source, bundle: { ...bundle, manifest: { ...bundle.manifest,
    groups: bundle.manifest.groups.map((group) => group.key === key ? { ...group, name: `${bundle.manifest.managed_prefix} ${label}` } : group),
    roles: bundle.manifest.roles.map((role) => role.key === key ? { ...role, name: `${bundle.manifest.managed_prefix} Role · ${label}` } : role),
  } } }
}

export function moveGroup(
  source: StudioProjectV2,
  key: string,
  parent: string,
): StudioProjectV2 {
  if (!canMoveGroup(source.bundle, key, parent)) return source
  return { ...source, bundle: { ...source.bundle, manifest: { ...source.bundle.manifest,
    groups: source.bundle.manifest.groups.map((group) => group.key === key ? { ...group, parent } : group),
  } } }
}

export function reorderGroup(
  source: StudioProjectV2,
  activeKey: string,
  overKey: string,
): StudioProjectV2 {
  const from = source.bundle.manifest.groups.findIndex((group) => group.key === activeKey)
  const to = source.bundle.manifest.groups.findIndex((group) => group.key === overKey)
  if (from < 0 || to < 0 || from === to) return source
  const groups = [...source.bundle.manifest.groups]
  const [moved] = groups.splice(from, 1)
  if (moved) groups.splice(to, 0, moved)
  return { ...source, bundle: { ...source.bundle, manifest: { ...source.bundle.manifest, groups } } }
}

export function setGroupKind(
  source: StudioProjectV2,
  key: string,
  kind: 'container' | 'leaf',
): StudioProjectV2 {
  const current = source.bundle.manifest.groups.find((group) => group.key === key)
  if (!current || current.kind === kind || current.parent === undefined) return source
  if (kind === 'container' && source.target_schema_version === '1.0') return source
  if (kind === 'leaf' && childrenOf(source.bundle, key).length > 0) return source
  return mutateProject(source, (project) => {
    const { bundle } = project
    const group = bundle.manifest.groups.find((item) => item.key === key)
    if (!group) return
    if (kind === 'container') {
      group.kind = 'container'
      delete group.service_code
      delete group.restricted
      removeLeafDependencies(bundle, new Set([key]))
    } else {
      group.kind = 'leaf'
      group.service_code = nextServiceCode(bundle)
      addLeafDependencies(bundle, group)
    }
  })
}

export function removeGroup(
  source: StudioProjectV2,
  key: string,
): StudioProjectV2 {
  const target = source.bundle.manifest.groups.find((group) => group.key === key)
  if (!target || target.parent === undefined) return source
  const removed = groupAndDescendantKeys(source.bundle, key)
  return mutateProject(source, (project) => {
    project.bundle.manifest.groups = project.bundle.manifest.groups.filter(
      (group) => !removed.has(group.key),
    )
    removeLeafDependencies(project.bundle, removed)
  })
}

export function setRestricted(
  source: StudioProjectV2,
  key: string,
  restricted: boolean,
): StudioProjectV2 {
  const groups = source.bundle.manifest.groups.map((group) => {
    if (group.key !== key || group.kind !== 'leaf') return group
    const updated = { ...group }
    if (restricted) updated.restricted = true
    else delete updated.restricted
    return updated
  })
  return finalize({ ...source, bundle: { ...source.bundle, manifest: { ...source.bundle.manifest, groups } } }, source)
}

export { customerEntryPoints }

export function setCustomerEntryPoint(
  source: StudioProjectV2,
  key: string,
  enabled: boolean,
): StudioProjectV2 {
  return mutateProject(source, (project) => {
    const { bundle } = project
    const group = bundle.manifest.groups.find((item) => item.key === key)
    if (!group || group.kind !== 'leaf') return
    const entries = new Set(customerEntryPoints(bundle))
    if (enabled) entries.add(key)
    else entries.delete(key)
    materializeCustomerEntryPoints(bundle, [...entries])
  })
}
