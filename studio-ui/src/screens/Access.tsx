import { displayGroupName, permissionFor, setPermission } from '../project-model'
import { useStudio } from '../studio-state'
import { PageHeader } from '../ui'
import type { CSSProperties } from 'react'
import type { GroupResource, Permission } from '../types'

export function Access() {
  const { project, updateProject } = useStudio()
  const leaves = project.manifest.groups.filter((group) => group.kind === 'leaf')
  const options: Permission[] = ['none', 'read', 'create', 'work']
  return (
    <section className="access-screen">
      <PageHeader
        title="Design access by service"
        description="Organizations, synthetic populations, and roles remain explicit and scoped to managed services."
      />
      <div className="three-columns">
        <div>
          <h2>Organizations</h2>
          {project.manifest.organizations.map((item) => (
            <p className="list-row" key={item.key}>
              {displayGroupName(project, { ...item, kind: 'container' } as GroupResource)}
              <small>{item.class}</small>
            </p>
          ))}
        </div>
        <div>
          <h2>Populations</h2>
          {[...new Set(project.manifest.organizations.map((item) => item.class))].map((item) => (
            <p className="list-row" key={item}>{item.replaceAll('_', ' ')}</p>
          ))}
        </div>
        <div>
          <h2>Roles</h2>
          {project.manifest.roles.map((item) => (
            <p className="list-row" key={item.key}>
              {item.name.replace(/^.*?Role · /, '')}
              <small>Managed role</small>
            </p>
          ))}
        </div>
      </div>
      <h2>ACL matrix</h2>
      <div className="matrix-scroll">
        <div className="matrix" style={{ '--service-count': leaves.length } as CSSProperties}>
          <div className="matrix-corner">Role / service</div>
          {leaves.map((leaf) => <b key={leaf.key}>{displayGroupName(project, leaf)}</b>)}
          {project.manifest.roles.map((role) => (
            <div className="matrix-row" key={role.key}>
              <b>{role.name.replace(/^.*?Role · /, '')}</b>
              {leaves.map((leaf) => (
                <select
                  aria-label={`${role.name} ${leaf.name}`}
                  value={permissionFor(role, leaf.key)}
                  onChange={(event) => updateProject(setPermission(project, role.key, leaf.key, event.target.value as Permission))}
                  key={leaf.key}
                >
                  {options.map((option) => <option value={option} key={option}>{option}</option>)}
                </select>
              ))}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
