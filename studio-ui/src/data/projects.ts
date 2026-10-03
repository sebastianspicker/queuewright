import exampleManifestJson from '../../../queuewright/examples/minimal/desired-state.json'
import exampleProfileJson from '../../../queuewright/examples/minimal/profile.json'
import minimalProjectV2Json from '../../../queuewright/examples/minimal/project-v2.json'
import universityManifestJson from '../../../queuewright/examples/university/university.desired-state.json'
import universityProfileJson from '../../../queuewright/examples/university/profile.json'
import universityProjectV2Json from '../../../queuewright/examples/university/project-v2.json'
import {
  type ManifestDocument,
  type ProfileDocument,
  type RawBundle,
  type StudioProjectV2,
} from '../contracts'
import { cloneJson as clone } from '../contracts/runtime'

/** Checked-in output from the backend compiler, used only by the network-free static demo. */
export function staticDemoProject(kind: 'blank' | 'example' = 'example'): StudioProjectV2 {
  return clone(
    (kind === 'blank' ? minimalProjectV2Json : universityProjectV2Json) as StudioProjectV2,
  )
}

export function exampleBundle(): RawBundle {
  return {
    profile: clone(universityProfileJson) as ProfileDocument,
    manifest: clone(universityManifestJson) as ManifestDocument,
  }
}

function blankDocuments(): RawBundle {
  const profile = clone(exampleProfileJson) as ProfileDocument
  const manifest = clone(exampleManifestJson) as ManifestDocument
  profile.schema_version = '1.1'
  manifest.schema_version = '1.1'
  profile.profile_key = 'queuewright_draft'
  profile.display_name = 'Untitled configuration'
  profile.manifest = 'queuewright_draft.desired-state.json'
  profile.identity.agent_login_template = 'queuewright_draft.agent.{key}'
  profile.identity.customer_login_template = 'queuewright_draft.customer.{key}'
  profile.identity.email_template = 'queuewright_draft.{kind}.{key}@example.invalid'
  profile.identity.agent_firstname = 'qWright'
  profile.identity.customer_firstname = 'qWright'
  profile.presentation.field_labels = { queuewright_draft_service_code: 'Service' }
  profile.presentation.core_workflow_names = {
    agent_create_shared: 'qWright Draft · CW · Agent create shared',
  }
  profile.uat.title_prefix = '[QWRIGHT-UAT]'
  const firstScenario = profile.uat.scenarios.at(0)
  if (firstScenario) firstScenario.expected_tags = ['queuewright_draft/uat']
  manifest.manifest_key = 'queuewright-draft-v1'
  manifest.managed_prefix = 'qWright Draft ·'
  manifest.technical_namespace = 'queuewright_draft_'
  for (const item of [...manifest.groups, ...manifest.organizations, ...manifest.roles]) {
    item.name = item.name?.replace('Example Prototype ·', 'qWright Draft ·') ?? ''
  }
  manifest.users.email_template = 'queuewright_draft.{kind}.{key}@example.invalid'
  manifest.overviews = []
  manifest.macros = []
  manifest.tags = ['queuewright_draft/uat']
  manifest.checklist_templates = []
  manifest.triggers = []
  manifest.jobs = []
  manifest.report_profiles = []
  const firstTicketField = manifest.object_manager.ticket_fields.at(0)
  if (firstTicketField) firstTicketField.name = 'queuewright_draft_service_code'
  manifest.uat.title_prefix = '[QWRIGHT-UAT]'
  return { profile, manifest }
}

/** Raw authored input for normal creation; the API creates all canonical metadata. */
export function blankBundle(): RawBundle {
  return blankDocuments()
}
