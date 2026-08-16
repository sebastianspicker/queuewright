import type { GroupResource, StudioProject } from '../types'

export function uniqueGroupKey(project: StudioProject, stem: string): string {
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

export function canMoveGroup(
  source: StudioProject,
  key: string,
  parent: string,
): boolean {
  const group = source.manifest.groups.find((item) => item.key === key)
  const parentGroup = source.manifest.groups.find((item) => item.key === parent)
  return Boolean(
    group
      && parentGroup
      && group.parent !== undefined
      && parentGroup.kind === 'container'
      && key !== parent
      && !isDescendant(source, parent, key),
  )
}

export function groupAndDescendantKeys(
  project: StudioProject,
  key: string,
): Set<string> {
  const removed = new Set([key])
  let grew = true
  while (grew) {
    grew = false
    for (const group of project.manifest.groups) {
      if (group.parent && removed.has(group.parent) && !removed.has(group.key)) {
        removed.add(group.key)
        grew = true
      }
    }
  }
  return removed
}
