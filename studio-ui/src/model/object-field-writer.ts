import type { ObjectFieldResource, StudioProject } from '../types'
import type { ObjectFieldCollection } from './object-field-reader'

export function replaceObjectFields(
  project: StudioProject,
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
