import type { CapabilityDelivery } from '../types'

export function decisionPresentation(delivery: CapabilityDelivery) {
  switch (delivery) {
    case 'automated':
      return {
        deliveryIsLocked: true,
        deliveryHint: 'Configure this capability in the preceding design steps.',
        manualBoundary: undefined,
      }
    case 'guided_manual':
      return {
        deliveryIsLocked: false,
        deliveryHint: undefined,
        manualBoundary: 'Manual delivery: assign and evidence the administrator work outside this studio.',
      }
    case 'unsupported':
      return {
        deliveryIsLocked: true,
        deliveryHint: 'This capability remains disabled because this workflow cannot deliver it.',
        manualBoundary: 'Unsupported: retain this as a visible blocker; no workaround is applied here.',
      }
    default:
      return { deliveryIsLocked: false, deliveryHint: undefined, manualBoundary: undefined }
  }
}
