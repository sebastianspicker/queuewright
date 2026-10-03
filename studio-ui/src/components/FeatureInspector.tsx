import { X } from 'lucide-react'
import type { ComponentType, Dispatch } from 'react'
import { HANDOFF_MODES, setHandoffModes, toggleFeature } from '../editor/model'
import { useStudio } from '../editor/context'

type SwitchControl = ComponentType<{
  checked: boolean
  disabled?: boolean
  label: string
  onChange: Dispatch<boolean>
}>

const handoffDependencies = [
  ['Field', 'Handoff type'],
  ['Tags', '2 managed tags'],
  ['Macro', 'Prepare handoff'],
  ['Trigger', 'Record handoff'],
] as const

function HandoffDetails({
  enabled,
  selectedModes,
  setMode,
}: {
  enabled: boolean
  selectedModes: Set<string>
  setMode: Dispatch<[string, boolean]>
}) {
  return (
    <>
      <fieldset className="inspector-section">
        <legend className="caption">Handoff modes</legend>
        {HANDOFF_MODES.map((mode) => (
          <label className="check-row" key={mode}>
            <input className="check" type="checkbox" checked={selectedModes.has(mode)} disabled={!enabled || (selectedModes.size === 1 && selectedModes.has(mode))} onChange={(event) => { setMode([mode, event.target.checked]) }} />
            <span>{mode.replaceAll('_', ' ')}</span>
          </label>
        ))}
        {enabled ? <p className="inspector-hint">At least one mode stays selected.</p> : <p className="inspector-hint">Enable the capability to choose modes.</p>}
      </fieldset>
      <section className="inspector-section" aria-labelledby="handoff-dependencies">
        <h3 className="caption" id="handoff-dependencies">Adds to the bundle</h3>
        <dl className="generated">
          {handoffDependencies.map(([kind, name]) => <div key={kind}><dt>{kind}</dt><dd>{name}</dd></div>)}
        </dl>
      </section>
    </>
  )
}

function SafetyAssurances({ assurances }: { assurances: string[] }) {
  if (!assurances.length) return null
  return (
    <section className="inspector-section" aria-labelledby="safety-assurances">
      <h3 className="caption" id="safety-assurances">Always holds</h3>
      <ul className="assurances">
        {assurances.map((assurance) => {
          const text = assurance.replaceAll('_', ' ')
          return <li key={assurance}>{text.charAt(0).toUpperCase() + text.slice(1)}</li>
        })}
      </ul>
    </section>
  )
}

export function FeatureInspector({ Switch }: { Switch: SwitchControl }) {
  const studio = useStudio()
  const { project, catalog, selectedFeature, selectFeature } = studio
  const { bundle } = project
  const feature = catalog.find((item) => item.id === selectedFeature)
  if (!feature) return <p className="inspector-empty">Select a capability to see what it adds.</p>
  const enabled = bundle.feature_state[feature.id].enabled
  const modes = bundle.feature_state.cross_department_handoff.settings.modes
  const selectedModes = new Set(Array.isArray(modes) ? modes.filter((mode): mode is string => typeof mode === 'string') : [])
  const close = () => { selectFeature(undefined) }
  const setMode = ([mode, checked]: [string, boolean]) => {
    const next = new Set(selectedModes)
    if (checked) next.add(mode)
    else next.delete(mode)
    studio.updateProject(setHandoffModes(project, [...next]))
  }
  return (
    <>
      <div className="inspector-title">
        <div>
          <p className="caption">{feature.category}</p>
          <h2>{feature.name}</h2>
        </div>
        <button className="icon-button" type="button" aria-label="Close inspector" onClick={close}><X size={18} strokeWidth={1.75} /></button>
      </div>
      <p className="inspector-copy">{feature.id === 'cross_department_handoff' ? 'Prepare, record, and review transfers between managed services without exposing restricted source details.' : feature.description}</p>
      <div className="switch-row is-primary">
        <span><strong>Enabled</strong>{feature.locked ? <small>Part of the safe baseline; cannot be switched off.</small> : null}</span>
        <Switch checked={enabled} disabled={feature.locked} onChange={(checked) => { studio.updateProject(toggleFeature(project, feature.id, checked, catalog)) }} label={`Enable ${feature.name}`} />
      </div>
      {feature.id === 'cross_department_handoff' ? <HandoffDetails enabled={enabled} selectedModes={selectedModes} setMode={setMode} /> : <SafetyAssurances assurances={feature.lockedAssurances} />}
      <details className="settings-source">
        <summary>Settings as JSON</summary>
        <pre>{JSON.stringify(bundle.feature_state[feature.id].settings, null, 2)}</pre>
      </details>
      <div className="inspector-actions">
        <button className="button primary" type="button" onClick={() => { studio.validateNow() }}>Validate settings</button>
      </div>
    </>
  )
}
