import { describe, expect, it } from 'vitest'
import type { GroupResource } from '../contracts'
import { flattenTree } from './Structure'

const group = (key: string, parent?: string, kind: 'container' | 'leaf' = 'container'): GroupResource => ({ key, name: key, active: true, kind, ...(parent ? { parent } : {}) })

describe('indexed tree traversal', () => {
  it('preserves source sibling order and depth when descendants precede their parent', () => {
    const groups = [group('second', 'root'), group('nested', 'first', 'leaf'), group('root'), group('first', 'root')]
    expect(flattenTree(groups, new Set(['root', 'first'])).map(({ group: item, depth }) => [item.key, depth])).toEqual([
      ['root', 0], ['second', 1], ['first', 1], ['nested', 2],
    ])
  })
  it('hides collapsed descendants and keeps the rootless fallback', () => {
    const groups = [group('root'), group('child', 'root')]
    expect(flattenTree(groups, new Set()).map(({ group: item }) => item.key)).toEqual(['root'])
    expect(flattenTree(groups.slice(1), new Set())).toEqual([{ group: groups[1], depth: 0 }])
    expect(flattenTree([], new Set())).toEqual([])
  })
})
