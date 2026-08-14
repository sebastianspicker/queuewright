import {
  Box,
  Check,
  CheckCircle2,
  ClipboardCheck,
  Database,
  Landmark,
  LockKeyhole,
  Network,
  PlayCircle,
  Scale,
  type LucideIcon,
} from 'lucide-react'
import { steps } from '../data'
import { useStudio } from '../studio-state'
import type { StepId } from '../types'

const stepIcons: Record<StepId, LucideIcon> = {
  start: PlayCircle,
  organization: Landmark,
  structure: Network,
  access: LockKeyhole,
  features: Box,
  governance: Scale,
  'test-data': Database,
  review: ClipboardCheck,
}

const workflowPhases: Array<{
  label: string
  steps: StepId[]
}> = [
  { label: 'Frame', steps: ['start', 'organization'] },
  { label: 'Design', steps: ['structure', 'access', 'features'] },
  { label: 'Assure', steps: ['governance', 'test-data', 'review'] },
]

export function StepRail() {
  const { step, dispatch, hydrated, storageStatus, demoMode } = useStudio()
  const currentIndex = steps.findIndex(([id]) => id === step)
  const storageLabel = demoMode
    ? 'Fixture data · changes reset'
    : !hydrated || storageStatus === 'loading'
    ? 'Loading browser projects…'
    : storageStatus === 'saving' || storageStatus === 'pending'
      ? 'Saving in this browser…'
      : storageStatus === 'error'
        ? 'Browser save failed'
        : 'Saved in this browser'
  return (
    <nav className="step-rail" aria-label="qWright steps">
      <div className="step-list">
        {workflowPhases.map((phase) => (
          <div className="step-phase" key={phase.label}>
            <p>{phase.label}</p>
            {phase.steps.map((id) => {
              const itemIndex = steps.findIndex(([candidate]) => candidate === id)
              const label = steps.at(itemIndex)?.[1] ?? id
              const Icon = Object.entries(stepIcons).find(([key]) => key === id)?.[1] ?? PlayCircle
              const isActive = step === id
              const isDone = itemIndex < currentIndex
              const className = [
                'step',
                isActive ? 'active current' : '',
                isDone ? 'done' : '',
              ].filter(Boolean).join(' ')
              return (
                <button
                  type="button"
                  className={className}
                  onClick={() => dispatch({ type: 'step', step: id })}
                  aria-current={isActive ? 'step' : undefined}
                  key={id}
                >
                  <span className="step-marker" aria-hidden="true">
                    {isDone && !isActive ? (
                      <Check className="step-check" size={15} strokeWidth={2.4} />
                    ) : (
                      <>
                        <span className="step-index">{String(itemIndex + 1).padStart(2, '0')}</span>
                        <Icon className="step-icon" size={17} strokeWidth={1.8} />
                      </>
                    )}
                  </span>
                  <span className="step-label">{label}</span>
                </button>
              )
            })}
          </div>
        ))}
      </div>
      <div className="browser-save">
        <CheckCircle2 size={20} />
        <span>{storageLabel}</span>
      </div>
    </nav>
  )
}
