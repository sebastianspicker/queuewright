import {
  FEATURE_IDS,
  type ApiError,
  type BlueprintCompileResult,
  type CatalogResponse,
  type FeatureDefinition,
  type FeatureId,
  type RawBundle,
  type StudioProjectV1,
  type StudioProjectV2,
  type StudioProjectV2Draft,
} from '../contracts'
import { featureDefinition } from '../contracts/runtime'

export class StudioApiError extends Error {
  readonly code: string
  readonly path: string
  readonly status: number

  constructor(status: number, error: ApiError) {
    super(error.message)
    this.name = 'StudioApiError'
    this.status = status
    this.code = error.code
    this.path = error.path
  }
}

function isFeatureId(value: string): value is FeatureId {
  return (FEATURE_IDS as readonly string[]).includes(value)
}

/** Drop compiler-owned mirrors and catalog metadata before revalidating an editable V2 draft. */
export function editableV2Draft(project: StudioProjectV2): StudioProjectV2Draft {
  return {
    project_schema_version: '2.0', id: project.id, name: project.name,
    target_schema_version: project.target_schema_version,
    workbook: {
      organization: project.workbook.organization,
      capability_decisions: Object.fromEntries(
        Object.entries(project.workbook.capability_decisions).map(([id, decision]) => [id, {
          enabled: decision.enabled,
          completion: decision.completion,
        }]),
      ),
    },
    extensions: project.extensions,
    bundle: project.bundle,
  }
}

async function json<T>(response: Response): Promise<T> {
  const body = (await response.json()) as T | ApiError
  if (!response.ok) {
    const error = body as ApiError
    throw new StudioApiError(response.status, {
      code: error.code ?? 'request_failed', path: error.path ?? 'request',
      message: error.message ?? `Local qWright request failed (${response.status})`,
    })
  }
  return body as T
}

type GraphNode = BlueprintCompileResult['graph']['nodes'][number]
interface EditorCompileResponse extends Omit<BlueprintCompileResult, 'bundle' | 'graph'> {
  representation: 'editor-1'
  graph: { graph_hash: string; nodes: Array<Omit<GraphNode, 'desired'> & Partial<Pick<GraphNode, 'desired'>>> }
}

/** Restore duplicate artifact values without changing the server's canonical hashes. */
export function expandEditorResponse(response: EditorCompileResponse): BlueprintCompileResult {
  if (response.representation !== 'editor-1') {
    throw new StudioApiError(502, { code: 'invalid_response', path: 'representation', message: 'Unsupported local compiler response.' })
  }
  const operations = new Map(response.plan.operations.map((operation) => [operation.id, operation]))
  const nodes = response.graph.nodes.map((node): GraphNode => {
    if ('desired' in node && node.desired !== undefined) return node as GraphNode
    const operation = operations.get(node.id)
    if (!operation || !('desired_state' in operation)) {
      throw new StudioApiError(502, { code: 'invalid_response', path: `graph.${node.id}`, message: 'The local compiler response is incomplete.' })
    }
    return { ...node, desired: operation.desired_state }
  })
  const { representation: _representation, ...compiled } = response
  return { ...compiled, bundle: response.project.bundle, graph: { ...response.graph, nodes } }
}

/** The only browser transport boundary. */
export const api = {
  async loadCatalog(signal?: AbortSignal): Promise<FeatureDefinition[]> {
    const catalog = await json<CatalogResponse>(await fetch('/api/v1/catalog', { signal }))
    return catalog.features.filter((feature) => isFeatureId(feature.id)).map(featureDefinition)
  },

  /** Sends authored fields once and accepts the server-normalized canonical V2 result. */
  async compile(input: RawBundle | StudioProjectV1 | StudioProjectV2, signal?: AbortSignal): Promise<BlueprintCompileResult> {
    const body = 'project_schema_version' in input
      ? { project: input.project_schema_version === '2.0' ? editableV2Draft(input) : input }
      : input
    return expandEditorResponse(await json<EditorCompileResponse>(await fetch('/api/v2/compile-editor', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body), signal,
    })))
  },
}
