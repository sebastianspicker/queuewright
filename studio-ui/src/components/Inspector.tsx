import { ChevronUp } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
import { useStudio } from '../editor/context'
import { displayGroupName } from '../editor/model'
import { FeatureInspector } from './FeatureInspector'
import { sheetNotes } from './sheet-notes'
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

export function SheetNotesPanel() {
  const { step } = useStudio()
  const notes = sheetNotes[step]
  const headingId = useId()
  return (
    <section className="sheet-notes" aria-labelledby={headingId}>
      <h2 className="caption" id={headingId}>{notes.heading}</h2>
      <ol className={notes.heading === 'Legend' ? 'is-legend' : undefined}>
        {notes.items.map((item) => (
          <li key={item.text}>
            {item.term ? <strong>{item.term}</strong> : null}
            <span>{item.text}</span>
          </li>
        ))}
      </ol>
    </section>
  )
}

/**
 * The notes column. It edits the current selection on Services and Policies
 * and carries the sheet's standing notes elsewhere. Below 760px it becomes a
 * bottom sheet that peeks when something is selected.
 */
export function Inspector() {
  const { step, project, catalog, selectedGroup, selectedFeature } = useStudio()
  const group = step === 'structure' ? project.bundle.manifest.groups.find((item) => item.key === selectedGroup) : undefined
  const feature = step === 'features' ? catalog.find((item) => item.id === selectedFeature) : undefined
  const selectionKey = group?.key ?? feature?.id
  const selectionName = group ? displayGroupName(project.bundle, group) : feature?.name
  const [expanded, setExpanded] = useState(false)
  // Expand only when the user picks something on the current sheet, never on arrival.
  const previous = useRef({ step, selectionKey })
  useEffect(() => {
    if (previous.current.step !== step) setExpanded(false)
    else if (previous.current.selectionKey !== selectionKey) setExpanded(Boolean(selectionKey))
    previous.current = { step, selectionKey }
  }, [step, selectionKey])
  const editing = step === 'structure' || step === 'features'
  const className = [
    'inspector',
    selectionKey ? 'has-selection' : '',
    expanded ? 'is-expanded' : '',
  ].filter(Boolean).join(' ')
  return (
    <aside className={className} aria-label={editing ? 'Inspector' : 'Sheet notes'}>
      {selectionKey ? (
        <button
          className="inspector-peek"
          type="button"
          aria-expanded={expanded}
          aria-controls="inspector-body"
          onClick={() => setExpanded((value) => !value)}
        >
          <span className="caption">{group ? 'Selected' : 'Capability'}</span>
          <strong>{selectionName}</strong>
          <span className="inspector-peek-action">{expanded ? 'Hide' : 'Edit'}<ChevronUp size={16} strokeWidth={1.75} aria-hidden="true" /></span>
        </button>
      ) : null}
      <div className="inspector-body" id="inspector-body">
        {step === 'structure' ? <StructureInspector Switch={Switch} /> : null}
        {step === 'features' ? <FeatureInspector Switch={Switch} /> : null}
        {!selectionKey ? <SheetNotesPanel /> : null}
      </div>
    </aside>
  )
}
