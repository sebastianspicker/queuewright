import { api } from './api'
import { exampleProject } from './data'
import {
  importFilesIntoStudio,
  importValues,
  projectFromBlueprint,
} from './studio-import'
import type { StudioProject, StudioProjectV2 } from './types'

function blueprintFor(project: StudioProject): StudioProjectV2 {
  return {
    project_schema_version: '2.0',
    id: project.id,
    name: project.name,
    target_schema_version: project.target_schema_version,
    workbook: {
      organization: { name: project.name },
      services: [],
      policies: {},
      capability_decisions: {},
      uat: {},
    },
    extensions: {},
    bundle: {
      profile: project.profile,
      manifest: project.manifest,
      resource_ownership: project.resource_ownership,
      feature_state: project.feature_state,
    },
  }
}

function compiled(project: StudioProject) {
  return { project } as Awaited<ReturnType<typeof api.compile>>
}

describe('Studio import', () => {
  afterEach(() => vi.restoreAllMocks())

  it('prefers a Blueprint and compiles it before compiling its V1 projection', async () => {
    const project = exampleProject()
    const blueprint = blueprintFor(project)
    const compiledBlueprint = { ...blueprint, name: 'Compiled blueprint' }
    const compiledProject = { ...project, name: 'Compiled project' }
    const replace = vi.fn()
    const compileBlueprint = vi.spyOn(api, 'compileBlueprint').mockResolvedValue({ project: compiledBlueprint } as never)
    const compile = vi.spyOn(api, 'compile').mockResolvedValue(compiled(compiledProject))
    const migrate = vi.spyOn(api, 'migrateProject')

    await importValues([project, { profile: project.profile, manifest: project.manifest }, blueprint], replace)

    expect(compileBlueprint).toHaveBeenCalledExactlyOnceWith(blueprint)
    expect(compile).toHaveBeenCalledExactlyOnceWith(projectFromBlueprint(compiledBlueprint))
    expect(migrate).not.toHaveBeenCalled()
    expect(replace).toHaveBeenCalledExactlyOnceWith([compiledProject, compiledBlueprint])
  })

  it('compiles, migrates, then replaces a direct V1 project', async () => {
    const project = exampleProject()
    const compiledProject = { ...project, name: 'Compiled project' }
    const migrated = blueprintFor(compiledProject)
    const replace = vi.fn()
    const compile = vi.spyOn(api, 'compile').mockResolvedValue(compiled(compiledProject))
    const migrate = vi.spyOn(api, 'migrateProject').mockResolvedValue(migrated)

    await importValues([project], replace)

    expect(compile).toHaveBeenCalledExactlyOnceWith(project)
    expect(migrate).toHaveBeenCalledExactlyOnceWith(compiledProject)
    expect(replace).toHaveBeenCalledExactlyOnceWith([compiledProject, migrated])
  })

  it('rejects a Blueprint compilation failure without downstream calls or replacement', async () => {
    const project = exampleProject()
    const blueprint = blueprintFor(project)
    const failure = new Error('Blueprint compilation refused')
    const replace = vi.fn()
    const compileBlueprint = vi.spyOn(api, 'compileBlueprint').mockRejectedValue(failure)
    const compile = vi.spyOn(api, 'compile')
    const migrate = vi.spyOn(api, 'migrateProject')

    await expect(importValues([blueprint], replace)).rejects.toBe(failure)

    expect(compileBlueprint).toHaveBeenCalledExactlyOnceWith(blueprint)
    expect(compile).not.toHaveBeenCalled()
    expect(migrate).not.toHaveBeenCalled()
    expect(replace).not.toHaveBeenCalled()
  })

  it.each([
    ['an embedded bundle', (project: StudioProject) => [{ profile: project.profile, manifest: project.manifest }]],
    ['separate profile and manifest files', (project: StudioProject) => [project.profile, project.manifest]],
  ])('imports %s through the same compile-migrate-replace path', async (_description, valuesFor) => {
    const project = exampleProject()
    const imported = { ...project, name: 'Imported project' }
    const compiledProject = { ...imported, name: 'Compiled project' }
    const migrated = blueprintFor(compiledProject)
    const replace = vi.fn()
    const importBundle = vi.spyOn(api, 'importBundle').mockResolvedValue(imported)
    const compile = vi.spyOn(api, 'compile').mockResolvedValue(compiled(compiledProject))
    const migrate = vi.spyOn(api, 'migrateProject').mockResolvedValue(migrated)

    await importValues(valuesFor(project), replace)

    expect(importBundle).toHaveBeenCalledExactlyOnceWith(project.profile, project.manifest)
    expect(compile).toHaveBeenCalledExactlyOnceWith(imported)
    expect(migrate).toHaveBeenCalledExactlyOnceWith(compiledProject)
    expect(replace).toHaveBeenCalledExactlyOnceWith([compiledProject, migrated])
  })

  it('rejects a bundle import failure without downstream calls or replacement', async () => {
    const project = exampleProject()
    const failure = new Error('Bundle import refused')
    const replace = vi.fn()
    const importBundle = vi.spyOn(api, 'importBundle').mockRejectedValue(failure)
    const compile = vi.spyOn(api, 'compile')
    const migrate = vi.spyOn(api, 'migrateProject')

    await expect(importValues([{ profile: project.profile, manifest: project.manifest }], replace)).rejects.toBe(failure)

    expect(importBundle).toHaveBeenCalledExactlyOnceWith(project.profile, project.manifest)
    expect(compile).not.toHaveBeenCalled()
    expect(migrate).not.toHaveBeenCalled()
    expect(replace).not.toHaveBeenCalled()
  })

  it('enforces the import count and size limits before parsing or calling the API', async () => {
    const replace = vi.fn()
    const compile = vi.spyOn(api, 'compile')
    const file = new File(['{}'], 'project.json', { type: 'application/json' })
    const oversized = new File(['x'.repeat(2 * 1024 * 1024 + 1)], 'large.json', { type: 'application/json' })

    await expect(importFilesIntoStudio([], replace)).resolves.toBe('Choose one project or bundle file, or a profile and manifest pair.')
    await expect(importFilesIntoStudio([file, file, file], replace)).resolves.toBe('Choose one project or bundle file, or a profile and manifest pair.')
    await expect(importFilesIntoStudio([oversized], replace)).resolves.toBe('Each import file must be 2 MiB or smaller.')
    expect(compile).not.toHaveBeenCalled()
    expect(replace).not.toHaveBeenCalled()
  })

  it('returns malformed JSON errors without replacing Studio state', async () => {
    const replace = vi.fn()
    const compile = vi.spyOn(api, 'compile')
    const malformed = new File(['{'], 'broken.json', { type: 'application/json' })

    const message = await importFilesIntoStudio([malformed], replace)

    expect(message).toBe("Expected property name or '}' in JSON at position 1 (line 1 column 2)")
    expect(compile).not.toHaveBeenCalled()
    expect(replace).not.toHaveBeenCalled()
  })

  it('returns a compile failure without migrating or replacing Studio state', async () => {
    const project = exampleProject()
    const replace = vi.fn()
    const compile = vi.spyOn(api, 'compile').mockRejectedValue(new Error('Compilation refused'))
    const migrate = vi.spyOn(api, 'migrateProject')

    const message = await importFilesIntoStudio([
      new File([JSON.stringify(project)], 'project.json', { type: 'application/json' }),
    ], replace)

    expect(message).toBe('Compilation refused')
    expect(compile).toHaveBeenCalledExactlyOnceWith(project)
    expect(migrate).not.toHaveBeenCalled()
    expect(replace).not.toHaveBeenCalled()
  })

  it('returns API failures and never replaces state after a partial import', async () => {
    const project = exampleProject()
    const compiledProject = { ...project, name: 'Compiled project' }
    const replace = vi.fn()
    const compile = vi.spyOn(api, 'compile').mockResolvedValue(compiled(compiledProject))
    const migrate = vi.spyOn(api, 'migrateProject').mockRejectedValue(new Error('Migration refused'))

    const message = await importFilesIntoStudio([
      new File([JSON.stringify(project)], 'project.json', { type: 'application/json' }),
    ], replace)

    expect(message).toBe('Migration refused')
    expect(compile).toHaveBeenCalledExactlyOnceWith(project)
    expect(migrate).toHaveBeenCalledExactlyOnceWith(compiledProject)
    expect(replace).not.toHaveBeenCalled()
  })
})
