import {
  Building2,
  Check,
  ChevronRight,
  Plus,
  University,
} from 'lucide-react'
import { mutateProject } from '../project-model'
import { useStudio } from '../studio-state'
import { PageHeader } from '../ui'
import { ImportControl } from '../shell/ImportControl'
import type { SchemaVersion } from '../types'

export function Start() {
  const {
    project,
    projects,
    createNew,
    openProject,
    importError,
    updateProject,
  } = useStudio()
  const root = project.manifest.groups.find((group) => group.parent === undefined)
  const canUseSchema10 = Boolean(root)
    && project.manifest.groups.filter((group) => group.kind === 'container').length === 1
    && project.manifest.groups.every((group) =>
      group.key === root?.key || (group.kind === 'leaf' && group.parent === root?.key),
    )
  return (
    <section className="start-screen">
      <PageHeader
        title="Start a configuration"
        description="Choose a safe local starting point. Nothing is sent to a Zammad tenant."
      />
      {importError ? <p className="notice error">{importError}</p> : null}
      <div className="project-basics">
        <label className="field">
          Project name
          <input
            value={project.name}
            onChange={(event) => updateProject(mutateProject(project, (draft) => {
              draft.name = event.target.value.trimStart() || 'Untitled configuration'
            }))}
          />
        </label>
        <label className="field">
          Target schema
          <select
            value={project.target_schema_version}
            onChange={(event) => updateProject(mutateProject(project, (draft) => {
              draft.target_schema_version = event.target.value as SchemaVersion
            }))}
          >
            <option value="1.1">1.1 · nested units</option>
            <option value="1.0" disabled={!canUseSchema10}>1.0 · flat legacy structure</option>
          </select>
        </label>
        <p><strong>Schema {project.target_schema_version}</strong><small>{project.id}</small></p>
      </div>
      <div className="start-actions">
        <button className="start-action" type="button" onClick={() => void createNew('blank')}>
          <Plus size={21} />
          <span><strong>Blank project</strong><small>Begin with one root and one editable service.</small></span>
        </button>
        <button className="start-action" type="button" onClick={() => void createNew('example')}>
          <University size={21} />
          <span><strong>University template</strong><small>Open a complete, neutral service design covering every Queuewright policy family.</small></span>
        </button>
        <ImportControl />
      </div>
      <h2>Projects in this browser</h2>
      <div className="project-library">
        {projects.map((item) => (
          <button
            type="button"
            className={item.id === project.id ? 'project-row selected' : 'project-row'}
            onClick={() => void openProject(item.id)}
            key={item.id}
          >
            <Building2 size={19} />
            <span><strong>{item.name}</strong><small>{item.target_schema_version} · {item.id}</small></span>
            {item.id === project.id ? <Check size={18} /> : <ChevronRight size={18} />}
          </button>
        ))}
      </div>
    </section>
  )
}
