import type { StudioProject } from '../types'

function replacementTag(project: StudioProject, removedTags: Set<string>): string | undefined {
  const retainedTags = project.manifest.tags.filter((tag) => !removedTags.has(tag))
  return retainedTags.find((tag) => tag.endsWith('/uat')) ?? retainedTags[0]
}

export function replaceRemovedTags(project: StudioProject, removedTags: Set<string>): void {
  const fallbackTag = replacementTag(project, removedTags)
  for (const scenario of project.profile.uat.scenarios) {
    if (!Array.isArray(scenario.expected_tags)) continue
    const remaining = scenario.expected_tags.filter(
      (tag): tag is string => typeof tag === 'string' && !removedTags.has(tag),
    )
    if (remaining.length === 0 && fallbackTag) remaining.push(fallbackTag)
    scenario.expected_tags = remaining
  }
}
