import type { Dispatch } from 'react'
import { api } from '../api'
import { listDrafts, loadActiveDraft, loadBlueprint } from '../storage'
import type { StudioProject, StudioProjectV2 } from '../types'
import { rebaseBlueprint } from './blueprint'
import { seedProject, type Action } from './model'

interface HydrationResult {
  active: StudioProject
  blueprint?: StudioProjectV2
  projects: StudioProject[]
  warning?: string
}

async function validateStoredProject(project?: StudioProject): Promise<StudioProject | undefined> {
  if (!project) return undefined
  try {
    return (await api.compile(project)).project
  } catch {
    return undefined
  }
}

function bundledProject(): Promise<StudioProject> {
  return api.importBundle(seedProject.profile, seedProject.manifest).catch(() => seedProject)
}

async function restoreBlueprint(project: StudioProject): Promise<StudioProjectV2 | undefined> {
  const stored = await loadBlueprint(project.id)
  if (!stored) return undefined
  try {
    const migrated = await api.migrateProject(project)
    return (await api.compileBlueprint(rebaseBlueprint(migrated, stored))).project
  } catch {
    return undefined
  }
}

async function resolveHydration(
  storedActive: StudioProject | undefined,
  projects: StudioProject[],
): Promise<HydrationResult> {
  let active = await validateStoredProject(storedActive)
  let warning: string | undefined
  if (storedActive && !active) {
    warning = 'The stored active project was quarantined because authoritative validation failed.'
  }
  if (!active) {
    active = await bundledProject()
    if (active === seedProject) {
      warning ??= 'The loopback compiler is unavailable; the bundled project is open but exports stay disabled.'
    }
  }
  return { active, blueprint: await restoreBlueprint(active), projects, warning }
}

function applyHydration(
  dispatch: Dispatch<Action>,
  result: HydrationResult,
  isCancelled: () => boolean,
): void {
  if (isCancelled()) return
  dispatch({
    type: 'hydrate',
    active: result.active,
    blueprint: result.blueprint,
    projects: result.projects,
  })
  if (result.warning) dispatch({ type: 'import:error', message: result.warning })
}

export function hydrateStudio(
  dispatch: Dispatch<Action>,
  isCancelled: () => boolean,
): Promise<void> {
  return Promise.all([loadActiveDraft(), listDrafts()])
    .then(([storedActive, projects]) => resolveHydration(storedActive, projects))
    .then((result) => { applyHydration(dispatch, result, isCancelled) })
    .catch(() => {
      if (!isCancelled()) dispatch({ type: 'hydrate', projects: [] })
    })
}
