import { api } from './api'
import type { Dispatch } from 'react'
import type {
  ManifestDocument,
  ProfileDocument,
  StudioProject,
  StudioProjectV2,
} from './types'

type ReplaceStudio = Dispatch<[StudioProject, StudioProjectV2]>

export function readFile(file: Blob): Promise<string> {
  if (typeof file.text === 'function') return file.text()
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => { resolve(String(reader.result ?? '')) }
    reader.onerror = () => { reject(reader.error ?? new Error('Unable to read import file')) }
    reader.readAsText(file)
  })
}

export function projectValue(value: unknown): StudioProject | undefined {
  if (typeof value !== 'object' || value === null) return undefined
  return (value as { project_schema_version?: unknown }).project_schema_version === '1.0'
    ? value as StudioProject
    : undefined
}

export function blueprintValue(value: unknown): StudioProjectV2 | undefined {
  if (typeof value !== 'object' || value === null) return undefined
  return (value as { project_schema_version?: unknown }).project_schema_version === '2.0'
    ? value as StudioProjectV2
    : undefined
}

export function profileValue(value: unknown): ProfileDocument | undefined {
  if (typeof value !== 'object' || value === null) return undefined
  return typeof (value as { profile_key?: unknown }).profile_key === 'string'
    ? value as ProfileDocument
    : undefined
}

export function manifestValue(value: unknown): ManifestDocument | undefined {
  if (typeof value !== 'object' || value === null) return undefined
  return typeof (value as { manifest_key?: unknown }).manifest_key === 'string'
    ? value as ManifestDocument
    : undefined
}

export function projectFromBlueprint(blueprint: StudioProjectV2): StudioProject {
  return {
    project_schema_version: '1.0',
    id: blueprint.id,
    name: blueprint.name,
    target_schema_version: blueprint.target_schema_version,
    ...blueprint.bundle,
  }
}

export async function importValues(
  values: unknown[],
  onReplace: ReplaceStudio,
): Promise<void> {
  const blueprint = values.map(blueprintValue).find(Boolean)
  if (blueprint) {
    await importBlueprint(blueprint, onReplace)
    return
  }
  const project = values.map(projectValue).find(Boolean)
  if (project) {
    await compileMigrateAndReplace(project, onReplace)
    return
  }
  const bundle = findBundle(values)
  if (!bundle) throw new Error('A profile and desired-state manifest are both required.')
  await importProfileAndManifest(bundle.profile, bundle.manifest, onReplace)
}

async function importBlueprint(
  blueprint: StudioProjectV2,
  onReplace: ReplaceStudio,
): Promise<void> {
  const compiled = await api.compileBlueprint(blueprint)
  const result = await api.compile(projectFromBlueprint(compiled.project))
  onReplace([result.project, compiled.project])
}

async function importProfileAndManifest(
  profile: ProfileDocument,
  manifest: ManifestDocument,
  onReplace: ReplaceStudio,
): Promise<void> {
  const project = await api.importBundle(profile, manifest)
  await compileMigrateAndReplace(project, onReplace)
}

async function compileMigrateAndReplace(
  project: StudioProject,
  onReplace: ReplaceStudio,
): Promise<void> {
  const result = await api.compile(project)
  const blueprint = await api.migrateProject(result.project)
  onReplace([result.project, blueprint])
}

export async function importFilesIntoStudio(
  input: FileList | File[],
  onReplace: ReplaceStudio,
): Promise<string | undefined> {
  const files = [...input]
  const validationError = importFileValidation(files)
  if (validationError) return validationError
  try {
    const values = await Promise.all(files.map(async (file) => JSON.parse(await readFile(file))))
    await importValues(values, onReplace)
  } catch (error) {
    return error instanceof Error ? error.message : 'The selected JSON could not be imported.'
  }
  return undefined
}

function importFileValidation(files: File[]): string | undefined {
  if (files.length < 1 || files.length > 2) return 'Choose one project or bundle file, or a profile and manifest pair.'
  return files.some((file) => file.size > 2 * 1024 * 1024) ? 'Each import file must be 2 MiB or smaller.' : undefined
}

export function findBundle(values: unknown[]): { profile: ProfileDocument; manifest: ManifestDocument } | undefined {
  const bundle = values.find((value) =>
    typeof value === 'object' && value !== null
      && profileValue((value as { profile?: unknown }).profile)
      && manifestValue((value as { manifest?: unknown }).manifest),
  ) as { profile: ProfileDocument; manifest: ManifestDocument } | undefined
  if (bundle) return bundle
  const profile = values.map(profileValue).find(Boolean)
  const manifest = values.map(manifestValue).find(Boolean)
  return profile && manifest ? { profile, manifest } : undefined
}
