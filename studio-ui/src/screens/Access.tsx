import { displayGroupName, permissionFor, setPermission } from '../editor/model'
import { useStudioProject } from '../editor/context'
import { PageHeader, SectionHeading } from '../components/ui'
import { memo, useCallback, useMemo } from 'react'
import type { GroupResource, Permission, RoleResource } from '../contracts'

const options: Permission[] = ['none', 'read', 'create', 'work']
type PermissionChange = (role: string, group: string, permission: Permission) => void

function roleLabel(role: RoleResource): string {
  return role.name.replace(/^.*?Role · /, '')
}

const PermissionCell = memo(function PermissionCell({ roleKey, roleName, leaf, leafName, permission, onChange }: {
  roleKey: string; roleName: string; leaf: GroupResource; leafName: string; permission: Permission; onChange: PermissionChange
}) {
  return (
    <td data-level={permission}>
      <select
        className="acl-select"
        aria-label={`${roleName} on ${leafName}`}
        value={permission}
        onChange={(event) => onChange(roleKey, leaf.key, event.target.value as Permission)}
      >
        {options.map((option) => <option value={option} key={option}>{option}</option>)}
      </select>
    </td>
  )
})

const AccessRow = memo(function AccessRow({ role, leaves, names, onChange }: {
  role: RoleResource; leaves: GroupResource[]; names: Map<string, string>; onChange: PermissionChange
}) {
  const label = roleLabel(role)
  return (
    <tr>
      <th scope="row">{label}</th>
      {leaves.map((leaf) => <PermissionCell key={leaf.key} roleKey={role.key} roleName={label}
        leaf={leaf} leafName={names.get(leaf.key) ?? leaf.key} permission={permissionFor(role, leaf.key)} onChange={onChange} />)}
    </tr>
  )
})

export function Access() {
  const { project, editProject } = useStudioProject()
  const { bundle } = project
  const leaves = useMemo(() => bundle.manifest.groups.filter((group) => group.kind === 'leaf'), [bundle.manifest.groups])
  const names = useMemo(() => new Map(leaves.map((leaf) => [leaf.key, displayGroupName(bundle, leaf)])), [bundle, leaves])
  const onPermission = useCallback<PermissionChange>((role, group, permission) => { editProject((current) => setPermission(current, role, group, permission)) }, [editProject])
  const organizations = bundle.manifest.organizations
  const populations = [...new Set(organizations.map((item) => item.class))]
  return (
    <section className="access-screen">
      <PageHeader
        title="Access by service"
        description="Who may do what in each ticket-bearing service. Every grant is explicit and scoped to a managed service; nothing is inherited or shared by domain."
      />
      <SectionHeading id="acl-heading" aside={<span className="caption section-count">{bundle.manifest.roles.length} roles × {leaves.length} services</span>}>Access matrix</SectionHeading>
      {leaves.length && bundle.manifest.roles.length ? (
        <div className="matrix-scroll" role="region" aria-labelledby="acl-heading" tabIndex={0}>
          <table className="matrix">
            <thead>
              <tr>
                <th scope="col" className="matrix-corner"><span className="caption">Role</span><span className="caption">Service</span></th>
                {leaves.map((leaf) => <th scope="col" key={leaf.key}><span>{names.get(leaf.key)}</span></th>)}
              </tr>
            </thead>
            <tbody>
              {bundle.manifest.roles.map((role) => <AccessRow role={role} leaves={leaves} names={names} onChange={onPermission} key={role.key} />)}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="notice">The matrix appears once the project has at least one role and one service. Add services on sheet 03.</p>
      )}

      <div className="schedule">
        <section aria-labelledby="orgs-heading">
          <SectionHeading id="orgs-heading" aside={<span className="caption section-count">{organizations.length}</span>}>Organizations</SectionHeading>
          <ul className="schedule-list">
            {organizations.map((item) => (
              <li key={item.key}>
                <span>{displayGroupName(bundle, { ...item, kind: 'container' } as GroupResource).replace(/^Organization · /, '')}</span>
                <small>{item.class.replaceAll('_', ' ')}</small>
              </li>
            ))}
          </ul>
        </section>
        <section aria-labelledby="pop-heading">
          <SectionHeading id="pop-heading" aside={<span className="caption section-count">{populations.length}</span>}>Populations</SectionHeading>
          <ul className="schedule-list">
            {populations.map((item) => <li key={item}><span>{item.replaceAll('_', ' ')}</span></li>)}
          </ul>
        </section>
        <section aria-labelledby="roles-heading">
          <SectionHeading id="roles-heading" aside={<span className="caption section-count">{bundle.manifest.roles.length}</span>}>Roles</SectionHeading>
          <ul className="schedule-list">
            {bundle.manifest.roles.map((item) => <li key={item.key}><span>{roleLabel(item)}</span><small>managed</small></li>)}
          </ul>
        </section>
      </div>
    </section>
  )
}
