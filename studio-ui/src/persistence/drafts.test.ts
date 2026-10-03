import { IDBFactory, IDBObjectStore } from 'fake-indexeddb'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { staticDemoProject } from '../data'
import type { StudioProjectV1 } from '../contracts'
import { loadActiveDraft, loadDraft, migrateLegacyDrafts, saveDraft } from './drafts'

function legacyProject(id = 'legacy'): StudioProjectV1 {
  const canonical = staticDemoProject()
  return {
    project_schema_version: '1.0', id, name: id,
    target_schema_version: canonical.target_schema_version,
    profile: canonical.bundle.profile, manifest: canonical.bundle.manifest,
    resource_ownership: canonical.bundle.resource_ownership, feature_state: canonical.bundle.feature_state,
  }
}

function request<T>(value: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => { value.onsuccess = () => resolve(value.result); value.onerror = () => reject(value.error) })
}

async function seed(projects: unknown[], blueprints: unknown[] = [], active?: string): Promise<void> {
  const opening = indexedDB.open('queuewright-studio', 3)
  opening.onupgradeneeded = () => { for (const name of ['projects', 'blueprints', 'meta']) opening.result.createObjectStore(name) }
  const db = await request(opening)
  const tx = db.transaction(['projects', 'blueprints', 'meta'], 'readwrite')
  const committed = new Promise<void>((resolve, reject) => { tx.oncomplete = () => resolve(); tx.onabort = () => reject(tx.error) })
  for (const item of projects) tx.objectStore('projects').put(item, (item as { id: string }).id)
  for (const item of blueprints) tx.objectStore('blueprints').put(item, (item as { id: string }).id)
  if (active) tx.objectStore('meta').put(active, 'active-project')
  await committed
  db.close()
}

async function raw(store: string, key: string): Promise<unknown> {
  const db = await request(indexedDB.open('queuewright-studio'))
  try { return await request(db.transaction(store).objectStore(store).get(key)) } finally { db.close() }
}

const compile = async (project: StudioProjectV1) => ({ ...staticDemoProject(), id: project.id, name: project.name })

beforeEach(() => vi.stubGlobal('indexedDB', new IDBFactory()))
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('IndexedDB draft persistence', () => {
  it('upgrades legacy stores without overwriting projects or deleting original records', async () => {
    const current = { ...staticDemoProject(), id: 'shared', name: 'Current' }
    const legacy = legacyProject('shared')
    const blueprintOnly = legacyProject('blueprint-only')
    await seed([current], [legacy, blueprintOnly], 'shared')
    expect(await loadActiveDraft()).toEqual(current)
    expect(await loadDraft('blueprint-only')).toEqual(blueprintOnly)
    expect(await raw('blueprints', 'shared')).toEqual(legacy)
    expect(await loadActiveDraft()).toEqual(current)
  })

  it('writes only the authoritative store and selects the draft in the same transaction', async () => {
    const project = staticDemoProject()
    const put = vi.spyOn(IDBObjectStore.prototype, 'put')
    await saveDraft(project)
    expect(put.mock.instances.map((store) => (store as IDBObjectStore).name)).toEqual(['projects', 'meta'])
    expect(await loadActiveDraft()).toEqual(project)
    expect(await raw('blueprints', project.id)).toBeUndefined()
  })

  it('rolls back a failed save, including the active selection', async () => {
    const active = staticDemoProject()
    await saveDraft(active)
    const next = { ...active, id: 'next' }
    const original = IDBObjectStore.prototype.put
    vi.spyOn(IDBObjectStore.prototype, 'put').mockImplementation(function (this: IDBObjectStore, value, key) {
      if (this.name === 'meta') throw new DOMException('quota', 'QuotaExceededError')
      return original.call(this, value, key)
    })
    await expect(saveDraft(next)).rejects.toThrow('quota')
    expect(await loadDraft('next')).toBeUndefined()
    expect(await loadActiveDraft()).toEqual(active)
  })

  it('rejects an asynchronously aborted transaction and rolls back its writes', async () => {
    const original = IDBObjectStore.prototype.put
    vi.spyOn(IDBObjectStore.prototype, 'put').mockImplementation(function (this: IDBObjectStore, value, key) {
      const result = original.call(this, value, key)
      if (this.name === 'meta') result.addEventListener('success', () => this.transaction.abort())
      return result
    })
    const project = staticDemoProject()
    await expect(saveDraft(project)).rejects.toThrow()
    expect(await loadDraft(project.id)).toBeUndefined()
  })

  it('migrates only V1 once, preserves active metadata, and isolates partial failures', async () => {
    const active = staticDemoProject()
    const bad = legacyProject('bad')
    const good = legacyProject('good')
    await seed([active, good, bad], [], active.id)
    const compiler = vi.fn(async (project: StudioProjectV1) => {
      if (project.id === 'bad') throw new Error('invalid')
      return compile(project)
    })
    const onError = vi.fn()
    const migrated = await migrateLegacyDrafts(compiler, { onError })
    expect(migrated.map((project) => project.id)).toEqual(expect.arrayContaining([active.id, 'good']))
    expect(compiler).toHaveBeenCalledTimes(2)
    expect(onError).toHaveBeenCalledTimes(1)
    expect(await loadDraft('bad')).toEqual(bad)
    expect(await loadActiveDraft()).toEqual(active)
    compiler.mockClear()
    await migrateLegacyDrafts(compiler)
    expect(compiler).toHaveBeenCalledTimes(1)
    expect(compiler).toHaveBeenCalledWith(bad)
  })

  it('limits migrations to two in flight and stops queued work on cancellation', async () => {
    await seed(Array.from({ length: 6 }, (_, index) => legacyProject(`legacy-${index}`)))
    let cancelled = false
    const completions: Array<() => void> = []
    const compiler = vi.fn((project: StudioProjectV1) => new Promise<Awaited<ReturnType<typeof compile>>>((resolve) => {
      completions.push(() => { void compile(project).then(resolve) })
    }))
    const migration = migrateLegacyDrafts(compiler, { cancelled: () => cancelled })
    await vi.waitFor(() => expect(compiler).toHaveBeenCalledTimes(2))
    cancelled = true
    completions.forEach((complete) => complete())
    await migration
    expect(compiler).toHaveBeenCalledTimes(2)
    expect(await loadDraft('legacy-0')).toEqual(legacyProject('legacy-0'))
  })

  it('never overwrites a draft edited while its legacy validation is pending', async () => {
    const legacy = legacyProject()
    await seed([legacy], [], legacy.id)
    const edited = { ...staticDemoProject(), id: legacy.id, name: 'Intervening edit' }
    await migrateLegacyDrafts(async (project) => { await saveDraft(edited); return compile(project) })
    expect(await loadDraft(legacy.id)).toEqual(edited)
    expect(await loadActiveDraft()).toEqual(edited)
  })
})
