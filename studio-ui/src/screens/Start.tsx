import { ArrowRight } from 'lucide-react'
import { renameProject, setTargetSchema } from '../editor/model'
import { useStudio } from '../editor/context'
import { ImportControl } from '../components/ImportControl'
import { EmptyState, PageHeader, SectionHeading } from '../components/ui'
import type { SchemaVersion } from '../contracts'

export function Start() {
  const {
    project,
    projects,
    createNew,
    openProject,
    importError,
    updateProject,
    demoMode,
  } = useStudio()
  const { bundle } = project
  const root = bundle.manifest.groups.find((group) => group.parent === undefined)
  const canUseSchema10 = Boolean(root)
    && bundle.manifest.groups.filter((group) => group.kind === 'container').length === 1
    && bundle.manifest.groups.every((group) =>
      group.key === root?.key || (group.kind === 'leaf' && group.parent === root?.key),
    )
  return (
    <section className="start-screen">
      <PageHeader
        title="Open or start a project"
        description={demoMode
          ? 'This static demo runs on bundled fictional data. Edits reset when the page reloads, and nothing is validated or saved.'
          : 'Projects are drafted and kept on this machine. Nothing on these sheets connects to, or changes, a Zammad tenant.'}
      />
      {importError ? <p className="notice error" role="alert"><span>{importError}</span></p> : null}

      <SectionHeading id="current-project">Current project</SectionHeading>
      <div className="project-basics" aria-labelledby="current-project">
        <label className="field">
          Project name
          <input
            value={project.name}
            onChange={(event) => updateProject(renameProject(project, event.target.value.trimStart() || 'Untitled configuration'))}
          />
        </label>
        <label className="field">
          Target schema
          <select
            value={project.target_schema_version}
            onChange={(event) => updateProject(setTargetSchema(project, event.target.value as SchemaVersion))}
          >
            <option value="1.1">1.1, nested units</option>
            <option value="1.0" disabled={!canUseSchema10}>1.0, flat legacy structure</option>
          </select>
        </label>
        <dl className="project-id">
          <dt className="caption">Project ID</dt>
          <dd><code>{project.id}</code></dd>
        </dl>
      </div>
      {!canUseSchema10 ? <p className="field-note">Schema 1.0 is available only while every service sits directly under the root.</p> : null}

      <SectionHeading id="start-from">Start something new</SectionHeading>
      <ul className="start-options" aria-labelledby="start-from">
        <li>
          <button className="start-option" type="button" onClick={() => void createNew('blank')}>
            <span className="start-option-mark" aria-hidden="true">A</span>
            <span className="start-option-text"><strong>Blank project</strong><small>One root unit and one editable service.</small></span>
            <ArrowRight size={18} strokeWidth={1.75} aria-hidden="true" />
          </button>
        </li>
        <li>
          <button className="start-option" type="button" onClick={() => void createNew('example')}>
            <span className="start-option-mark" aria-hidden="true">B</span>
            <span className="start-option-text"><strong>University template</strong><small>A complete, fictional service design that exercises every Queuewright policy family.</small></span>
            <ArrowRight size={18} strokeWidth={1.75} aria-hidden="true" />
          </button>
        </li>
        <li><ImportControl /></li>
      </ul>

      <SectionHeading id="library" aside={<span className="caption section-count">{projects.length}</span>}>In this browser</SectionHeading>
      {projects.length ? (
        <ul className="project-library" aria-labelledby="library">
          {projects.map((item) => {
            const current = item.id === project.id
            return (
              <li key={item.id}>
                <button
                  type="button"
                  className="project-row"
                  aria-current={current ? 'true' : undefined}
                  onClick={() => void openProject(item.id)}
                >
                  <strong>{item.name}</strong>
                  <span className="project-row-meta">Schema {item.target_schema_version} · <code>{item.id}</code></span>
                  <span className={current ? 'tag is-solid' : 'project-row-open'}>{current ? 'Open now' : 'Open'}</span>
                </button>
              </li>
            )
          })}
        </ul>
      ) : (
        <EmptyState title="No saved projects yet">
          {demoMode ? 'The static demo does not save projects.' : 'Projects appear here once they have been saved in this browser.'}
        </EmptyState>
      )}
    </section>
  )
}
