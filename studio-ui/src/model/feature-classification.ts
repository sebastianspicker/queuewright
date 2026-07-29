import type { FeatureId, StudioProject } from '../types'
import { objectFields, type ObjectFieldCollection } from './object-field-reader'

function ensureField(
  project: StudioProject,
  collection: ObjectFieldCollection,
  suffix: string,
  options: string[],
): void {
  const name = `${project.manifest.technical_namespace}${suffix}`
  const fields = objectFields(project, collection)
  if (!fields.some((field) => field.name === name)) fields.push({ name, options, type: 'select' })
}

export function addClassificationResources(project: StudioProject, feature: FeatureId): boolean {
  switch (feature) {
    case 'ticket_fields':
      ensureField(project, 'ticket_fields', 'service_code', project.manifest.groups.flatMap((group) => group.service_code ? [group.service_code] : []))
      return true
    case 'user_classification':
      ensureField(project, 'user_fields', 'user_population', ['students', 'faculty', 'professional_services'])
      return true
    case 'organization_classification':
      ensureField(project, 'organization_fields', 'organization_class', ['students', 'faculty', 'professional_services'])
      return true
    case 'group_classification':
      ensureField(project, 'group_fields', 'group_class', ['container', 'service', 'restricted'])
      return true
    default:
      return false
  }
}
