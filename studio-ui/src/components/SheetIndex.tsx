import { ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react'
import { useId, useRef } from 'react'
import type { StepId } from '../contracts'
import { useStudio } from '../editor/context'
import { phases, sheetCount, sheetFor, steps } from './steps'
import { isLocallyValid, openDecisionCount, plural } from './status'
import { Delta } from './ui'

function SheetMark({ id }: { id: StepId }) {
  const studio = useStudio()
  if (id === 'governance') {
    const open = openDecisionCount(studio.project)
    return open ? <Delta count={open} accessibleLabel={plural(open, 'open decision')} /> : null
  }
  if (id === 'review' && !studio.demoMode && isLocallyValid(studio)) {
    return <span className="sheet-valid">Valid</span>
  }
  return null
}

function SheetList({ onPick }: { onPick?: () => void }) {
  const { step, goToStep } = useStudio()
  const prefix = useId()
  return (
    <>
      {phases.map((phase) => (
        <div className="sheet-phase" key={phase.label}>
          <p className="caption" id={`${prefix}-${phase.label}`}>{phase.label}</p>
          <ol aria-labelledby={`${prefix}-${phase.label}`}>
            {phase.steps.map((id) => {
              const sheet = sheetFor(id)
              return (
                <li key={id}>
                  <button
                    type="button"
                    className="sheet-link"
                    aria-current={step === id ? 'step' : undefined}
                    onClick={() => { goToStep(id); onPick?.() }}
                  >
                    <span className="sheet-number numeral" aria-hidden="true">{sheet.number}</span>
                    <span className="sheet-name">{sheet.label}</span>
                    <SheetMark id={id} />
                  </button>
                </li>
              )
            })}
          </ol>
        </div>
      ))}
    </>
  )
}

export function SheetIndex() {
  return (
    <nav className="sheet-index" aria-label="Sheets">
      <SheetList />
    </nav>
  )
}

/** Mobile navigation: previous and next sheet, with the full index in a popover. */
export function SheetPager() {
  const { step, goToStep } = useStudio()
  const list = useRef<HTMLDivElement>(null)
  const sheet = sheetFor(step)
  const previous = steps.at(sheet.index - 1)
  const next = steps.at(sheet.index + 1)
  return (
    <div className="sheet-pager">
      <button
        className="icon-button"
        type="button"
        disabled={sheet.index === 0 || !previous}
        aria-label={previous && sheet.index > 0 ? `Previous sheet: ${previous[1]}` : 'Previous sheet'}
        onClick={() => { if (previous && sheet.index > 0) goToStep(previous[0]) }}
      >
        <ChevronLeft size={20} strokeWidth={1.75} />
      </button>
      <button className="sheet-pager-current" type="button" popoverTarget="sheet-pager-list">
        <span className="numeral">{sheet.number}</span>
        <span className="caption">/ {sheetCount}</span>
        <strong>{sheet.label}</strong>
        <ChevronDown size={16} strokeWidth={1.75} aria-hidden="true" />
        <span className="sr-only">, show all sheets</span>
      </button>
      <button
        className="icon-button"
        type="button"
        disabled={!next}
        aria-label={next ? `Next sheet: ${next[1]}` : 'Next sheet'}
        onClick={() => { if (next) goToStep(next[0]) }}
      >
        <ChevronRight size={20} strokeWidth={1.75} />
      </button>
      <div className="sheet-popover" id="sheet-pager-list" popover="auto" ref={list} role="dialog" aria-label="All sheets">
        <SheetList onPick={() => list.current?.hidePopover()} />
      </div>
    </div>
  )
}
