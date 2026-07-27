import {
  ChevronDown,
  LockKeyhole,
  Menu,
  ShieldCheck,
  University,
} from 'lucide-react'
import { useStudio } from '../studio-state'
import { ImportControl } from './ImportControl'

export function TopBar() {
  const { project, compiling, dispatch, validateNow } = useStudio()
  const goToProjects = () => dispatch({ type: 'step', step: 'start' })
  return (
    <header className="topbar">
      <button className="icon-button menu-button" type="button" aria-label="Open projects" onClick={goToProjects}>
        <Menu size={24} />
      </button>
      <div className="brand" aria-label="qWright">
        <span className="brand-mark" aria-hidden="true">q</span>
        <span aria-hidden="true"><span className="brand-accent">q</span>Wright</span>
      </div>
      <button className="project-switcher" type="button" onClick={goToProjects}>
        <University size={21} />
        <span className="project-copy">
          <small>Current project</small>
          <strong>{project.name}</strong>
        </span>
        <ChevronDown size={17} />
      </button>
      <span className="local-badge">
        <LockKeyhole size={15} aria-hidden="true" />
        Local workspace
      </span>
      <ImportControl compact />
      <button
        className="button primary validate-button"
        type="button"
        onClick={validateNow}
        disabled={compiling}
      >
        <ShieldCheck size={19} />
        {compiling ? 'Validating…' : 'Validate design'}
      </button>
    </header>
  )
}
