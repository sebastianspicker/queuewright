import { ShieldAlert } from 'lucide-react'
import { useStudioProject } from '../editor/context'
import { replaceOrganizationValue } from '../editor/model'
import { PageHeader } from '../components/ui'
import {
  organizationFields,
  organizationValue,
  title,
} from './capability-meta'

export function Organization() {
  const { project, updateProject } = useStudioProject()
  return (
    <section className="organization-screen">
      <PageHeader
        kicker="Step 02 · Operating context"
        title="Describe the organization"
        description="Use plain-language operational context. This workbook intentionally does not collect contact details, tenant addresses, URLs, or credentials."
      />
      <div className="organization-fields" aria-label="Safe organization details">
        {organizationFields.map((field) => (
          <label className="field organization-field" key={field.key}>
            <span>{field.label}<small>{field.description}</small></span>
            {field.kind === 'select' ? (
              <select
                value={organizationValue(project, field.key)}
                onChange={(event) => updateProject(
                  replaceOrganizationValue(project, field.key, event.target.value),
                )}
              >
                <option value="">Choose…</option>
                {field.options.map((option) => (
                  <option value={option} key={option}>{title(option)}</option>
                ))}
              </select>
            ) : (
              <input
                value={organizationValue(project, field.key)}
                placeholder={field.placeholder}
                onChange={(event) => updateProject(
                  replaceOrganizationValue(project, field.key, event.target.value),
                )}
              />
            )}
          </label>
        ))}
      </div>
      <p className="notice"><ShieldAlert size={18} aria-hidden="true" /> Keep this workspace local and synthetic. Connection, application, and tenant administration are outside this workflow.</p>
    </section>
  )
}
