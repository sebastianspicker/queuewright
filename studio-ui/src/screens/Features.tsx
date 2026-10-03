import {
  Check,
  RotateCcw,
  Search,
} from 'lucide-react'
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
  return (
    <section className="features-screen">
      <PageHeader
        title="Choose the capabilities you need"
        description="Enable only the workflows your teams will use. Dependencies are added automatically and remain inside your managed structure."
      />
      {catalogError ? <p className="notice">{catalogError}</p> : null}
      <div className="feature-filters">
        <label className="search-field">
          <Search size={19} />
          <span className="sr-only">Find a feature</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Find a feature"
          />
        </label>
        <select
          value={category}
          onChange={(event) => setCategory(event.target.value)}
          aria-label="Feature category"
        >
          <option>All categories</option>
          {[...new Set(catalog.map((feature) => feature.category))].map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
        <button className="text-button" type="button" onClick={() => updateProject(resetFeatures(project, catalog))}>
          <RotateCcw size={16} /> Reset to safe baseline
        </button>
      </div>
      <div className="feature-catalog">
        {groupFeatures(visible).map(([group, features]) => (
          <div className="feature-group" key={group}>
            <SectionHeading>{group}</SectionHeading>
            {features.map((feature) => {
              const enabled = bundle.feature_state[feature.id].enabled
              return (
                <div
                  className={selectedFeature === feature.id ? 'feature-row selected' : 'feature-row'}
                  onClick={() => selectFeature(feature.id)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      selectFeature(feature.id)
                    }
                  }}
                  role="group"
                  aria-label={`${feature.name} capability`}
                  tabIndex={0}
                  key={feature.id}
                >
                  <label className="check-control" onClick={(event) => event.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={enabled}
                      disabled={feature.locked}
                      onChange={(event) => updateProject(toggleFeature(project, feature.id, event.target.checked, catalog))}
                      aria-label={feature.name}
                    />
                    <span><Check size={15} /></span>
                  </label>
                  <strong>{feature.name}</strong>
                  <p>{feature.description}</p>
                  <em>{enabled ? 'Enabled' : 'Not selected'}</em>
                </div>
              )
            })}
          </div>
        ))}
        {!visible.length ? (
          <EmptyState title="No capabilities found">
            Try a different search term or choose another category.
          </EmptyState>
        ) : null}
      </div>
    </section>
  )
}
