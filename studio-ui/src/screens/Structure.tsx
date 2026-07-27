import {
  DndContext,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import {
  ChevronDown,
  ChevronRight,
  Expand,
  Folder,
  GripVertical,
  Plus,
  Tag,
  University,
} from 'lucide-react'
import { addGroup, reorderGroup } from '../project-model'
import { useStudio } from '../studio-state'
import { PageHeader } from '../ui'
import { useStateSet } from './useStateSet'
import { useEffect } from 'react'
import type { CSSProperties, KeyboardEvent } from 'react'
import type { GroupResource } from '../types'

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
  const output: TreeItem[] = []
  const visit = (group: GroupResource, depth: number) => {
    output.push({ group, depth })
    if (group.kind === 'container' && expanded.has(group.key)) {
      for (const child of groups.filter((item) => item.parent === group.key)) {
        visit(child, depth + 1)
      }
    }
  }
  visit(root, 0)
  return output
}

function SortableTreeRow({
  item,
  selected,
  expanded,
  onSelect,
  onExpand,
}: {
  item: TreeItem
  selected: boolean
  expanded: boolean
  onSelect(): void
  onExpand(): void
}) {
  const sortable = useSortable({ id: item.group.key })
  const style = {
    transform: CSS.Transform.toString(sortable.transform),
    transition: sortable.transition,
    '--tree-depth': item.depth,
  } as CSSProperties
  const isContainer = item.group.kind === 'container'
  const GroupIcon = item.depth === 0 ? University : isContainer ? Folder : Tag
  const keyboardSelect = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      onSelect()
    }
  }
  const badge = item.group.kind === 'leaf'
    ? 'Service'
    : item.depth === 0
      ? 'Root unit'
      : 'Unit'
  return (
    <div
      ref={sortable.setNodeRef}
      style={style}
      className={selected ? 'tree-row selected' : 'tree-row'}
      data-depth={item.depth}
      {...sortable.attributes}
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={keyboardSelect}
    >
      <span className="tree-indent" />
      {isContainer ? (
        <button
          type="button"
          className="disclosure"
          onClick={(event) => { event.stopPropagation(); onExpand() }}
          aria-label={`${expanded ? 'Collapse' : 'Expand'} ${item.group.name}`}
        >
          {expanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
        </button>
      ) : <span className="disclosure-spacer" />}
      {item.depth > 0 ? (
        <button
          type="button"
          className="drag-handle"
          aria-label={`Reorder ${item.group.name}`}
          onClick={(event) => event.stopPropagation()}
          {...sortable.listeners}
        >
          <GripVertical size={18} />
        </button>
      ) : <span className="drag-spacer" />}
      <GroupIcon size={21} strokeWidth={1.6} />
      <strong>{item.group.name.replace(/^.*? · /, '')}</strong>
      <span className={item.group.kind === 'leaf' ? 'service-badge' : 'unit-badge'}>
        {badge}
      </span>
    </div>
  )
}

export function Structure() {
  const { project, selectedGroup, dispatch, updateProject } = useStudio()
  const expanded = useStateSet(
    project.manifest.groups
      .filter((group) => group.kind === 'container')
      .map((group) => group.key),
  )
  const items = flattenTree(project.manifest.groups, expanded.value)
  const unitCount = project.manifest.groups.filter((group) => group.kind === 'container').length
  const serviceCount = project.manifest.groups.filter((group) => group.kind === 'leaf').length
  useEffect(() => {
    expanded.replace(
      project.manifest.groups
        .filter((group) => group.kind === 'container')
        .map((group) => group.key),
    )
  }, [project.id])
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
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
        kicker="Step 03 · Service topology"
        title="Build your service structure"
        description="Arrange departments and services. Only ticket-bearing services receive queues and access roles; units organize the tree."
      />
      <div className="toolbar">
        <button
          className="button primary"
          type="button"
          disabled={project.target_schema_version === '1.0'}
          title={project.target_schema_version === '1.0' ? 'Upgrade this project to schema 1.1 to nest units.' : undefined}
          onClick={() => add('container')}
        >
          <Plus size={19} /> Add unit
        </button>
        <button className="button quiet" type="button" onClick={() => add('leaf')}>
          <Plus size={19} /> Add service
        </button>
        <button
          className="button quiet"
          type="button"
          onClick={() => expanded.replace(
            project.manifest.groups
              .filter((group) => group.kind === 'container')
              .map((group) => group.key),
          )}
        >
          <Expand size={18} /> Expand all
        </button>
        <div className="toolbar-spacer" />
        <span className="count-pill">
          {unitCount} {unitCount === 1 ? 'unit' : 'units'} · {serviceCount}{' '}
          {serviceCount === 1 ? 'service' : 'services'}
        </span>
      </div>
      <DndContext sensors={sensors} onDragEnd={dragEnd}>
        <SortableContext items={items.map((item) => item.group.key)} strategy={verticalListSortingStrategy}>
          <div className="tree" aria-label="Service structure">
            {items.map((item) => (
              <SortableTreeRow
                item={item}
                selected={item.group.key === selectedGroup}
                expanded={expanded.value.has(item.group.key)}
                onSelect={() => dispatch({ type: 'group:select', id: item.group.key })}
                onExpand={() => expanded.toggle(item.group.key)}
                key={item.group.key}
              />
            ))}
          </div>
        </SortableContext>
      </DndContext>
    </section>
  )
}
