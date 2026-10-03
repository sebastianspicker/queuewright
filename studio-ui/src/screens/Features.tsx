import { RotateCcw, Search } from 'lucide-react'
import { resetFeatures, toggleFeature } from '../editor/model'
import { useStudio } from '../editor/context'
import { EmptyState, PageHeader, SectionHeading } from '../components/ui'
import { useState } from 'react'
import type { FeatureDefinition } from '../contracts'

export function groupFeatures(features: FeatureDefinition[]): Array<[string, FeatureDefinition[]]> {
  const groups = new Map<string, FeatureDefinition[]>()
  for (const feature of features) {
    groups.set(feature.category, [...(groups.get(feature.category) ?? []), feature])
  }
  return [...groups]
}

export function Features() {
  const {
    project,
    catalog,
    selectedFeature,
    catalogError,
    selectFeature,
    updateProject,
  } = useStudio()
  const { bundle } = project
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('All categories')
  const visible = catalog.filter((feature) =>
    (category === 'All categories' || feature.category === category)
    && `${feature.name} ${feature.description}`.toLowerCase().includes(query.toLowerCase()),
  )
  const enabledCount = catalog.filter((feature) => bundle.feature_state[feature.id].enabled).length
  return (
    <section className="features-screen">
      <PageHeader
        title="Policies and capabilities"
        description="Switch on only the workflows your teams will use. Anything a capability depends on is enabled with it and stays inside the managed structure."
      />
      {catalogError ? <p className="notice" role="status"><span>{catalogError}</span></p> : null}
      <div className="filters" role="search">
        <label className="search-field">
          <Search size={16} strokeWidth={1.75} aria-hidden="true" />
          <span className="sr-only">Find a capability</span>
          <input
            className="input"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Find a capability"
          />
        </label>
        <select
          className="select"
          value={category}
          onChange={(event) => setCategory(event.target.value)}
          aria-label="Capability category"
        >
          <option>All categories</option>
          {[...new Set(catalog.map((feature) => feature.category))].map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
        <button className="text-button" type="button" onClick={() => updateProject(resetFeatures(project, catalog))}>
          <RotateCcw size={14} strokeWidth={1.75} aria-hidden="true" /> Reset to safe baseline
        </button>
      </div>
      <p className="filters-summary caption" aria-live="polite">{enabledCount} of {catalog.length} enabled{visible.length !== catalog.length ? ` · showing ${visible.length}` : ''}</p>
      <div className="feature-catalog">
        {groupFeatures(visible).map(([group, features]) => (
          <section className="feature-group" key={group} aria-label={group}>
            <SectionHeading>{group}</SectionHeading>
            <ul>
              {features.map((feature) => {
                const enabled = bundle.feature_state[feature.id].enabled
                const selected = selectedFeature === feature.id
                return (
                  <li className={selected ? 'feature-row is-selected' : 'feature-row'} key={feature.id} onClick={() => selectFeature(feature.id)}>
                    <input
                      className="check"
                      type="checkbox"
                      checked={enabled}
                      disabled={feature.locked}
                      onClick={(event) => event.stopPropagation()}
                      onChange={(event) => updateProject(toggleFeature(project, feature.id, event.target.checked, catalog))}
                      aria-label={`Enable ${feature.name}`}
                    />
                    <button className="feature-name" type="button" aria-pressed={selected} onClick={(event) => { event.stopPropagation(); selectFeature(feature.id) }}>
                      <strong>{feature.name}</strong>
                      <span>{feature.description}</span>
                    </button>
                    <span className={feature.locked ? 'feature-state is-locked' : enabled ? 'feature-state is-on' : 'feature-state'}>
                      {feature.locked ? 'Baseline' : enabled ? 'On' : 'Off'}
                    </span>
                  </li>
                )
              })}
            </ul>
          </section>
        ))}
        {!visible.length ? (
          <EmptyState title="No capability matches">
            Try another word, or show all categories.
          </EmptyState>
        ) : null}
      </div>
    </section>
  )
}
