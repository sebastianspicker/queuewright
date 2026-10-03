import type { StudioProjectV1, StudioProjectV2 } from '../contracts'
import { isV1Project, isV2Project } from '../contracts/runtime'

const DB_NAME = 'queuewright-studio'
const DB_VERSION = 4
const PROJECTS = 'projects'
const BLUEPRINTS = 'blueprints'
const META = 'meta'
const ACTIVE_PROJECT = 'active-project'

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(PROJECTS)) db.createObjectStore(PROJECTS)
      if (!db.objectStoreNames.contains(META)) db.createObjectStore(META)
      if (!db.objectStoreNames.contains(BLUEPRINTS)) db.createObjectStore(BLUEPRINTS)
      // Preserve legacy records verbatim, including quarantined data. Projects wins
      // on collisions; the old store is retained for recovery and migration compatibility.
      const transaction = request.transaction!
      const projects = transaction.objectStore(PROJECTS)
      const cursor = transaction.objectStore(BLUEPRINTS).openCursor()
      cursor.onsuccess = () => {
        const entry = cursor.result
        if (!entry) return
        const existing = projects.getKey(entry.key)
        existing.onsuccess = () => {
          if (existing.result === undefined) projects.put(entry.value, entry.key)
          entry.continue()
        }
      }
    }
    request.onsuccess = () => {
      request.result.onversionchange = () => request.result.close()
      resolve(request.result)
    }
    request.onerror = () => reject(request.error)
  })
}

async function withDb<T>(operation: (db: IDBDatabase) => Promise<T>): Promise<T> {
  const db = await openDb()
  try { return await operation(db) } finally { db.close() }
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

function writeTransaction(db: IDBDatabase, stores: string[], write: (transaction: IDBTransaction) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(stores, 'readwrite')
    transaction.oncomplete = () => resolve()
    transaction.onabort = () => reject(transaction.error ?? new Error('Browser save aborted.'))
    try { write(transaction) } catch (error) { transaction.abort(); reject(error) }
  })
}

function hasIdentity(value: unknown): value is StudioProjectV1 | StudioProjectV2 {
  return (isV1Project(value) || isV2Project(value)) && typeof value.id === 'string' && typeof value.name === 'string'
}

/** Projects is authoritative; saving a draft and selecting it commit atomically. */
export async function saveDraft(project: StudioProjectV2): Promise<void> {
  await withDb((db) => writeTransaction(db, [PROJECTS, META], (transaction) => {
    transaction.objectStore(PROJECTS).put(project, project.id)
    transaction.objectStore(META).put(project.id, ACTIVE_PROJECT)
  }))
}

async function storedRecords(): Promise<unknown[]> {
  return withDb((db) => requestResult(db.transaction(PROJECTS).objectStore(PROJECTS).getAll()))
}

export async function loadDraft(id: string): Promise<unknown> {
  return withDb((db) => requestResult(db.transaction(PROJECTS).objectStore(PROJECTS).get(id)))
}

export async function loadActiveDraft(): Promise<unknown> {
  return withDb(async (db) => {
    const transaction = db.transaction([PROJECTS, META])
    const id = await requestResult(transaction.objectStore(META).get(ACTIVE_PROJECT))
    if (typeof id === 'string') {
      const project = await requestResult(transaction.objectStore(PROJECTS).get(id))
      if (project !== undefined) return project
    }
    const records = await requestResult(transaction.objectStore(PROJECTS).getAll())
    return records.filter(hasIdentity).sort((left, right) => left.name.localeCompare(right.name)).at(0)
  })
}

interface MigrationOptions {
  cancelled?: () => boolean
  onError?: (error: unknown) => void
}

async function migrateRecords(
  records: unknown[],
  compile: (project: StudioProjectV1) => Promise<StudioProjectV2>,
  options: MigrationOptions,
  save: (source: StudioProjectV1, project: StudioProjectV2) => Promise<void>,
): Promise<StudioProjectV2[]> {
  const projects: StudioProjectV2[] = []
  let index = 0
  // Keep startup traffic bounded, and isolate each quarantined/failed draft.
  const worker = async () => {
    while (index < records.length && !options.cancelled?.()) {
      const record = records[index++]
      if (!hasIdentity(record)) continue
      if (isV2Project(record)) { projects.push(record); continue }
      try {
        const project = await compile(record)
        if (options.cancelled?.()) break
        if (!isV2Project(project) || project.id !== record.id) throw new Error('Migration changed the stored project identity.')
        await save(record, project)
        projects.push(project)
      } catch (error) { if (!options.cancelled?.()) options.onError?.(error) }
    }
  }
  await Promise.all([worker(), worker()])
  return projects.sort((left, right) => left.name.localeCompare(right.name))
}

async function saveMigration(source: StudioProjectV1, project: StudioProjectV2, cancelled?: () => boolean): Promise<void> {
  await withDb((db) => writeTransaction(db, [PROJECTS], (transaction) => {
    const store = transaction.objectStore(PROJECTS)
    const request = store.get(source.id)
    request.onsuccess = () => {
      // Validation ran outside the transaction. Never overwrite an intervening
      // edit or another migration, and never change the active-project pointer.
      if (!cancelled?.() && JSON.stringify(request.result) === JSON.stringify(source)) store.put(project, source.id)
    }
  }))
}

/** Only successfully validated V1 records are rewritten. V2 records are read-only. */
export async function migrateLegacyDrafts(
  compile: (project: StudioProjectV1) => Promise<StudioProjectV2>,
  options: MigrationOptions = {},
): Promise<StudioProjectV2[]> {
  return migrateRecords(await storedRecords(), compile, options, (source, project) => saveMigration(source, project, options.cancelled))
}
