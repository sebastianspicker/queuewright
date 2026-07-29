import { Copy, Network, Users, X } from 'lucide-react'
import type { ComponentType, Dispatch } from 'react'
import {
  customerEntryPoints,
  displayGroupName,
  isDescendant,
  moveGroup,
  removeGroup,
  renameGroup,
  setCustomerEntryPoint,
  setGroupKind,
  setRestricted,
} from '../project-model'
import { useStudio } from '../studio-state'
import type { GroupResource, StudioProject } from '../types'

type SwitchControl = ComponentType<{
  checked: boolean
  disabled?: boolean
  label: string
  onChange: Dispatch<boolean>
}>

function GroupDefinition({
  group,
  groupName,
  isRoot,
  onNameChange,
  onParentChange,
  onTypeChange,
  parents,
  project,
}: {
  group: GroupResource
  groupName: string
  isRoot: boolean
  onNameChange: Dispatch<string>
  onParentChange: Dispatch<string>
  onTypeChange: Dispatch<'container' | 'leaf'>
  parents: GroupResource[]
  project: StudioProject
}) {
  return (
    <div className="section">
      <p className="section-label">Definition</p>
      <label className="field">
        Name
        <input value={groupName} onChange={(event) => { onNameChange(event.target.value) }} />
      </label>
      <label className="field">
        Unit type
        <select
          value={group.kind}
          disabled={isRoot || project.target_schema_version === '1.0'}
          onChange={(event) => { onTypeChange(event.target.value as 'container' | 'leaf') }}
        >
          <option value="container">Organizational unit</option>
          <option value="leaf">Ticket-bearing service</option>
        </select>
      </label>
      <label className="field">
        Parent unit
        <select value={group.parent ?? ''} disabled={isRoot} onChange={(event) => { onParentChange(event.target.value) }}>
          {isRoot ? <option value="">Root unit</option> : null}
          {parents.map((parent) => <option value={parent.key} key={parent.key}>{displayGroupName(project, parent)}</option>)}
        </select>
      </label>
    </div>
  )
}

function LeafDetails({
  entryPoints,
  group,
  onEntryPointChange,
  onRestrictedChange,
  Switch,
}: {
  entryPoints: string[]
  group: GroupResource
  onEntryPointChange: Dispatch<boolean>
  onRestrictedChange: Dispatch<boolean>
  Switch: SwitchControl
}) {
  return (
    <>
      <div className="section">
        <p className="section-label">Operating posture</p>
        <div className="switch-row"><span>Sensitive area</span><Switch checked={group.restricted === true} onChange={onRestrictedChange} label="Sensitive area" /></div>
        <div className="switch-row"><span>Customer entry point</span><Switch checked={entryPoints.includes(group.key)} onChange={onEntryPointChange} label="Customer entry point" /></div>
      </div>
      <div className="section">
        <p className="section-label">Generated access</p>
        <label className="generated-field">Service role<span><Users size={18} aria-hidden="true" /><code>{group.key}</code><Copy size={17} aria-hidden="true" /></span></label>
        <label className="generated-field">Cross-department handoff<span><Network size={18} aria-hidden="true" /><code>{group.key}-handoff</code><Copy size={17} aria-hidden="true" /></span></label>
      </div>
    </>
  )
}

export function StructureInspector({ Switch }: { Switch: SwitchControl }) {
  const studio = useStudio()
  const { project, selectedGroup, dispatch } = studio
  const group = project.manifest.groups.find((item) => item.key === selectedGroup)
  if (!group) return <p className="inspector-empty">Select a unit or service to edit it.</p>
  const isRoot = group.parent === undefined
  const parents = project.manifest.groups.filter((candidate) => candidate.kind === 'container' && candidate.key !== group.key && !isDescendant(project, candidate.key, group.key))
  const parent = project.manifest.groups.find((item) => item.key === group.parent) ?? group
  const groupName = displayGroupName(project, group)
  const typeLabel = group.kind === 'leaf' ? 'Ticket-bearing service' : 'Organizational unit'
  const close = () => { dispatch({ type: 'group:select', id: undefined }) }
  const remove = () => { studio.updateProject(removeGroup(project, group.key)); close() }
  return (
    <>
      <div className="inspector-title"><div><h2>{groupName}</h2><p className="inspector-subtitle">{typeLabel} · under {group.parent ? displayGroupName(project, parent) : 'Root'}</p></div><button className="icon-button" type="button" aria-label="Close inspector" onClick={close}><X size={22} /></button></div>
      <GroupDefinition
        group={group}
        groupName={groupName}
        isRoot={isRoot}
        onNameChange={(name) => { studio.updateProject(renameGroup(project, group.key, name), group.key) }}
        onParentChange={(parentKey) => { studio.updateProject(moveGroup(project, group.key, parentKey), group.key) }}
        onTypeChange={(kind) => { studio.updateProject(setGroupKind(project, group.key, kind), group.key) }}
        parents={parents}
        project={project}
      />
      {group.kind === 'leaf' ? <LeafDetails entryPoints={customerEntryPoints(project)} group={group} onEntryPointChange={(checked) => { studio.updateProject(setCustomerEntryPoint(project, group.key, checked), group.key) }} onRestrictedChange={(checked) => { studio.updateProject(setRestricted(project, group.key, checked), group.key) }} Switch={Switch} /> : null}
      <button className="button primary inspector-save" type="button" onClick={() => { studio.validateNow() }}>Validate changes</button>
      {!isRoot ? <button className="text-button danger" type="button" onClick={remove}>Remove from structure</button> : null}
    </>
  )
}
