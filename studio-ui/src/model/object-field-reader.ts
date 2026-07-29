import type { StudioProject } from '../types'

export type ObjectFieldCollection = 'ticket_fields' | 'user_fields' | 'organization_fields' | 'group_fields'

export function objectFields(project: StudioProject, collection: ObjectFieldCollection) {
  switch (collection) {
    case 'ticket_fields': return project.manifest.object_manager.ticket_fields
    case 'user_fields': return project.manifest.object_manager.user_fields
    case 'organization_fields': return project.manifest.object_manager.organization_fields
    case 'group_fields': return project.manifest.object_manager.group_fields
  }
}
