import { syncOwnership } from '../data'
import type {
  ResourceOwner,
  StudioProject,
} from '../types'

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function humanize(value: string): string {
  return value
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function refreshPresentation(project: StudioProject): void {
  const { object_manager: objectManager } = project.manifest
  const fields = [
    ...objectManager.ticket_fields,
    ...objectManager.user_fields,
    ...objectManager.organization_fields,
    ...objectManager.group_fields,
  ]
  const previousFields = project.profile.presentation.field_labels
  project.profile.presentation.field_labels = Object.fromEntries(
    fields.map((field) => [
      field.name,
      previousFields[field.name]
        ?? humanize(field.name.replace(project.manifest.technical_namespace, '')),
    ]),
  )

  const previousOptions = project.profile.presentation.option_labels
  const options = new Set(fields.flatMap((field) => field.options))
  project.profile.presentation.option_labels = Object.fromEntries(
    [...options].sort().map((option) => [
      option,
      previousOptions[option] ?? humanize(option),
    ]),
  )

  const previousWorkflows = project.profile.presentation.core_workflow_names
  project.profile.presentation.core_workflow_names = Object.fromEntries(
    objectManager.core_workflows.map((workflow) => [
      workflow.key,
      previousWorkflows[workflow.key]
        ?? `${project.manifest.managed_prefix} CW · ${humanize(workflow.key)}`,
    ]),
  )

  const ticketLogicalNames = new Set(
    objectManager.ticket_fields.map((field) =>
      field.name.replace(project.manifest.technical_namespace, ''),
    ),
  )
  project.profile.uat.defaults = Object.fromEntries(
    [...ticketLogicalNames].map((name) => [
      name,
      project.profile.uat.defaults[name] ?? null,
    ]),
  )
}

export function finalize(
  project: StudioProject,
  previousOwnership: Record<string, ResourceOwner>,
): StudioProject {
  project.profile.display_name = project.name
  project.profile.schema_version = project.target_schema_version
  project.manifest.schema_version = project.target_schema_version
  project.manifest.uat.ticket_count = project.profile.uat.scenarios.length
  project.manifest.reference_sets.S = project.manifest.groups
    .filter((group) => group.kind === 'leaf' && group.restricted === true)
    .map((group) => group.key)
    .sort()
  refreshPresentation(project)
  project.resource_ownership = syncOwnership(
    project.profile,
    project.manifest,
    previousOwnership,
  )
  return project
}

export { clone }

export function mutateProject(
  source: StudioProject,
  mutation: (project: StudioProject) => void,
): StudioProject {
  const project = clone(source)
  mutation(project)
  return finalize(project, source.resource_ownership)
}
