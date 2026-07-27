import { bundledCatalog, exampleProject } from './data'
import {
  addGroup,
  moveGroup,
  permissionFor,
  setCustomerEntryPoint,
  setHandoffModes,
  setPermission,
  toggleFeature,
} from './project-model'

describe('project model', () => {
  it('loads the neutral university template with every owned feature enabled', () => {
    const project = exampleProject()
    const enabled = new Set(
      Object.entries(project.feature_state)
        .filter(([, state]) => state.enabled)
        .map(([id]) => id),
    )

    expect(project.profile.profile_key).toBe('university')
    expect(project.profile.identity.email_template).toBe(
      'university.{kind}.{key}@example.invalid',
    )
    expect(enabled).toEqual(new Set(bundledCatalog.map((feature) => feature.id)))
    for (const owner of Object.values(project.resource_ownership)) {
      if (owner === 'core' || owner === 'custom') continue
      expect(project.feature_state[owner].enabled).toBe(true)
    }
  })

  it('adds a service to the authoritative bundle and ownership map', () => {
    const source = exampleProject()
    const { project, key } = addGroup(source, 'leaf', 'academic_services')

    expect(project.manifest.groups).toHaveLength(source.manifest.groups.length + 1)
    expect(project.manifest.roles.some((role) => role.key === key)).toBe(true)
    expect(project.manifest.users.agents.some((agent) => agent.role === key)).toBe(true)
    expect(project.profile.uat.scenarios.some((scenario) => scenario.group === key)).toBe(true)
    expect(project.resource_ownership[`groups:${key}`]).toBe('core')
  })

  it('maps the visual ACL level into the manifest role ACL', () => {
    const source = exampleProject()
    const project = setPermission(source, 'finance', 'student_services', 'read')
    const role = project.manifest.roles.find((item) => item.key === 'finance')

    expect(role).toBeDefined()
    expect(permissionFor(role!, 'student_services')).toBe('read')
    expect(role?.acl.read).toContain('student_services')
  })

  it('materializes and removes optional feature resources', () => {
    const source = exampleProject()
    const enabled = toggleFeature(source, 'checklists', true)
    const disabled = toggleFeature(enabled, 'checklists', false)

    expect(enabled.manifest.checklist_templates).toHaveLength(1)
    expect(disabled.manifest.checklist_templates).toHaveLength(0)
  })

  it('rejects descendant reparenting without mutating the project', () => {
    const source = exampleProject()
    expect(moveGroup(source, 'academic_services', 'student_services')).toBe(source)
  })

  it('materializes customer login entry points as a customer-create workflow', () => {
    const project = setCustomerEntryPoint(
      exampleProject(),
      'student_services',
      true,
    )
    const workflow = project.manifest.object_manager.core_workflows.find(
      (item) => item.key === 'customer_create_entry_points',
    )

    expect(workflow?.context).toBe('customer_create')
    expect(workflow?.match).toContain('student_services')
    expect(project.resource_ownership['core_workflows:customer_create_entry_points']).toBe('core')
  })

  it('materializes selected handoff modes into the managed field options', () => {
    const project = setHandoffModes(exampleProject(), ['consultation', 'transfer'])
    const field = project.manifest.object_manager.ticket_fields.find(
      (item) => item.name.endsWith('_handoff_type'),
    )

    expect(field?.options).toEqual(['consultation', 'transfer'])
    expect(project.feature_state.cross_department_handoff.settings.modes)
      .toEqual(['consultation', 'transfer'])
  })
})
