import type {
  BlueprintCompileResult,
  CapabilityCompletion,
  CapabilityDecision,
  CapabilityDelivery,
  StudioProjectV2,
} from '../types'

export const completions: CapabilityCompletion[] = [
  'decision_required',
  'ready',
  'blocked',
]

export const capabilityDomains: Record<string, string> = {
  organization: 'Organization',
  'service-topology': 'Service topology',
  'organizations-customers': 'Organizations and customers',
  'roles-acl': 'Roles and access control',
  'identity-security': 'Identity and security',
  'fields-core-workflows': 'Fields and core workflows',
  'calendars-sla': 'Calendars and service levels',
  tags: 'Tags',
  'overviews-macros-templates-text-modules-checklists': 'Agent productivity',
  'triggers-schedulers-report-profiles': 'Automation and reporting',
  'channels-postmaster-signatures': 'Channels',
  'webhooks-integrations': 'Integrations',
  'knowledge-base': 'Knowledge base',
  'time-accounting': 'Time accounting',
  'privacy-retention': 'Privacy and retention',
  'branding-ticket-settings': 'Branding and ticket settings',
  ai: 'AI',
  'uat-evidence': 'UAT evidence',
  'platform-dr': 'Platform continuity',
}

export const capabilityGuidance: Record<string, string> = {
  organization: 'Record the operating context and ownership model that guide every later choice.',
  'service-topology': 'Design ticket-bearing services and their parent units as one understandable tree.',
  'organizations-customers': 'Define customer segmentation without broad sharing or automatic domain assignment.',
  'roles-acl': 'Grant each role only the services and actions its agents need.',
  'identity-security': 'Plan authentication, session, and administrator controls through a reviewed manual change.',
  'fields-core-workflows': 'Plan fields and conditional forms with migration and restart impacts made explicit.',
  'calendars-sla': 'Define business calendars, response targets, and escalation ownership.',
  tags: 'Keep a governed tag vocabulary for routing, reporting, and safe test evidence.',
  'overviews-macros-templates-text-modules-checklists': 'Give agents focused views and reusable tools without hidden global behavior.',
  'triggers-schedulers-report-profiles': 'Design automation with narrow scopes, collision checks, and named owners.',
  'channels-postmaster-signatures': 'Plan inbound and outbound identities without placing channel secrets in this project.',
  'webhooks-integrations': 'Account for external integrations while keeping unsupported outbound execution blocked.',
  'knowledge-base': 'Plan audience, ownership, review cadence, and publication workflow.',
  'time-accounting': 'Define when time is captured and how it supports reporting.',
  'privacy-retention': 'Document retention and privacy operations that require privileged human review.',
  'branding-ticket-settings': 'Choose safe presentation and ticket defaults without hiding tenant-wide impact.',
  ai: 'Keep optional AI surfaces visible as unsupported until a separate reviewed integration exists.',
  'uat-evidence': 'Prove the design with synthetic users, internal articles, and retained evidence.',
  'platform-dr': 'Record backup, restore, upgrade, monitoring, and continuity evidence outside API configuration.',
}

export const organizationFields = [
  {
    key: 'name',
    label: 'Organization name',
    description: 'A display name for this configuration workbook.',
    kind: 'text',
    placeholder: 'Example University',
  },
  {
    key: 'service_owner_role',
    label: 'Service owner role',
    description: 'Use a role title, not a person or contact address.',
    kind: 'text',
    placeholder: 'Head of Service Management',
  },
  {
    key: 'operating_model',
    label: 'Operating model',
    description: 'How service ownership is distributed.',
    kind: 'select',
    options: ['centralized', 'federated', 'hybrid'],
  },
  {
    key: 'primary_language',
    label: 'Primary language',
    description: 'The default language for labels and guidance.',
    kind: 'select',
    options: ['en', 'de', 'fr', 'es'],
  },
  {
    key: 'timezone',
    label: 'Business timezone',
    description: 'Use an IANA timezone such as Europe/Berlin.',
    kind: 'text',
    placeholder: 'Europe/Berlin',
  },
  {
    key: 'support_model',
    label: 'Support model',
    description: 'The broad coverage model used when designing calendars.',
    kind: 'select',
    options: ['business_hours', 'extended_hours', 'follow_the_sun', '24x7'],
  },
  {
    key: 'security_baseline',
    label: 'Security baseline',
    description: 'The policy posture the guided manual steps must satisfy.',
    kind: 'select',
    options: ['sso_primary', 'local_hardened', 'mixed_transition'],
  },
  {
    key: 'change_strategy',
    label: 'Change strategy',
    description: 'Additive inactive changes are the safest default.',
    kind: 'select',
    options: ['additive_inactive', 'pilot_then_expand', 'manual_only'],
  },
] as const

export function title(value: string): string {
  return value.replaceAll('_', ' ').replaceAll('-', ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

export function organizationValue(project: StudioProjectV2, key: string): string {
  const value = Object.entries(project.workbook.organization).find(
    ([candidate]) => candidate === key,
  )?.[1]
  return typeof value === 'string' ? value : ''
}

export function replaceOrganizationValue(
  project: StudioProjectV2,
  key: string,
  value: string,
): StudioProjectV2 {
  return {
    ...project,
    workbook: {
      ...project.workbook,
      organization: {
        ...project.workbook.organization,
        [key]: value,
      },
    },
  }
}

export function replaceDecision(
  project: StudioProjectV2,
  id: string,
  patch: Partial<Pick<CapabilityDecision, 'enabled' | 'completion'>>,
): StudioProjectV2 {
  const source = project.workbook.capability_decisions
  const target = Object.entries(source).find(([candidate]) => candidate === id)
  if (!target) return project
  const decisions = Object.fromEntries(
    Object.entries(source).map(([key, decision]) => [key, { ...decision }]),
  )
  const updatedTarget = Object.entries(decisions).find(([candidate]) => candidate === id)?.[1]
  const decisionFor = (capabilityId: string) => Object.entries(decisions).find(
    ([candidate]) => candidate === capabilityId,
  )?.[1]
  const disable = (capabilityId: string) => {
    const decision = decisionFor(capabilityId)
    if (!decision) return
    decision.enabled = false
    decision.completion = decision.delivery === 'unsupported' ? 'blocked' : 'decision_required'
    for (const [dependentId, dependent] of Object.entries(decisions)) {
      if (dependent.dependencies.includes(capabilityId)) disable(dependentId)
    }
  }
  const enable = (capabilityId: string) => {
    const decision = decisionFor(capabilityId)
    if (!decision) return
    decision.enabled = true
    for (const dependency of decision.dependencies) enable(dependency)
    if (decision.delivery === 'unsupported') decision.completion = 'blocked'
  }
  const setEnabled = (capabilityId: string, enabled: boolean) => {
    if (enabled) enable(capabilityId)
    else disable(capabilityId)
  }
  if (patch.enabled !== undefined) setEnabled(id, patch.enabled)
  if (patch.completion !== undefined && updatedTarget) {
    updatedTarget.completion = patch.completion
  }
  return {
    ...project,
    workbook: {
      ...project.workbook,
      capability_decisions: {
        ...decisions,
      },
    },
  }
}

export function deliveryMessage(value: CapabilityDelivery): string {
  const messages = new Map<CapabilityDelivery, string>([
    ['automated', 'Generated in the local bundle'],
    ['guided_manual', 'Requires a documented manual administrator action'],
    ['verify_only', 'Requires evidence from the existing platform'],
    ['unsupported', 'Not delivered by this workflow'],
  ])
  return messages.get(value) ?? 'Not delivered by this workflow'
}

export function graphSummary(result?: BlueprintCompileResult): Array<[string, string]> {
  if (!result) return [['Configuration graph', 'Awaiting a local V2 compile']]
  const count = (delivery: CapabilityDelivery) => result.graph.nodes.filter(
    (node) => node.delivery === delivery,
  ).length
  return [
    ['Configuration graph', `${result.graph.nodes.length} nodes in the compiled snapshot`],
    ['Graph identity', result.graph.graph_hash],
    ['Automated nodes', String(count('automated'))],
    ['Manual nodes', String(count('guided_manual'))],
    ['Unsupported nodes', String(count('unsupported'))],
  ]
}
