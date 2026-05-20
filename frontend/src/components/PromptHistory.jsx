import { useState, useEffect, useCallback, useRef } from 'react'
import { fetchHistory, favoriteHistoryItem } from '../api/client'

/**
 * PromptHistory — View recent prompt generations with favorite toggling.
 *
 * Props:
 * - onCopy: callback to copy prompt text
 * - showToast: callback to show a toast notification
 */
function PromptHistory({ onCopy, showToast }) {
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [retryKey, setRetryKey] = useState(0)
  const [expandedId, setExpandedId] = useState(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const loadingMoreRef = useRef(false)
  const offsetRef = useRef(0)

  const handleRetry = useCallback(() => {
    setLoading(true)
    setError(null)
    setItems([])
    offsetRef.current = 0
    setRetryKey(k => k + 1)
  }, [])

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        setError(null)
        const data = await fetchHistory({ limit: 20, offset: 0 })
        if (!cancelled) {
          setItems(data.items || [])
          setTotal(data.total || 0)
          offsetRef.current = (data.items || []).length
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

  const handleLoadMore = useCallback(async () => {
    if (loadingMoreRef.current) return
    setLoadingMore(true)
    loadingMoreRef.current = true
    try {
      const data = await fetchHistory({ limit: 20, offset: offsetRef.current })
      setItems(prev => [...prev, ...(data.items || [])])
      offsetRef.current += (data.items || []).length
    } catch (err) {
      showToast(`Failed to load more: ${err.message}`)
    } finally {
      setLoadingMore(false)
      loadingMoreRef.current = false
    }
  }, [showToast])

  const handleFavorite = useCallback(async (generationId) => {
    try {
      const result = await favoriteHistoryItem(generationId)
      setItems(prev =>
        prev.map(item =>
          item.generation_id === generationId
            ? { ...item, is_favorite: result.is_favorite }
            : item
        )
      )
      showToast(result.is_favorite ? '⭐ Added to favorites' : 'Removed from favorites')
    } catch (err) {
      showToast(`Failed to toggle favorite: ${err.message}`)
    }
  }, [showToast])

  const toggleExpand = useCallback((generationId) => {
    setExpandedId(prev => prev === generationId ? null : generationId)
  }, [])

  const formatTime = useCallback((isoString) => {
    if (!isoString) return 'Unknown'
    try {
      const date = new Date(isoString)
      return date.toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    } catch {
      return isoString
    }
  }, [])

  const truncate = useCallback((str, maxLen = 80) => {
    if (!str || str.length <= maxLen) return str
    return str.slice(0, maxLen).trim() + '…'
  }, [])

  // --- Loading state ---
  if (loading) {
    return (
      <div className="rounded-lg border border-gray-800 bg-gray-900 p-5">
        <h2 className="mb-4 text-lg font-semibold text-white">Prompt History</h2>
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-16 rounded bg-gray-800 animate-pulse" />
          ))}
        </div>
      </div>
    )
  }

  // --- Error state ---
  if (error) {
    return (
      <div className="rounded-lg border border-red-900 bg-gray-900 p-5">
        <h2 className="mb-2 text-lg font-semibold text-white">Prompt History</h2>
        <p className="text-sm text-red-400">Failed to load history: {error}</p>
        <button
          onClick={handleRetry}
          className="mt-3 rounded-md bg-red-800 px-3 py-1.5 text-xs font-medium text-red-300 hover:bg-red-700 cursor-pointer"
        >
          Retry
        </button>
      </div>
    )
  }

  // --- Empty state ---
  if (items.length === 0) {
    return (
      <div className="rounded-lg border border-gray-800 bg-gray-900 p-5">
        <h2 className="mb-4 text-lg font-semibold text-white">Prompt History</h2>
        <div className="py-8 text-center">
          <span className="text-3xl">📜</span>
          <h3 className="mt-3 text-sm font-semibold text-gray-400">No history yet</h3>
          <p className="mt-1 text-xs text-gray-600">
            Generated prompts will appear here.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-5">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">Prompt History</h2>
        <span className="text-xs text-gray-500">
          {total} {total === 1 ? 'entry' : 'entries'}
        </span>
      </div>

      <div className="space-y-2">
        {items.map(item => {
          const isExpanded = expandedId === item.generation_id
          const classAttr = item.attributes?.classes || item.attributes?.class
          const styleAttr = item.attributes?.styles || item.attributes?.style

          return (
            <div
              key={item.generation_id}
              className={`rounded-md border transition-colors cursor-pointer
                ${isExpanded
                  ? 'border-gray-600 bg-gray-800'
                  : 'border-gray-700 bg-gray-800/50 hover:border-gray-600'
                }`}
            >
              {/* Summary row — always visible */}
              <div
                role="button"
                tabIndex={0}
                aria-expanded={isExpanded}
                onClick={() => toggleExpand(item.generation_id)}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleExpand(item.generation_id) } }}
                className="w-full px-3 py-2.5 cursor-pointer"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      {/* Favorite star */}
                      <button
                        onClick={e => { e.stopPropagation(); handleFavorite(item.generation_id) }}
                        className={`text-sm flex-shrink-0 cursor-pointer transition-transform hover:scale-125
                          ${item.is_favorite ? 'text-amber-400' : 'text-gray-600 hover:text-gray-400'}`}
                        title={item.is_favorite ? 'Remove from favorites' : 'Add to favorites'}
                        aria-label={item.is_favorite ? 'Remove from favorites' : 'Add to favorites'}
                      >
                        {item.is_favorite ? '⭐' : '☆'}
                      </button>

                      {/* Attribute badges */}
                      {classAttr && (
                        <span className="inline-flex items-center rounded bg-indigo-600/20 px-1.5 py-0.5 text-[10px] font-medium text-indigo-300 border border-indigo-600/30">
                          {classAttr}
                        </span>
                      )}
                      {styleAttr && (
                        <span className="inline-flex items-center rounded bg-emerald-600/20 px-1.5 py-0.5 text-[10px] font-medium text-emerald-300 border border-emerald-600/30">
                          {styleAttr}
                        </span>
                      )}
                    </div>

                    {/* Prompt preview */}
                    <p className="mt-1 text-xs text-gray-400 truncate">
                      {truncate(item.positive_prompt)}
                    </p>
                  </div>

                  {/* Timestamp */}
                  <span className="text-[10px] text-gray-500 flex-shrink-0 whitespace-nowrap">
                    {formatTime(item.created_at)}
                  </span>
                </div>
              </div>

              {/* Expanded details */}
              {isExpanded && (
                <div className="border-t border-gray-700 px-3 py-3 space-y-3">
                  {/* Positive prompt */}
                  <div>
                    <label className="mb-1 block text-xs font-medium text-emerald-400 uppercase tracking-wider">
                      Positive Prompt
                    </label>
                    <div className="rounded-md bg-gray-900/50 border border-gray-700 p-2.5 text-xs text-gray-200 leading-relaxed select-all">
                      {item.positive_prompt}
                    </div>
                    <button
                      onClick={() => onCopy(item.positive_prompt, 'Positive')}
                      className="mt-1.5 rounded bg-gray-700 px-2 py-0.5 text-[10px] font-medium text-gray-400 hover:bg-gray-600 hover:text-white cursor-pointer transition-colors"
                    >
                      📋 Copy Positive
                    </button>
                  </div>

                  {/* Negative prompt */}
                  <div>
                    <label className="mb-1 block text-xs font-medium text-red-400 uppercase tracking-wider">
                      Negative Prompt
                    </label>
                    <div className="rounded-md bg-gray-900/50 border border-gray-700 p-2.5 text-xs text-gray-200 leading-relaxed select-all">
                      {item.negative_prompt}
                    </div>
                    <button
                      onClick={() => onCopy(item.negative_prompt, 'Negative')}
                      className="mt-1.5 rounded bg-gray-700 px-2 py-0.5 text-[10px] font-medium text-gray-400 hover:bg-gray-600 hover:text-white cursor-pointer transition-colors"
                    >
                      📋 Copy Negative
                    </button>
                  </div>

                  {/* Copy both */}
                  <button
                    onClick={() => onCopy(
                      `Positive: ${item.positive_prompt}\n\nNegative: ${item.negative_prompt}`,
                      'Both'
                    )}
                    className="rounded bg-indigo-600/20 px-2.5 py-1 text-[10px] font-medium text-indigo-300 hover:bg-indigo-600/30 cursor-pointer border border-indigo-600/40 transition-colors"
                  >
                    📋 Copy Both
                  </button>

                  {/* Resolved attributes */}
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Attributes
                    </label>
                    <div className="flex flex-wrap gap-1">
                      {Object.entries(item.attributes || {}).map(([key, val]) => (
                        <span
                          key={key}
                          className="inline-flex items-center rounded-full bg-gray-800 px-2 py-0.5 text-[10px] text-gray-400 border border-gray-700"
                        >
                          <span className="text-gray-500 mr-1">{key}:</span>
                          {val}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Generation ID */}
                  <div className="text-[10px] text-gray-600 font-mono">
                    ID: {item.generation_id}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Load More button */}
      {items.length < total && (
        <div className="mt-4 text-center">
          <button
            onClick={handleLoadMore}
            disabled={loadingMore}
            className="rounded-md bg-gray-800 px-4 py-2 text-xs font-medium text-gray-300 hover:bg-gray-700 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer transition-colors border border-gray-700"
          >
            {loadingMore ? (
              <span className="flex items-center gap-2">
                <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                Loading…
              </span>
            ) : (
              `Load More (${total - items.length} remaining)`
            )}
          </button>
        </div>
      )}
    </div>
  )
}

export default PromptHistory