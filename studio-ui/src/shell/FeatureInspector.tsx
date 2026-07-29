import { ChevronRight, Code2, ShieldCheck, Tag, X, Zap } from 'lucide-react'
import type { ComponentType } from 'react'
import { HANDOFF_MODES, setHandoffModes, toggleFeature } from '../project-model'
import { useStudio } from '../studio-state'

type ChangeHandler<Arguments extends unknown[]> = (...args: Arguments) => void

type SwitchControl = ComponentType<{
  checked: boolean
  disabled?: boolean
  label: string
  onChange: ChangeHandler<[boolean]>
}>

function HandoffDetails({
  enabled,
  selectedModes,
  setMode,
}: {
  enabled: boolean
  selectedModes: Set<string>
  setMode: ChangeHandler<[string, boolean]>
}) {
  return (
    <>
      <div className="inspector-divider" />
      <h3>Handoff behavior</h3>
      {HANDOFF_MODES.map((mode) => (
        <label className="behavior-check" key={mode}>
          <input type="checkbox" checked={selectedModes.has(mode)} disabled={!enabled || (selectedModes.size === 1 && selectedModes.has(mode))} onChange={(event) => { setMode(mode, event.target.checked) }} />
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
  )
}

function SafetyAssurances({ assurances }: { assurances: string[] }) {
  return (
    <>
      <div className="inspector-divider" />
      <h3>Safety assurances</h3>
      {assurances.map((assurance) => <p className="dependency" key={assurance}><ShieldCheck size={18} /> {assurance.replaceAll('_', ' ')}</p>)}
    </>
  )
}

export function FeatureInspector({ Switch }: { Switch: SwitchControl }) {
  const { project, catalog, selectedFeature, dispatch, updateProject, validateNow } = useStudio()
  const feature = catalog.find((item) => item.id === selectedFeature)
  if (!feature) return <p className="inspector-empty">Select a capability to inspect it.</p>
  const enabled = project.feature_state[feature.id].enabled
  const modes = project.feature_state.cross_department_handoff.settings.modes
  const selectedModes = new Set(Array.isArray(modes) ? modes.filter((mode): mode is string => typeof mode === 'string') : [])
  const close = () => { dispatch({ type: 'feature:select', id: undefined }) }
  const setMode = (mode: string, checked: boolean) => {
    const next = new Set(selectedModes)
    if (checked) next.add(mode)
    else next.delete(mode)
    updateProject(setHandoffModes(project, [...next]))
  }
  return (
    <>
      <div className="inspector-title"><h2>{feature.name}</h2><button className="icon-button" type="button" aria-label="Close inspector" onClick={close}><X size={22} /></button></div>
      <p className="inspector-copy">{feature.id === 'cross_department_handoff' ? 'Prepare, record, and review transfers between managed services without exposing restricted source details.' : feature.description}</p>
      <div className="switch-row strong"><span>Enable feature</span><Switch checked={enabled} disabled={feature.locked} onChange={(checked) => { updateProject(toggleFeature(project, feature.id, checked, catalog)) }} label={`Enable ${feature.name}`} /></div>
      {feature.id === 'cross_department_handoff' ? <HandoffDetails enabled={enabled} selectedModes={selectedModes} setMode={setMode} /> : <SafetyAssurances assurances={feature.lockedAssurances} />}
      <details className="advanced-settings"><summary>Advanced settings <ChevronRight size={18} /></summary><pre>{JSON.stringify(project.feature_state[feature.id].settings, null, 2)}</pre></details>
      <button className="button primary inspector-save" type="button" onClick={validateNow}>Validate feature settings</button>
    </>
  )
}
