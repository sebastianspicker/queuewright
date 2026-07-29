import type { CapabilityDecision } from '../types'
import { capabilityDomains } from './capability-meta'

export function decisionsByDomain(decisions: Array<[string, CapabilityDecision]>) {
  const domains = new Map<string, Array<[string, CapabilityDecision]>>()
  for (const decision of decisions) {
    const domain = capabilityDomains[decision[0]] ?? 'Unclassified capability'
    domains.set(domain, [...(domains.get(domain) ?? []), decision])
  }
  return domains
}
