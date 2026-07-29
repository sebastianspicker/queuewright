import { steps } from '../data'
import { useStudio } from '../studio-state'
import { FeatureInspector } from './FeatureInspector'
import { StructureInspector } from './StructureInspector'

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

function ContextSummary() {
  const { step } = useStudio()
  return (
    <div className="context-summary">
      <h2>{steps.find(([id]) => id === step)?.[1]}</h2>
      <p>Review this step in the main workspace. Changes stay local until authoritative validation succeeds.</p>
    </div>
  )
}

export function Inspector() {
  const { step } = useStudio()
  return (
    <aside className="inspector" aria-label="Inspector">
      {step === 'structure' ? <StructureInspector Switch={Switch} /> : null}
      {step === 'features' ? <FeatureInspector Switch={Switch} /> : null}
      {step !== 'structure' && step !== 'features' ? <ContextSummary /> : null}
    </aside>
  )
}
