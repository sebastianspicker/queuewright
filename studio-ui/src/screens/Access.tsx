import { displayGroupName, permissionFor, setPermission } from '../editor/model'
import { useStudioProject } from '../editor/context'
import { PageHeader } from '../components/ui'
import { memo, useCallback, useMemo, type CSSProperties } from 'react'
import type { GroupResource, Permission, RoleResource } from '../contracts'

const options: Permission[] = ['none', 'read', 'create', 'work']
type PermissionChange = (role: string, group: string, permission: Permission) => void
const PermissionCell = memo(function PermissionCell({ roleKey, roleName, leaf, permission, onChange }: {
  roleKey: string; roleName: string; leaf: GroupResource; permission: Permission; onChange: PermissionChange
}) {
  return <select aria-label={`${roleName} ${leaf.name}`} value={permission}
    onChange={(event) => onChange(roleKey, leaf.key, event.target.value as Permission)}>
    {options.map((option) => <option value={option} key={option}>{option}</option>)}
  </select>
})
const AccessRow = memo(function AccessRow({ role, leaves, onChange }: {
  role: RoleResource; leaves: GroupResource[]; onChange: PermissionChange
}) {
  return <div className="matrix-row"><b>{role.name.replace(/^.*?Role · /, '')}</b>
    {leaves.map((leaf) => <PermissionCell key={leaf.key} roleKey={role.key} roleName={role.name}
      leaf={leaf} permission={permissionFor(role, leaf.key)} onChange={onChange} />)}
  </div>
})

export function Access() {
  const { project, editProject } = useStudioProject()
  const { bundle } = project
  const leaves = useMemo(() => bundle.manifest.groups.filter((group) => group.kind === 'leaf'), [bundle.manifest.groups])
  const onPermission = useCallback<PermissionChange>((role, group, permission) => { editProject((current) => setPermission(current, role, group, permission)) }, [editProject])
  return (
    <section className="access-screen">
      <PageHeader
        title="Design access by service"
        description="Organizations, synthetic populations, and roles remain explicit and scoped to managed services."
      />
      <div className="three-columns">
        <div>
          <h2>Organizations</h2>
          {bundle.manifest.organizations.map((item) => (
            <p className="list-row" key={item.key}>
              {displayGroupName(bundle, { ...item, kind: 'container' } as GroupResource)}
              <small>{item.class}</small>
            </p>
          ))}
        </div>
        <div>
          <h2>Populations</h2>
          {[...new Set(bundle.manifest.organizations.map((item) => item.class))].map((item) => (
            <p className="list-row" key={item}>{item.replaceAll('_', ' ')}</p>
          ))}
        </div>
        <div>
          <h2>Roles</h2>
          {bundle.manifest.roles.map((item) => (
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
          {leaves.map((leaf) => <b key={leaf.key}>{displayGroupName(bundle, leaf)}</b>)}
          {bundle.manifest.roles.map((role) => <AccessRow role={role} leaves={leaves} onChange={onPermission} key={role.key} />)}
        </div>
      </div>
    </section>
  )
}
