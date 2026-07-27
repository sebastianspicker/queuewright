import type { ReactNode } from 'react'

export function PageHeader({
  title,
  description,
  action,
  kicker,
}: {
  title: string
  description: string
  action?: ReactNode
  kicker?: string
}) {
  return (
    <header className={action ? 'page-heading page-heading-with-action' : 'page-heading'}>
      <div>
        {kicker ? <span className="page-kicker">{kicker}</span> : null}
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </header>
  )
}

export function SectionHeading({
  children,
  id,
}: {
  children: ReactNode
  id?: string
}) {
  return (
    <div className="section-heading">
      <h2 id={id}>{children}</h2>
      <span aria-hidden="true" />
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
