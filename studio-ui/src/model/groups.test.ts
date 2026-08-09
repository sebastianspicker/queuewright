import { exampleProject } from '../data'
import {
  addGroup,
  customerEntryPoints,
  removeGroup,
  setCustomerEntryPoint,
} from './groups'

describe('group model facade', () => {
  it('keeps dependent resources in sync when a newly added service is removed', () => {
    const source = exampleProject()
    const { project: added, key } = addGroup(source, 'leaf', 'academic_services')
    const next = removeGroup(added, key)

    expect(next.manifest.groups.some((group) => group.key === key)).toBe(false)
    expect(next.manifest.roles.some((role) => role.key === key)).toBe(false)
    expect(next.manifest.users.agents.some((agent) => agent.key === key)).toBe(false)
    expect(next.profile.uat.scenarios.some((scenario) => scenario.key === `seed_${key}`)).toBe(false)
  })

  it('preserves the public customer-entry-point helpers', () => {
    const project = setCustomerEntryPoint(exampleProject(), 'student_services', true)

    expect(customerEntryPoints(project)).toEqual(['student_services'])
  })
})
