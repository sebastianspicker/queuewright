import { blankProject } from '../data'
import { toggleFeature } from './features'

describe('feature model facade', () => {
  it('materializes the selected handoff modes through the feature toggle', () => {
    const source = blankProject()
    source.feature_state.cross_department_handoff.settings = {
      modes: ['consultation', 'transfer'],
    }

    const project = toggleFeature(source, 'cross_department_handoff', true)
    const field = project.manifest.object_manager.ticket_fields.find(
      (item) => item.name.endsWith('_handoff_type'),
    )

    expect(project.feature_state.cross_department_handoff.enabled).toBe(true)
    expect(field?.options).toEqual(['consultation', 'transfer'])
    expect(project.manifest.triggers.some((item) => item.key === 'record_handoff')).toBe(true)
  })

  it('removes resources when an optional operational feature is disabled', () => {
    const enabled = toggleFeature(blankProject(), 'checklists', true)
    const disabled = toggleFeature(enabled, 'checklists', false)

    expect(enabled.manifest.checklist_templates).toHaveLength(1)
    expect(disabled.manifest.checklist_templates).toHaveLength(0)
  })
})
