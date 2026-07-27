import {
  ChevronRight,
  Code2,
  Copy,
  Network,
  ShieldCheck,
  Tag,
  Users,
  X,
  Zap,
} from 'lucide-react'
import {
  displayGroupName,
  HANDOFF_MODES,
  isDescendant,
  moveGroup,
  removeGroup,
  renameGroup,
  setCustomerEntryPoint,
  setGroupKind,
  setHandoffModes,
  setRestricted,
  toggleFeature,
  customerEntryPoints,
} from '../project-model'
import { steps } from '../data'
import { useStudio } from '../studio-state'

function Switch({
  checked,
  disabled = false,
  onChange,
  label,
}: {
  checked: boolean
  disabled?: boolean
  onChange(checked: boolean): void
  label: string
}) {
  return (
    <button
      className={checked ? 'switch on' : 'switch'}
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
    >
      <span />
    </button>
  )
}

function StructureInspector() {
  const { project, selectedGroup, dispatch, updateProject, validateNow } = useStudio()
  const group = project.manifest.groups.find((item) => item.key === selectedGroup)
  if (!group) return <p className="inspector-empty">Select a unit or service to edit it.</p>
  const name = displayGroupName(project, group)
  const isRoot = group.parent === undefined
  const entryPoints = customerEntryPoints(project)
  const parents = project.manifest.groups.filter((candidate) =>
    candidate.kind === 'container'
    && candidate.key !== group.key
    && !isDescendant(project, candidate.key, group.key),
  )
  const parentName = group.parent
    ? displayGroupName(
      project,
      project.manifest.groups.find((item) => item.key === group.parent) ?? group,
    )
    : 'Root'
  const typeLabel = group.kind === 'leaf'
    ? 'Ticket-bearing service'
    : 'Organizational unit'
  return (
    <>
      <div className="inspector-title">
        <div>
          <h2>{name}</h2>
          <p className="inspector-subtitle">{typeLabel} · under {parentName}</p>
        </div>
        <button
          className="icon-button"
          type="button"
          aria-label="Close inspector"
          onClick={() => dispatch({ type: 'group:select', id: undefined })}
        >
          <X size={22} />
        </button>
      </div>

      <div className="section">
        <p className="section-label">Definition</p>
        <label className="field">
          Name
          <input
            value={name}
            onChange={(event) => updateProject(renameGroup(project, group.key, event.target.value), group.key)}
          />
        </label>
        <label className="field">
          Unit type
          <select
            value={group.kind}
            disabled={isRoot || project.target_schema_version === '1.0'}
            onChange={(event) => updateProject(
              setGroupKind(project, group.key, event.target.value as 'container' | 'leaf'),
              group.key,
            )}
          >
            <option value="container">Organizational unit</option>
            <option value="leaf">Ticket-bearing service</option>
          </select>
        </label>
        <label className="field">
          Parent unit
          <select
            value={group.parent ?? ''}
            disabled={isRoot}
            onChange={(event) => updateProject(moveGroup(project, group.key, event.target.value), group.key)}
          >
            {isRoot ? <option value="">Root unit</option> : null}
            {parents.map((parent) => (
              <option value={parent.key} key={parent.key}>
                {displayGroupName(project, parent)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {group.kind === 'leaf' ? (
        <>
          <div className="section">
            <p className="section-label">Operating posture</p>
            <div className="switch-row">
              <span>Sensitive area</span>
              <Switch
                checked={group.restricted === true}
                onChange={(checked) => updateProject(setRestricted(project, group.key, checked), group.key)}
                label="Sensitive area"
              />
            </div>
            <div className="switch-row">
              <span>Customer entry point</span>
              <Switch
                checked={entryPoints.includes(group.key)}
                onChange={(checked) => updateProject(setCustomerEntryPoint(project, group.key, checked), group.key)}
                label="Customer entry point"
              />
            </div>
          </div>

          <div className="section">
            <p className="section-label">Generated access</p>
            <label className="generated-field">
              Service role
              <span>
                <Users size={18} aria-hidden="true" />
                <code>{group.key}</code>
                <Copy size={17} aria-hidden="true" />
              </span>
            </label>
            <label className="generated-field">
              Cross-department handoff
              <span>
                <Network size={18} aria-hidden="true" />
                <code>{group.key}-handoff</code>
                <Copy size={17} aria-hidden="true" />
              </span>
            </label>
          </div>
        </>
      ) : null}

      <button className="button primary inspector-save" type="button" onClick={validateNow}>
        Validate changes
      </button>
      {!isRoot ? (
        <button
          className="text-button danger"
          type="button"
          onClick={() => {
            updateProject(removeGroup(project, group.key))
            dispatch({ type: 'group:select', id: undefined })
          }}
        >
          Remove from structure
        </button>
      ) : null}
    </>
  )
}

function FeatureInspector() {
  const { project, catalog, selectedFeature, dispatch, updateProject, validateNow } = useStudio()
  const feature = catalog.find((item) => item.id === selectedFeature)
  if (!feature) return <p className="inspector-empty">Select a capability to inspect it.</p>
  const enabled = project.feature_state[feature.id].enabled
  const modes = project.feature_state.cross_department_handoff.settings.modes
  const selectedModes = new Set(
    Array.isArray(modes)
      ? modes.filter((mode): mode is string => typeof mode === 'string')
      : [],
  )
  const setMode = (mode: string, checked: boolean) => {
    const next = new Set(selectedModes)
    if (checked) next.add(mode)
    else next.delete(mode)
    updateProject(setHandoffModes(project, [...next]))
  }
  return (
    <>
      <div className="inspector-title">
        <h2>{feature.name}</h2>
        <button
          className="icon-button"
          type="button"
          aria-label="Close inspector"
          onClick={() => dispatch({ type: 'feature:select', id: undefined })}
        >
          <X size={22} />
        </button>
      </div>
      <p className="inspector-copy">
        {feature.id === 'cross_department_handoff'
          ? 'Prepare, record, and review transfers between managed services without exposing restricted source details.'
          : feature.description}
      </p>
      <div className="switch-row strong">
        <span>Enable feature</span>
        <Switch
          checked={enabled}
          disabled={feature.locked}
          onChange={(checked) => updateProject(toggleFeature(project, feature.id, checked, catalog))}
          label={`Enable ${feature.name}`}
        />
      </div>
      {feature.id === 'cross_department_handoff' ? (
        <>
          <div className="inspector-divider" />
          <h3>Handoff behavior</h3>
          {HANDOFF_MODES.map((mode) => (
            <label className="behavior-check" key={mode}>
              <input
                type="checkbox"
                checked={selectedModes.has(mode)}
                disabled={!enabled || (selectedModes.size === 1 && selectedModes.has(mode))}
                onChange={(event) => setMode(mode, event.target.checked)}
              />
              <span>{mode.replaceAll('_', ' ')}</span>
            </label>
          ))}
          <div className="inspector-divider" />
          <h3>Dependencies added</h3>
          <p className="dependency"><Tag size={18} /> Handoff type field</p>
          <p className="dependency"><Tag size={18} /> 2 managed tags</p>
          <p className="dependency"><Code2 size={19} /> Prepare handoff macro</p>
          <p className="dependency"><Zap size={19} /> Record handoff trigger</p>
        </>
      ) : (
        <>
          <div className="inspector-divider" />
          <h3>Safety assurances</h3>
          {feature.lockedAssurances.map((assurance) => (
            <p className="dependency" key={assurance}>
              <ShieldCheck size={18} /> {assurance.replaceAll('_', ' ')}
            </p>
          ))}
        </>
      )}
      <details className="advanced-settings">
        <summary>Advanced settings <ChevronRight size={18} /></summary>
        <pre>{JSON.stringify(project.feature_state[feature.id].settings, null, 2)}</pre>
      </details>
      <button className="button primary inspector-save" type="button" onClick={validateNow}>
        Validate feature settings
      </button>
    </>
  )
}

export function Inspector() {
  const { step } = useStudio()
  return (
    <aside className="inspector" aria-label="Inspector">
      {step === 'structure' ? (
        <StructureInspector />
      ) : step === 'features' ? (
        <FeatureInspector />
      ) : (
        <div className="context-summary">
          <h2>{steps.find(([id]) => id === step)?.[1]}</h2>
          <p>
            Review this step in the main workspace. Changes stay local until authoritative validation succeeds.
          </p>
        </div>
      )}
    </aside>
  )
}
