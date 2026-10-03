import {
  type StudioBundle,
  type StudioProjectV2,
} from '../../contracts'
import { cloneJson } from '../../contracts/runtime'

function humanize(value: string): string {
  return value
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function refreshPresentation(project: StudioBundle): void {
  const { object_manager: objectManager } = project.manifest
  const fields = [
    ...objectManager.ticket_fields,
    ...objectManager.user_fields,
    ...objectManager.organization_fields,
    ...objectManager.group_fields,
  ]
  const previousFields = new Map(Object.entries(project.profile.presentation.field_labels))
  project.profile.presentation.field_labels = Object.fromEntries(
    fields.map((field) => [
      field.name,
      previousFields.get(field.name)
        ?? humanize(field.name.replace(project.manifest.technical_namespace, '')),
    ]),
  )

  const previousOptions = new Map(Object.entries(project.profile.presentation.option_labels))
  const options = new Set(fields.flatMap((field) => field.options))
  project.profile.presentation.option_labels = Object.fromEntries(
    [...options].sort().map((option) => [
      option,
      previousOptions.get(option) ?? humanize(option),
    ]),
  )

  const previousWorkflows = new Map(Object.entries(project.profile.presentation.core_workflow_names))
  project.profile.presentation.core_workflow_names = Object.fromEntries(
    objectManager.core_workflows.map((workflow) => [
      workflow.key,
      previousWorkflows.get(workflow.key)
        ?? `${project.manifest.managed_prefix} CW · ${humanize(workflow.key)}`,
    ]),
  )

  const ticketLogicalNames = new Set(
    objectManager.ticket_fields.map((field) =>
      field.name.replace(project.manifest.technical_namespace, ''),
    ),
  )
  const defaults = new Map(Object.entries(project.profile.uat.defaults))
  project.profile.uat.defaults = Object.fromEntries(
    [...ticketLogicalNames].map((name) => [
      name,
      defaults.get(name) ?? null,
    ]),
  )
}

export function finalize(project: StudioProjectV2, source?: StudioProjectV2): StudioProjectV2 {
  const { bundle } = project
  let profile = bundle.profile
  let manifest = bundle.manifest
  if (profile.display_name !== project.name || profile.schema_version !== project.target_schema_version) {
    profile = { ...profile, display_name: project.name, schema_version: project.target_schema_version }
  }
  if (manifest.schema_version !== project.target_schema_version) manifest = { ...manifest, schema_version: project.target_schema_version }
  if (manifest.uat.ticket_count !== profile.uat.scenarios.length) {
    manifest = { ...manifest, uat: { ...manifest.uat, ticket_count: profile.uat.scenarios.length } }
  }
  if (!source || manifest.groups !== source.bundle.manifest.groups) {
    const restricted = manifest.groups.filter((group) => group.kind === 'leaf' && group.restricted === true).map((group) => group.key).sort()
    if (restricted.length !== manifest.reference_sets.S.length || restricted.some((key, index) => key !== manifest.reference_sets.S[index])) {
      manifest = { ...manifest, reference_sets: { ...manifest.reference_sets, S: restricted } }
    }
  }
  if (!source || manifest.object_manager !== source.bundle.manifest.object_manager
    || manifest.technical_namespace !== source.bundle.manifest.technical_namespace
    || manifest.managed_prefix !== source.bundle.manifest.managed_prefix) {
    profile = { ...profile, presentation: { ...profile.presentation }, uat: { ...profile.uat } }
    refreshPresentation({ ...bundle, profile, manifest })
  }
  return profile === bundle.profile && manifest === bundle.manifest ? project
    : { ...project, bundle: { ...bundle, profile, manifest } }
}

export function renameProject(source: StudioProjectV2, name: string): StudioProjectV2 {
  return finalize({ ...source, name }, source)
}

export function setTargetSchema(source: StudioProjectV2, target_schema_version: StudioProjectV2['target_schema_version']): StudioProjectV2 {
  return finalize({ ...source, target_schema_version }, source)
}

export function mutateProject(
  source: StudioProjectV2,
  mutation: (project: StudioProjectV2) => void,
): StudioProjectV2 {
  const project = cloneJson(source)
  mutation(project)
  return finalize(project)
}
