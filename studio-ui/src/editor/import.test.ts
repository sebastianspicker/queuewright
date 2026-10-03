import { afterEach, describe, expect, it, vi } from 'vitest'
import { importFilesIntoStudio, importValues } from './import'
import { exampleBundle, staticDemoProject } from '../data'
import type { StudioProjectV1 } from '../contracts'

afterEach(() => vi.unstubAllGlobals())

function legacyProject(): StudioProjectV1 {
  const canonical = staticDemoProject()
  return {
    project_schema_version: '1.0', id: 'legacy-import', name: 'Legacy import',
    target_schema_version: canonical.target_schema_version,
    profile: canonical.bundle.profile, manifest: canonical.bundle.manifest,
    resource_ownership: canonical.bundle.resource_ownership,
    feature_state: canonical.bundle.feature_state,
  }
}

describe('importFilesIntoStudio', () => {
  it('rejects transactional import limits before reading files', async () => {
    await expect(importFilesIntoStudio([])).rejects.toThrow('Choose one project')
    await expect(importFilesIntoStudio([new File(['x'], 'a.json'), new File(['x'], 'b.json'), new File(['x'], 'c.json')])).rejects.toThrow('Choose one project')
  })
  it('reports malformed input without invoking the replacement path', async () => {
    const file = new File(['not json'], 'broken.json', { type: 'application/json' })
    await expect(importFilesIntoStudio([file])).rejects.toThrow()
    expect(vi.isMockFunction(fetch)).toBe(false)
  })
  it('compiles a profile and manifest in one V2 request', async () => {
    const bundle = exampleBundle()
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ representation: 'editor-1', project: staticDemoProject(), plan: { operations: [] }, graph: { nodes: [] }, hashes: {} }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await importValues([bundle.profile, bundle.manifest])
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v2/compile-editor')
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual(bundle)
  })
  it('keeps V1 at the import boundary and sends it as a project payload', async () => {
    const project = legacyProject()
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ representation: 'editor-1', project: staticDemoProject(), plan: { operations: [] }, graph: { nodes: [] }, hashes: {} }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await importValues([project])
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ project })
  })
})
