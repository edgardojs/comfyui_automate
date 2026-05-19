import { useState, useEffect, useCallback } from 'react'
import { fetchAttributes, fetchLoRAJobs } from '../api/client'

/**
 * AttributePanel — Character attribute selection UI.
 *
 * Renders a dropdown + lock toggle for each attribute category.
 * Fetches the attribute library from the API on mount.
 * Includes a LoRA selector dropdown that fetches completed LoRA jobs
 * and auto-fills the trigger token when one is selected.
 */
function AttributePanel({
  attributes,
  lockedFields,
  onAttributeChange,
  onLockToggle,
  onRandomizeAll,
  onClearAll,
  loraSelection,
  onLoRAChange,
}) {
  const [categories, setCategories] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [retryKey, setRetryKey] = useState(0)

  // LoRA dropdown state
  const [completedLoras, setCompletedLoras] = useState([])
  const [loraLoading, setLoraLoading] = useState(true)
  const [loraError, setLoraError] = useState(null)

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

  // Fetch completed LoRA jobs
  useEffect(() => {
    let cancelled = false
    async function loadLoras() {
      try {
        setLoraError(null)
        const jobs = await fetchLoRAJobs({ status_filter: 'completed' })
        if (!cancelled) setCompletedLoras(jobs || [])
      } catch (err) {
        if (!cancelled) setLoraError(err.message)
      } finally {
        if (!cancelled) setLoraLoading(false)
      }
    }
    loadLoras()
    return () => { cancelled = true }
  }, [])

  const handleLoRASelect = useCallback((e) => {
    const jobId = e.target.value
    if (!jobId) {
      onLoRAChange?.(null)
      return
    }
    const job = completedLoras.find(j => j.job_id === jobId)
    if (job) {
      onLoRAChange?.({
        jobId: job.job_id,
        characterId: job.character_id,
        characterName: job.character_name || '',
        triggerToken: job.trigger_token || '',
        recommendedStrength: job.lora_strength || 1.0,
      })
    }
  }, [completedLoras, onLoRAChange])

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

      {/* LoRA Selector */}
      <div className="mb-4 pb-4 border-b border-gray-800">
        <label className="mb-1 block text-xs font-medium text-gray-400 uppercase tracking-wider">
          LoRA Model
        </label>
        {loraLoading ? (
          <div className="h-9 rounded bg-gray-800 animate-pulse" />
        ) : loraError ? (
          <p className="text-xs text-red-400">Failed to load LoRAs: {loraError}</p>
        ) : completedLoras.length === 0 ? (
          <p className="text-xs text-gray-500 italic">No trained LoRAs available</p>
        ) : (
          <select
            value={loraSelection?.jobId || ''}
            onChange={handleLoRASelect}
            className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm text-gray-200 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="">— None —</option>
            {completedLoras.map(job => (
              <option key={job.job_id} value={job.job_id}>
                {job.character_name || job.character_id} — {job.trigger_token || job.job_id}
              </option>
            ))}
          </select>
        )}
        {loraSelection && (
          <div className="mt-2 space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500">Trigger Token:</span>
              <code className="rounded bg-gray-800 px-1.5 py-0.5 text-xs text-indigo-300 font-mono">
                {loraSelection.triggerToken}
              </code>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500">Recommended Strength:</span>
              <span className="text-xs text-amber-400 font-medium">
                {loraSelection.recommendedStrength}
              </span>
            </div>
          </div>
        )}
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
                  {category.attributes?.map(attr => (
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