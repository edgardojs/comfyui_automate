import { useState, useEffect, useCallback } from 'react'
import { fetchAttributes } from '../api/client'

/**
 * AttributePanel — Character attribute selection UI.
 *
 * Renders a dropdown + lock toggle for each attribute category.
 * Fetches the attribute library from the API on mount.
 */
function AttributePanel({
  attributes,
  lockedFields,
  onAttributeChange,
  onLockToggle,
  onRandomizeAll,
  onClearAll,
}) {
  const [categories, setCategories] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [retryKey, setRetryKey] = useState(0)

  const handleRetry = useCallback(() => {
    setLoading(true)
    setError(null)
    setRetryKey(k => k + 1)
  }, [])

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        setError(null)
        const data = await fetchAttributes()
        if (!cancelled) setCategories(data.categories || [])
      } catch (err) {
        if (!cancelled) setError(err.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [retryKey])

  if (loading) {
    return (
      <div className="rounded-lg border border-gray-800 bg-gray-900 p-5">
        <h2 className="mb-4 text-lg font-semibold text-white">Character Attributes</h2>
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-9 rounded bg-gray-800 animate-pulse" />
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-900 bg-gray-900 p-5">
        <h2 className="mb-2 text-lg font-semibold text-white">Character Attributes</h2>
        <p className="text-sm text-red-400">Failed to load attributes: {error}</p>
        <button
          onClick={handleRetry}
          className="mt-3 rounded-md bg-red-800 px-3 py-1.5 text-xs font-medium text-red-300 hover:bg-red-700 cursor-pointer"
        >
          Retry
        </button>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-5">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">Character Attributes</h2>
        <div className="flex gap-2">
          <button
            onClick={onRandomizeAll}
            className="rounded-md bg-gray-700 px-2.5 py-1 text-xs font-medium text-gray-300 hover:bg-gray-600 hover:text-white transition-colors cursor-pointer"
            title="Randomize all attributes"
          >
            🎲 Randomize
          </button>
          <button
            onClick={onClearAll}
            className="rounded-md bg-gray-700 px-2.5 py-1 text-xs font-medium text-gray-300 hover:bg-gray-600 hover:text-white transition-colors cursor-pointer"
            title="Clear all selections"
          >
            ✕ Clear
          </button>
        </div>
      </div>

      <div className="space-y-3">
        {categories.map(category => {
          const isLocked = lockedFields.includes(category.id)
          const selectedValue = attributes[category.id] || ''

          return (
            <div key={category.id}>
              <label className="mb-1 block text-xs font-medium text-gray-400 uppercase tracking-wider">
                {category.label}
              </label>
              <div className="flex gap-2">
                <select
                  value={selectedValue}
                  onChange={e => onAttributeChange(category.id, e.target.value)}
                  className="flex-1 rounded-md border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm text-gray-200 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                >
                  <option value="">— Random —</option>
                  {category.attributes.map(attr => (
                    <option key={attr.id} value={attr.id}>
                      {attr.label}
                    </option>
                  ))}
                </select>
                <button
                  onClick={() => onLockToggle(category.id)}
                  className={`rounded-md px-2 py-1.5 text-sm transition-colors cursor-pointer
                    ${isLocked
                      ? 'bg-amber-600/20 text-amber-400 border border-amber-600'
                      : 'bg-gray-800 text-gray-500 border border-gray-700 hover:text-gray-300'
                    }`}
                  title={isLocked ? 'Unlock this attribute' : 'Lock this attribute across variations'}
                  aria-label={isLocked ? 'Unlock this attribute' : 'Lock this attribute across variations'}
                >
                  {isLocked ? '🔒' : '🔓'}
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default AttributePanel