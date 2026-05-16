import { useState, useEffect, useCallback } from 'react'
import { fetchTemplates, fetchNegativeProfiles } from '../api/client'

const VARIATION_OPTIONS = [1, 5, 10, 25]

/**
 * PromptOptions — Configuration panel for prompt generation.
 *
 * Contains variation count selector, template selector,
 * negative profile selector, and the generate button.
 */
function PromptOptions({
  variationCount,
  templateId,
  negativeProfileId,
  onVariationCountChange,
  onTemplateIdChange,
  onNegativeProfileIdChange,
  onGenerate,
  isGenerating,
}) {
  const [templates, setTemplates] = useState([])
  const [profiles, setProfiles] = useState([])
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
        const results = await Promise.allSettled([
          fetchTemplates(),
          fetchNegativeProfiles(),
        ])
        if (!cancelled) {
          const tmplResult = results[0]
          const profResult = results[1]

          // Use partial data if at least one request succeeded
          if (tmplResult.status === 'fulfilled') {
            setTemplates(tmplResult.value.templates || [])
          }
          if (profResult.status === 'fulfilled') {
            setProfiles(profResult.value.profiles || [])
          }

          // Show error only for requests that failed
          const errors = []
          if (tmplResult.status === 'rejected') {
            errors.push(`Templates: ${tmplResult.reason?.message || 'Failed to load'}`)
          }
          if (profResult.status === 'rejected') {
            errors.push(`Profiles: ${profResult.reason?.message || 'Failed to load'}`)
          }
          if (errors.length > 0) {
            setError(errors.join('; '))
          }
        }
      } catch (err) {
        if (!cancelled) setError(err.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [retryKey])

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-5">
      <h2 className="mb-4 text-lg font-semibold text-white">Prompt Options</h2>

      {error && (
        <div className="mb-4 flex items-center gap-2 rounded-md border border-red-900 bg-red-900/20 px-3 py-2 text-sm text-red-400">
          <span>⚠️</span>
          <span className="flex-1">Failed to load options: {error}</span>
          <button
            onClick={handleRetry}
            className="rounded bg-red-800 px-2 py-0.5 text-xs font-medium text-red-300 hover:bg-red-700 cursor-pointer"
          >
            Retry
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {/* Variation Count */}
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-400 uppercase tracking-wider">
            Variations
          </label>
          <div className="flex gap-1.5">
            {VARIATION_OPTIONS.map(count => (
              <button
                key={count}
                onClick={() => onVariationCountChange(count)}
                className={`flex-1 rounded-md px-2 py-1.5 text-sm font-medium transition-colors cursor-pointer
                  ${variationCount === count
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white border border-gray-700'
                  }`}
              >
                {count}
              </button>
            ))}
          </div>
        </div>

        {/* Template Selector */}
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-400 uppercase tracking-wider">
            Template
          </label>
          <select
            value={templateId}
            onChange={e => onTemplateIdChange(e.target.value)}
            disabled={loading}
            className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm text-gray-200 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
          >
            {templates.map(t => (
              <option key={t.id} value={t.id}>{t.label}</option>
            ))}
          </select>
        </div>

        {/* Negative Profile Selector */}
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-400 uppercase tracking-wider">
            Negative Profile
          </label>
          <select
            value={negativeProfileId}
            onChange={e => onNegativeProfileIdChange(e.target.value)}
            disabled={loading}
            className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm text-gray-200 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
          >
            {profiles.map(p => (
              <option key={p.id} value={p.id}>{p.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Generate Button */}
      <div className="mt-4">
        <button
          onClick={onGenerate}
          disabled={isGenerating}
          className="w-full rounded-md bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-gray-900 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
        >
          {isGenerating ? (
            <span className="flex items-center justify-center gap-2">
              <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              Generating…
            </span>
          ) : (
            <span className="flex items-center justify-center gap-2">
              🎲 Generate Prompts
            </span>
          )}
        </button>
      </div>
    </div>
  )
}

export default PromptOptions