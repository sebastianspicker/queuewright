import { ChevronDown } from 'lucide-react'
import { useStudio } from '../editor/context'
import { ImportControl } from './ImportControl'
import { SheetPager } from './SheetIndex'

export function TopBar() {
  const { project, compiling, demoMode, step, goToStep, validateNow } = useStudio()
  return (
    <header className="topbar">
      <div className="wordmark">
        <span className="wordmark-name">Queuewright</span>
        <span className="wordmark-product">Studio</span>
        {demoMode ? <span className="tag is-solid wordmark-demo">Demo</span> : null}
      </div>
      <button
        className="project-switcher"
        type="button"
        onClick={() => goToStep('start')}
        aria-current={step === 'start' ? 'page' : undefined}
      >
        <span className="caption">Project</span>
        <strong>{project.name}</strong>
        <ChevronDown size={16} strokeWidth={1.75} aria-hidden="true" />
        <span className="sr-only">, open project list</span>
      </button>
      <div className="topbar-actions">
        <ImportControl compact />
        <button
          className="button primary validate-button"
          type="button"
          onClick={validateNow}
          disabled={compiling}
        >
          {compiling
            ? 'Validating…'
            : demoMode
              ? <span>Simulate<span className="validate-long"> validation</span></span>
              : <span>Validate<span className="validate-long"> design</span></span>}
        </button>
      </div>
      <SheetPager />
    </header>
  )
}
