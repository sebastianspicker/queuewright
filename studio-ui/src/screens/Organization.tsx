import { useStudioProject } from '../editor/context'
import { replaceOrganizationValue } from '../editor/model'
import { PageHeader } from '../components/ui'
import {
  organizationFields,
  organizationValue,
  title,
} from './capability-meta'

const optionLabels: Record<string, string> = {
  en: 'English (en)',
  de: 'German (de)',
  fr: 'French (fr)',
  es: 'Spanish (es)',
  business_hours: 'Business hours',
  extended_hours: 'Extended hours',
  follow_the_sun: 'Follow the sun',
  '24x7': '24 x 7',
  sso_primary: 'SSO primary',
  local_hardened: 'Local accounts, hardened',
  mixed_transition: 'Mixed, in transition',
  additive_inactive: 'Additive and inactive',
  pilot_then_expand: 'Pilot, then expand',
  manual_only: 'Manual only',
}

export function Organization() {
  const { project, updateProject } = useStudioProject()
  return (
    <section className="organization-screen">
      <PageHeader
        title="Operating context"
        description="How the institution runs its service desk, in plain language. This sheet deliberately has no place for contact details, tenant addresses, URLs or credentials."
      />
      <div className="form-sheet" role="group" aria-label="Organization details">
        {organizationFields.map((field) => {
          const id = `organization-${field.key}`
          return (
            <div className="form-row" key={field.key}>
              <label htmlFor={id}>
                <strong>{field.label}</strong>
                <small>{field.description}</small>
              </label>
              {field.kind === 'select' ? (
                <select
                  className="select"
                  id={id}
                  value={organizationValue(project, field.key)}
                  onChange={(event) => updateProject(
                    replaceOrganizationValue(project, field.key, event.target.value),
                  )}
                >
                  <option value="">Not decided</option>
                  {field.options.map((option) => (
                    <option value={option} key={option}>{optionLabels[option] ?? title(option)}</option>
                  ))}
                </select>
              ) : (
                <input
                  className="input"
                  id={id}
                  value={organizationValue(project, field.key)}
                  placeholder={`e.g. ${field.placeholder}`}
                  onChange={(event) => updateProject(
                    replaceOrganizationValue(project, field.key, event.target.value),
                  )}
                />
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}
