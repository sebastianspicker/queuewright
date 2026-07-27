import type { StudioProject, StudioProjectV2 } from './types'

const DB_NAME = 'queuewright-studio'
const DB_VERSION = 3
const PROJECTS = 'projects'
const BLUEPRINTS = 'blueprints'
const META = 'meta'
const ACTIVE_PROJECT = 'active-project'

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(PROJECTS)) {
        request.result.createObjectStore(PROJECTS)
      }
      if (!request.result.objectStoreNames.contains(META)) {
        request.result.createObjectStore(META)
      }
      if (!request.result.objectStoreNames.contains(BLUEPRINTS)) {
        request.result.createObjectStore(BLUEPRINTS)
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

function transactionComplete(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve()
    transaction.onabort = () => reject(transaction.error)
    transaction.onerror = () => reject(transaction.error)
  })
}

export async function saveDraft(
  project: StudioProject,
  blueprint?: StudioProjectV2,
): Promise<void> {
  const db = await openDb()
  const transaction = db.transaction(
    [PROJECTS, BLUEPRINTS, META],
    'readwrite',
  )
  const committed = transactionComplete(transaction)
  const writes: Array<Promise<unknown>> = [
    requestResult(transaction.objectStore(PROJECTS).put(project, project.id)),
    requestResult(transaction.objectStore(META).put(project.id, ACTIVE_PROJECT)),
  ]
  if (blueprint) {
    writes.push(requestResult(
      transaction.objectStore(BLUEPRINTS).put(blueprint, project.id),
    ))
  }
  await Promise.all(writes)
  await committed
  db.close()
}

export async function loadBlueprint(
  id: string,
): Promise<StudioProjectV2 | undefined> {
  const db = await openDb()
  const result = await requestResult(
    db.transaction(BLUEPRINTS).objectStore(BLUEPRINTS).get(id),
  )
  db.close()
  return result as StudioProjectV2 | undefined
}

export async function loadDraft(
  id: string,
): Promise<StudioProject | undefined> {
  const db = await openDb()
  const result = await requestResult(
    db.transaction(PROJECTS).objectStore(PROJECTS).get(id),
  )
  db.close()
  return result as StudioProject | undefined
}

export async function listDrafts(): Promise<StudioProject[]> {
  const db = await openDb()
  const result = await requestResult(
    db.transaction(PROJECTS).objectStore(PROJECTS).getAll(),
  )
  db.close()
  return [...(result as StudioProject[])].sort((left, right) =>
    left.name.localeCompare(right.name),
  )
}

export async function loadActiveDraft(): Promise<StudioProject | undefined> {
  const db = await openDb()
  const transaction = db.transaction([PROJECTS, META])
  const id = await requestResult(
    transaction.objectStore(META).get(ACTIVE_PROJECT),
  )
  if (typeof id !== 'string') {
    db.close()
    return undefined
  }
  const project = await requestResult(
    transaction.objectStore(PROJECTS).get(id),
  )
  db.close()
  return project as StudioProject | undefined
}
