import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, editableV2Draft, expandEditorResponse, StudioApiError } from './client'
import { exampleBundle, staticDemoProject } from '../data'
import type { StudioProjectV1 } from '../contracts'

afterEach(() => vi.unstubAllGlobals())

const compileResponse = {
  representation: 'editor-1' as const, project: staticDemoProject(),
  plan: { operations: [{ id: 'groups:service', desired_state: { name: 'Example' } }] },
  graph: { graph_hash: 'same-hash', nodes: [
    { id: 'groups:service', resource_kind: 'groups' },
    { id: 'capability:organization', desired: { enabled: true } },
  ] }, hashes: { graph: 'same-hash' },
}

function legacyProject(): StudioProjectV1 {
  const canonical = staticDemoProject()
  return {
    project_schema_version: '1.0', id: 'legacy-project', name: 'Legacy project',
    target_schema_version: canonical.target_schema_version,
    profile: canonical.bundle.profile, manifest: canonical.bundle.manifest,
    resource_ownership: canonical.bundle.resource_ownership,
    feature_state: canonical.bundle.feature_state,
  }
}

describe('api compile seam', () => {
  it('compiles a raw profile and manifest atomically without a V1 import request', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(compileResponse), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const bundle = exampleBundle()
    await api.compile(bundle)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v2/compile-editor')
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual(bundle)
  })

  it('sends only authored V2 fields and accepts the canonical replacement', async () => {
    const project = staticDemoProject()
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(compileResponse), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await api.compile(project)
    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))
    expect(body).toEqual({ project: editableV2Draft(project) })
    expect(body.project.workbook).toEqual({
      organization: project.workbook.organization,
      capability_decisions: expect.any(Object),
    })
    expect(Object.values(body.project.workbook.capability_decisions).every(
      (decision) => Object.keys(decision as object).sort().join(',') === 'completion,enabled',
    )).toBe(true)
  })

  it('wraps a V1 project instead of misclassifying its profile as a raw bundle', async () => {
    const project = legacyProject()
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(compileResponse), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await api.compile(project)
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ project })
  })

  it('preserves structured API errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 'invalid', path: 'project', message: 'bad input' }), { status: 400 })))
    await expect(api.compile(staticDemoProject())).rejects.toBeInstanceOf(StudioApiError)
  })
})


describe('compact artifact expansion', () => {
  it('restores operation desired state and bundle while preserving capability data and hashes', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(compileResponse))))
    const result = await api.compile(staticDemoProject())
    expect(result.bundle).toBe(result.project.bundle)
    expect(result.graph.nodes[0]?.desired).toEqual({ name: 'Example' })
    expect(result.graph.nodes[1]?.desired).toEqual({ enabled: true })
    expect(result.graph.graph_hash).toBe('same-hash')
    expect(result.hashes).toEqual(compileResponse.hashes)
    expect(result).not.toHaveProperty('representation')
  })

  it('rejects missing source operations instead of manufacturing export data', () => {
    const broken = { ...compileResponse, plan: { operations: [] } }
    expect(() => expandEditorResponse(broken as unknown as Parameters<typeof expandEditorResponse>[0]))
      .toThrow(StudioApiError)
  })

  it('rejects unknown transport versions', () => {
    const broken = { ...compileResponse, representation: 'future-version' }
    expect(() => expandEditorResponse(broken as unknown as Parameters<typeof expandEditorResponse>[0]))
      .toThrow('Unsupported local compiler response')
  })
})
