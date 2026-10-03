import type { StepId } from '../contracts'

export interface SheetNotes {
  heading: 'Notes' | 'Legend'
  items: Array<{ term?: string; text: string }>
}

/** Standing notes for each sheet, shown in the notes column when nothing is selected. */
export const sheetNotes: Record<StepId, SheetNotes> = {
  start: {
    heading: 'Notes',
    items: [
      { text: 'Projects are kept in this browser only, for this local address. Clearing site data removes them.' },
      { text: 'Import accepts a profile with its desired-state manifest, a V1 project, or a Blueprint V2 document. V1 projects are migrated before they are saved.' },
      { text: 'Schema 1.0 allows a single root with services directly beneath it. Use 1.1 to nest units.' },
    ],
  },
  organization: {
    heading: 'Notes',
    items: [
      { text: 'Describe roles, not people. Names, email addresses, tenant URLs and credentials do not belong in a project.' },
      { text: 'Additive, inactive changes are the safest change strategy: new configuration arrives switched off.' },
    ],
  },
  structure: {
    heading: 'Notes',
    items: [
      { text: 'Units organize the tree. Only services carry tickets and receive access roles.' },
      { text: 'New units and services are placed under the selected unit, or beside the selected service.' },
      { text: 'Drag a row by its handle to reorder it among its siblings.' },
    ],
  },
  access: {
    heading: 'Legend',
    items: [
      { term: 'none', text: 'No access to the service.' },
      { term: 'read', text: 'Read tickets in the service.' },
      { term: 'create', text: 'Create tickets in the service.' },
      { term: 'work', text: 'Full access to the service\'s tickets (Zammad full).' },
      { text: 'Grant each role only the services and actions its agents need.' },
    ],
  },
  features: {
    heading: 'Notes',
    items: [
      { text: 'Enabling a capability also enables the capabilities it depends on.' },
      { text: 'Locked capabilities belong to the safe baseline and stay on.' },
      { text: 'Reset returns every capability to the safe baseline.' },
    ],
  },
  governance: {
    heading: 'Legend',
    items: [
      { term: 'Automated', text: 'Generated in the local bundle from the earlier sheets.' },
      { term: 'Guided manual', text: 'An administrator performs it outside Studio and keeps the evidence.' },
      { term: 'Verify only', text: 'Requires evidence from the existing platform.' },
      { term: 'Unsupported', text: 'Not delivered by this workflow. It stays visible as a blocker.' },
    ],
  },
  'test-data': {
    heading: 'Notes',
    items: [
      { text: 'Ready means locally valid for review. It is not evidence that anything was applied or verified.' },
      { text: 'Synthetic users and UAT scenarios are internal only; outbound communication stays disabled.' },
    ],
  },
  review: {
    heading: 'Notes',
    items: [
      { text: 'Exports use only the latest successful local compile. Any edit disables them until you validate again.' },
      { text: 'The graph hash identifies the complete canonical artifacts, so a reviewer can confirm they received exactly this revision.' },
    ],
  },
}
