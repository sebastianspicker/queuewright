import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { ChevronRight, GripVertical, Plus } from 'lucide-react'
import { addGroup, customerEntryPoints, reorderGroup } from '../editor/model'
import { useStudioStructure } from '../editor/context'
import { PageHeader, SectionHeading } from '../components/ui'
import { useStateSet } from './useStateSet'
import { useEffect, useMemo } from 'react'
import type { CSSProperties } from 'react'
import type { GroupResource } from '../contracts'

interface TreeItem {
  group: GroupResource
  depth: number
}

export function flattenTree(
  groups: GroupResource[],
  expanded: Set<string>,
): TreeItem[] {
  const root = groups.find((group) => group.parent === undefined)
  if (!root) return groups.map((group) => ({ group, depth: 0 }))
  const children = new Map<string, GroupResource[]>()
  for (const group of groups) {
    if (group.parent === undefined) continue
    const siblings = children.get(group.parent) ?? []
    siblings.push(group)
    children.set(group.parent, siblings)
  }
  const output: TreeItem[] = []
  const visit = (group: GroupResource, depth: number) => {
    output.push({ group, depth })
    if (group.kind === 'container' && expanded.has(group.key)) {
      for (const child of children.get(group.key) ?? []) {
        visit(child, depth + 1)
      }
    }
  }
  visit(root, 0)
  return output
}

function SortableTreeRow({
  item,
  name,
  selected,
  expanded,
  entryPoint,
  onSelect,
  onExpand,
}: {
  item: TreeItem
  name: string
  selected: boolean
  expanded: boolean
  entryPoint: boolean
  onSelect(): void
  onExpand(): void
}) {
  const sortable = useSortable({ id: item.group.key, disabled: item.depth === 0 })
  const style = {
    transform: CSS.Translate.toString(sortable.transform),
    transition: sortable.transition,
    '--tree-depth': item.depth,
  } as CSSProperties
  const { group, depth } = item
  const isContainer = group.kind === 'container'
  const kind = depth === 0 ? 'root' : isContainer ? 'unit' : 'service'
  const rowClass = ['tree-row', `is-${kind}`, selected ? 'is-selected' : '', sortable.isDragging ? 'is-dragging' : ''].filter(Boolean).join(' ')
  return (
    <li ref={sortable.setNodeRef} style={style} className={rowClass} onClick={onSelect}>
      <span className="tree-guides" aria-hidden="true" />
      {isContainer ? (
        <button
          type="button"
          className="tree-disclosure"
          onClick={(event) => { event.stopPropagation(); onExpand() }}
          aria-expanded={expanded}
          aria-label={`${expanded ? 'Collapse' : 'Expand'} ${name}`}
        >
          <ChevronRight size={16} strokeWidth={1.75} />
        </button>
      ) : <span className="tree-disclosure" aria-hidden="true" />}
      <span className="tree-mark" aria-hidden="true" />
      <button
        type="button"
        className="tree-name"
        aria-pressed={selected}
        onClick={(event) => { event.stopPropagation(); onSelect() }}
      >
        <span className="tree-name-text">{name || 'Unnamed'}</span>
        <span className="sr-only">, {kind === 'root' ? 'root unit' : kind}</span>
      </button>
      <span className="tree-tags">
        {group.restricted ? <span className="tag">Sensitive</span> : null}
        {entryPoint ? <span className="tag">Entry point</span> : null}
      </span>
      <code className="tree-key">{depth === 0 ? 'root' : group.key}</code>
      {depth > 0 ? (
        <button
          type="button"
          className="tree-handle"
          aria-label={`Reorder ${name}`}
          onClick={(event) => event.stopPropagation()}
          {...sortable.attributes}
          {...sortable.listeners}
        >
          <GripVertical size={16} strokeWidth={1.75} />
        </button>
      ) : <span className="tree-handle" aria-hidden="true" />}
    </li>
  )
}

export function Structure() {
  const { project, selectedGroup, selectGroup, updateProject } = useStudioStructure()
  const { bundle } = project
  const containers = () => bundle.manifest.groups
    .filter((group) => group.kind === 'container')
    .map((group) => group.key)
  const expanded = useStateSet(containers())
  const items = useMemo(() => flattenTree(bundle.manifest.groups, expanded.value), [bundle.manifest.groups, expanded.value])
  const entryPoints = useMemo(() => new Set(customerEntryPoints(bundle)), [bundle])
  const unitCount = bundle.manifest.groups.filter((group) => group.kind === 'container').length
  const serviceCount = bundle.manifest.groups.length - unitCount
  const flat = project.target_schema_version === '1.0'
  const prefix = bundle.manifest.managed_prefix
  const allExpanded = containers().every((key) => expanded.value.has(key))
  useEffect(() => {
    expanded.replace(containers())
  }, [project.id])
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )
  const add = (kind: 'container' | 'leaf') => {
    const result = addGroup(project, kind, selectedGroup)
    if (!result.key) return
    updateProject(result.project, result.key)
    if (kind === 'container') expanded.add(result.key)
  }
  const dragEnd = (event: DragEndEvent) => {
    if (event.over && event.active.id !== event.over.id) {
      updateProject(
        reorderGroup(project, String(event.active.id), String(event.over.id)),
      )
    }
  }
  return (
    <section className="structure-screen">
      <PageHeader
        title="Service structure"
        description="Draw the institution as a tree. Units group the organization; only services carry tickets, queues and access roles."
      />
      <div className="toolbar">
        <button className="button" type="button" disabled={flat} onClick={() => add('container')} aria-describedby={flat ? 'flat-schema-hint' : undefined}>
          <Plus size={16} strokeWidth={1.75} aria-hidden="true" /> Add unit
        </button>
        <button className="button" type="button" onClick={() => add('leaf')}>
          <Plus size={16} strokeWidth={1.75} aria-hidden="true" /> Add service
        </button>
        <button
          className="text-button toolbar-end"
          type="button"
          onClick={() => expanded.replace(allExpanded ? [] : containers())}
        >
          {allExpanded ? 'Collapse all' : 'Expand all'}
        </button>
      </div>
      {flat ? <p className="notice" id="flat-schema-hint">Schema 1.0 keeps services in a flat list under one root. Switch the project to schema 1.1 on the Start sheet to nest units.</p> : null}
      <SectionHeading id="tree-heading" aside={<span className="caption section-count">{unitCount} {unitCount === 1 ? 'unit' : 'units'} · {serviceCount} {serviceCount === 1 ? 'service' : 'services'}</span>}>Tree</SectionHeading>
      <DndContext sensors={sensors} onDragEnd={dragEnd}>
        <SortableContext items={items.map((item) => item.group.key)} strategy={verticalListSortingStrategy}>
          <ul className="tree" aria-labelledby="tree-heading">
            {items.map((item) => (
              <SortableTreeRow
                item={item}
                name={item.group.name.startsWith(prefix) ? item.group.name.slice(prefix.length).trim() : item.group.name.replace(/^.*? · /, '')}
                selected={item.group.key === selectedGroup}
                expanded={expanded.value.has(item.group.key)}
                entryPoint={entryPoints.has(item.group.key)}
                onSelect={() => selectGroup(item.group.key)}
                onExpand={() => expanded.toggle(item.group.key)}
                key={item.group.key}
              />
            ))}
          </ul>
        </SortableContext>
      </DndContext>
    </section>
  )
}
