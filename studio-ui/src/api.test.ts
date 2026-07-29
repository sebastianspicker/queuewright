import { api, StudioApiError } from './api'
import { exampleProject } from './data'
import type { StudioProjectV2 } from './types'

const feature = {
  id: 'ticket_fields',
  name: 'Ticket fields',
  category: 'Intake & classification',
  description: 'Ticket fields',
  default_enabled: true,
  locked: true,
  settings: { collection: 'ticket_fields' },
  dependencies: [],
  locked_assurances: ['offline_only'],
}

function compileResponseFor(project: ReturnType<typeof exampleProject>) {
  return {
    artifact_filenames: [
      'university.project.json',
      'university.profile.json',
      'university.desired-state.json',
      'university.plan.json',
    ],
    hashes: { plan: 'a', manifest: 'b', profile: 'c', project: 'd' },
    issues: [],
    summary: { counts: {}, display_name: project.name, manifest_key: '', profile_hash: '', profile_key: 'university', source_hash: '' },
    project,
    profile: project.profile,
    manifest: project.manifest,
    plan: { counts: {}, operations: [], plan_hash: 'a', safety: {} },
  }
}

function blueprintFor(project: ReturnType<typeof exampleProject>): StudioProjectV2 {
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

describe('Studio API contract', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('uses the local catalog and wraps the canonical project', async () => {
    const project = exampleProject()
    const compileResponse = compileResponseFor(project)
    const blueprint = blueprintFor(project)
    const blueprintResponse = {
      project: blueprint,
      bundle: blueprint.bundle,
      plan: compileResponse.plan,
      graph: { nodes: [], graph_hash: 'graph' },
      hashes: { graph: 'graph', plan: 'a' },
      issues: [],
    }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ schema_version: '1.0', features: [feature] }), { status: 200, headers: { 'content-type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify(compileResponse), { status: 200, headers: { 'content-type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ project: blueprint }), { status: 200, headers: { 'content-type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify(blueprintResponse), { status: 200, headers: { 'content-type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)

    const catalog = await api.loadCatalog()
    const compiled = await api.compile(project)
    const migrated = await api.migrateProject(project)
    const compiledBlueprint = await api.compileBlueprint(blueprint)

    expect(catalog[0]).toMatchObject({ id: 'ticket_fields', locked: true })
    expect(compiled.project).toEqual(project)
    expect(migrated).toEqual(blueprint)
    expect(compiledBlueprint.graph.graph_hash).toBe('graph')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/catalog')
    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/compile-project')
    expect(JSON.parse(String(fetchMock.mock.calls[1][1].body))).toEqual({ project })
    expect(fetchMock.mock.calls[2][0]).toBe('/api/v2/migrate-project')
    expect(fetchMock.mock.calls[3][0]).toBe('/api/v2/compile-project')
  })

  it('preserves the structured local API error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ code: 'invalid_project', path: 'project', message: 'invalid bundle' }), { status: 422 }),
    ))
    await expect(api.compile(exampleProject())).rejects.toMatchObject({
      code: 'invalid_project',
      path: 'project',
      status: 422,
    } satisfies Partial<StudioApiError>)
  })
})
