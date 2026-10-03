import type { Dispatch } from 'react'
import { api } from '../api/client'
import { loadActiveDraft, migrateLegacyDrafts } from '../persistence/drafts'
import type { BlueprintCompileResult, StudioProjectV2 } from '../contracts'
import { isV1Project, isV2Project } from '../contracts/runtime'
import { seedProject, type Action } from './reducer'

async function canonicalize(value: unknown): Promise<BlueprintCompileResult | undefined> {
  if (!isV1Project(value) && !isV2Project(value)) return undefined
  return api.compile(value)
}

export async function hydrateStudio(dispatch: Dispatch<Action>, cancelled: () => boolean): Promise<void> {
  let source: unknown
  let canonicalActive: StudioProjectV2 | undefined
  // A recovery seed must never reuse the quarantined record's key.
  const fallback = () => source === seedProject ? seedProject : { ...seedProject, id: `recovery-${crypto.randomUUID()}` }
  try {
    source = await loadActiveDraft() ?? seedProject
    if (cancelled()) return
    const result = await canonicalize(source)
    canonicalActive = result?.project
    if (cancelled()) return
    dispatch({ type: 'hydrate', active: canonicalActive ?? fallback(), projects: [], ...(result ? { result } : {}) })
    if (!canonicalActive) dispatch({ type: 'import:error', message: 'The stored active project was quarantined because authoritative validation failed.' })
  } catch {
    if (cancelled()) return
    dispatch({ type: 'hydrate', active: fallback(), projects: [] })
    dispatch({ type: 'import:error', message: 'The loopback compiler is unavailable; the bundled project is open but exports stay disabled.' })
  }
  if (cancelled()) return
  // The active editor is ready before any unrelated migration/validation starts.
  try {
    let failed = false
    const projects = await migrateLegacyDrafts(async (project) => {
      if (canonicalActive && JSON.stringify(project) === JSON.stringify(source)) return canonicalActive
      return (await api.compile(project)).project
    }, { cancelled, onError: () => { failed = true } })
    if (cancelled()) return
    dispatch({ type: 'projects:loaded', projects })
    if (failed) dispatch({ type: 'import:error', message: 'Some stored projects could not be migrated. Their original records are preserved; the active project remains open.' })
  } catch {
    if (!cancelled()) dispatch({ type: 'import:error', message: 'The browser project library could not be loaded. The active project remains open.' })
  }
}
