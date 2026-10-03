import { X } from 'lucide-react'
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
} from '../editor/model'
import { useStudio } from '../editor/context'
import type { GroupResource, StudioBundle, StudioProjectV2 } from '../contracts'

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
  targetSchemaVersion,
}: {
  group: GroupResource
  groupName: string
  isRoot: boolean
  onNameChange: Dispatch<string>
  onParentChange: Dispatch<string>
  onTypeChange: Dispatch<'container' | 'leaf'>
  parents: GroupResource[]
  project: StudioBundle
  targetSchemaVersion: StudioProjectV2['target_schema_version']
}) {
  return (
    <fieldset className="inspector-section">
      <legend className="caption">Definition</legend>
      <label className="field">
        Name
        <input value={groupName} onChange={(event) => { onNameChange(event.target.value) }} />
      </label>
      <label className="field">
        Type
        <select
          value={group.kind}
          disabled={isRoot || targetSchemaVersion === '1.0'}
          onChange={(event) => { onTypeChange(event.target.value as 'container' | 'leaf') }}
        >
          <option value="container">Unit (organizes the tree)</option>
          <option value="leaf">Service (carries tickets)</option>
        </select>
      </label>
      <label className="field">
        Parent unit
        <select value={group.parent ?? ''} disabled={isRoot} onChange={(event) => { onParentChange(event.target.value) }}>
          {isRoot ? <option value="">None (root)</option> : null}
          {parents.map((parent) => <option value={parent.key} key={parent.key}>{displayGroupName(project, parent)}</option>)}
        </select>
      </label>
    </fieldset>
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
      <fieldset className="inspector-section">
        <legend className="caption">Posture</legend>
        <div className="switch-row">
          <span><strong>Sensitive area</strong><small>Restricted details stay out of handoffs.</small></span>
          <Switch checked={group.restricted === true} onChange={onRestrictedChange} label="Sensitive area" />
        </div>
        <div className="switch-row">
          <span><strong>Customer entry point</strong><small>Offered to customers when they open a ticket.</small></span>
          <Switch checked={entryPoints.includes(group.key)} onChange={onEntryPointChange} label="Customer entry point" />
        </div>
      </fieldset>
      <section className="inspector-section" aria-labelledby="generated-access">
        <h3 className="caption" id="generated-access">Generated access</h3>
        <dl className="generated">
          <div><dt>Service role</dt><dd><code>{group.key}</code></dd></div>
          <div><dt>Handoff role</dt><dd><code>{group.key}-handoff</code></dd></div>
        </dl>
      </section>
    </>
  )
}

export function StructureInspector({ Switch }: { Switch: SwitchControl }) {
  const studio = useStudio()
  const { project, selectedGroup, selectGroup } = studio
  const { bundle } = project
  const group = bundle.manifest.groups.find((item) => item.key === selectedGroup)
  if (!group) return <p className="inspector-empty">Select a unit or service in the tree to edit it.</p>
  const isRoot = group.parent === undefined
  const parents = bundle.manifest.groups.filter((candidate) => candidate.kind === 'container' && candidate.key !== group.key && !isDescendant(bundle, candidate.key, group.key))
  const parent = bundle.manifest.groups.find((item) => item.key === group.parent) ?? group
  const groupName = displayGroupName(bundle, group)
  const typeLabel = group.kind === 'leaf' ? 'Service' : isRoot ? 'Root unit' : 'Unit'
  const close = () => { selectGroup(undefined) }
  const remove = () => { studio.updateProject(removeGroup(project, group.key)); close() }
  return (
    <>
      <div className="inspector-title">
        <div>
          <p className="caption">{typeLabel}{group.parent ? ` · in ${displayGroupName(bundle, parent)}` : ''}</p>
          <h2>{groupName || 'Unnamed'}</h2>
        </div>
        <button className="icon-button" type="button" aria-label="Close inspector" onClick={close}><X size={18} strokeWidth={1.75} /></button>
      </div>
      <GroupDefinition
        group={group}
        groupName={groupName}
        isRoot={isRoot}
        onNameChange={(name) => { studio.updateProject(renameGroup(project, group.key, name), group.key) }}
        onParentChange={(parentKey) => { studio.updateProject(moveGroup(project, group.key, parentKey), group.key) }}
        onTypeChange={(kind) => { studio.updateProject(setGroupKind(project, group.key, kind), group.key) }}
        parents={parents}
        project={bundle}
        targetSchemaVersion={project.target_schema_version}
      />
      {group.kind === 'leaf' ? <LeafDetails entryPoints={customerEntryPoints(bundle)} group={group} onEntryPointChange={(checked) => { studio.updateProject(setCustomerEntryPoint(project, group.key, checked), group.key) }} onRestrictedChange={(checked) => { studio.updateProject(setRestricted(project, group.key, checked), group.key) }} Switch={Switch} /> : null}
      <div className="inspector-actions">
        <button className="button primary" type="button" onClick={() => { studio.validateNow() }}>Validate changes</button>
        {!isRoot ? <button className="text-button danger" type="button" onClick={remove}>Remove {group.kind === 'leaf' ? 'service' : 'unit'}</button> : null}
      </div>
    </>
  )
}
