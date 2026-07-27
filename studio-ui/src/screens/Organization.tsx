import { ShieldAlert } from 'lucide-react'
import { useStudio } from '../studio-state'
import { PageHeader } from '../ui'
import {
  organizationFields,
  organizationValue,
  replaceOrganizationValue,
  title,
} from './capability-meta'

export function Organization() {
  const { blueprint, updateBlueprint } = useStudio()
  return (
    <section className="organization-screen">
      <PageHeader
        kicker="Step 02 · Operating context"
        title="Describe the organization"
        description="Use plain-language operational context. This workbook intentionally does not collect contact details, tenant addresses, URLs, or credentials."
      />
      {!blueprint ? <p className="notice">A Blueprint V2 project is required before organization details can be reviewed.</p> : null}
      {blueprint ? <div className="organization-fields" aria-label="Safe organization details">
        {organizationFields.map((field) => (
          <label className="field organization-field" key={field.key}>
            <span>{field.label}<small>{field.description}</small></span>
            {field.kind === 'select' ? (
              <select
                value={organizationValue(blueprint, field.key)}
                onChange={(event) => updateBlueprint(
                  replaceOrganizationValue(blueprint, field.key, event.target.value),
                )}
              >
                <option value="">Choose…</option>
                {field.options.map((option) => (
                  <option value={option} key={option}>{title(option)}</option>
                ))}
              </select>
            ) : (
              <input
                value={organizationValue(blueprint, field.key)}
                placeholder={field.placeholder}
                onChange={(event) => updateBlueprint(
                  replaceOrganizationValue(blueprint, field.key, event.target.value),
                )}
              />
            )}
          </label>
        ))}
      </div> : null}
      <p className="notice"><ShieldAlert size={18} aria-hidden="true" /> Keep this workspace local and synthetic. Connection, application, and tenant administration are outside this workflow.</p>
    </section>
  )
}
