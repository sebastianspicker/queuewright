import type { ObjectFieldResource, StudioBundle } from '../../contracts'

export type ObjectFieldCollection = 'ticket_fields' | 'user_fields' | 'organization_fields' | 'group_fields'

export const objectFieldCollections: ObjectFieldCollection[] = [
  'ticket_fields',
  'user_fields',
  'organization_fields',
  'group_fields',
]

export function objectFields(project: StudioBundle, collection: ObjectFieldCollection) {
  switch (collection) {
    case 'ticket_fields': return project.manifest.object_manager.ticket_fields
    case 'user_fields': return project.manifest.object_manager.user_fields
    case 'organization_fields': return project.manifest.object_manager.organization_fields
    case 'group_fields': return project.manifest.object_manager.group_fields
  }
}

export function replaceObjectFields(
  project: StudioBundle,
  collection: ObjectFieldCollection,
  fields: ObjectFieldResource[],
): void {
  switch (collection) {
    case 'ticket_fields': project.manifest.object_manager.ticket_fields = fields; return
    case 'user_fields': project.manifest.object_manager.user_fields = fields; return
    case 'organization_fields': project.manifest.object_manager.organization_fields = fields; return
    case 'group_fields': project.manifest.object_manager.group_fields = fields; return
  }
}

export function ensureField(
  project: StudioBundle,
  collection: ObjectFieldCollection,
  suffix: string,
  options: string[],
): void {
  const name = `${project.manifest.technical_namespace}${suffix}`
  const fields = objectFields(project, collection)
  if (!fields.some((field) => field.name === name)) fields.push({ name, options, type: 'select' })
}
