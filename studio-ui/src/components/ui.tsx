import type { ReactNode } from 'react'
import { useStudioStep } from '../editor/context'
import { sheetCount, sheetFor } from './steps'

export function PageHeader({
  title,
  description,
  action,
}: {
  title: string
  description: ReactNode
  action?: ReactNode
}) {
  const sheet = sheetFor(useStudioStep())
  return (
    <header className="sheet-header">
      <p className="sheet-header-number" aria-label={`Sheet ${sheet.index + 1} of ${sheetCount}, ${sheet.phase}`}>
        <span className="numeral" aria-hidden="true">{sheet.number}</span>
        <span className="caption" aria-hidden="true">/ {sheetCount} · {sheet.phase}</span>
      </p>
      <div className="sheet-header-text">
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action ? <div className="sheet-header-action">{action}</div> : null}
    </header>
  )
}

export function SectionHeading({
  children,
  id,
  aside,
}: {
  children: ReactNode
  id?: string
  aside?: ReactNode
}) {
  return (
    <div className={aside ? 'section-heading has-aside' : 'section-heading'}>
      <h2 id={id}>{children}</h2>
      <span aria-hidden="true" />
      {aside}
    </div>
  )
}

export function EmptyState({
  title,
  children,
}: {
  title: string
  children: ReactNode
}) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      <p>{children}</p>
    </div>
  )
}

/** The drafting revision mark: a triangle carrying a count of open items. */
export function Delta({ count, label, accessibleLabel }: { count: number; label?: string; accessibleLabel?: string }) {
  return (
    <span className="delta" role={label ? undefined : 'img'} aria-label={label ? undefined : accessibleLabel ?? `${count} open`}>
      <svg width="22" height="20" viewBox="0 0 22 20" aria-hidden="true">
        <path d="M11 1.3 L20.7 18.7 H1.3 Z" />
        <text x="11" y="16.2" textAnchor="middle">{count > 99 ? '99+' : count}</text>
      </svg>
      {label ? <span className="delta-label"><span className="sr-only">{count} </span>{label}</span> : null}
    </span>
  )
}
