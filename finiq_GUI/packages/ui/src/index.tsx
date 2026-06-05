import type { ReactNode } from 'react'

interface AppHeaderProps {
  kicker: string
  title: string
  description?: string
  actions?: ReactNode
}

interface EmptyStateProps {
  title: string
  children?: ReactNode
}

export function AppHeader({ kicker, title, description, actions }: AppHeaderProps) {
  return (
    <header className="top-bar">
      <div className="brand-block">
        <span className="app-kicker">{kicker}</span>
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className="toolbar-actions">{actions}</div> : null}
    </header>
  )
}

export function EmptyState({ title, children }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <h2>{title}</h2>
      {children ? <p>{children}</p> : null}
    </div>
  )
}
