import { useState, useEffect, useCallback } from 'react'
import {
  fetchReferences,
  generateCaptions,
  updateCaption,
  getReferenceFileUrl,
} from '../api/client'

/**
 * CaptionEditor — Grid view of accepted reference images with inline caption editing.
 *
 * Props:
 * - characterId: the character profile ID
 * - showToast: callback to show a toast notification
 *
 * Features:
 * - Grid view of accepted reference images with their captions
 * - Inline caption editing (click to edit)
 * - "Auto-Generate All Captions" button
 * - Caption style selector (detailed / simple)
 * - Per-image angle tag display
 * - Visual indicator for images missing captions
 */

const CAPTION_STYLE_OPTIONS = [
  { value: 'detailed', label: 'Detailed', description: 'Full tag string with all character attributes' },
  { value: 'simple', label: 'Simple', description: 'Short caption with key attributes only' },
]

function CaptionEditor({ characterId, showToast }) {
  const [references, setReferences] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [generating, setGenerating] = useState(false)
  const [captionStyle, setCaptionStyle] = useState('detailed')

  // Inline editing state
  const [editingImageId, setEditingImageId] = useState(null)
  const [editCaption, setEditCaption] = useState('')

  // Load only accepted references
  const loadReferences = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await fetchReferences(characterId, 'accepted')
      setReferences(data || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [characterId])

  useEffect(() => {
    if (characterId) loadReferences()
  }, [characterId, loadReferences])

  // --- Auto-generate captions ---
  const handleGenerateCaptions = useCallback(async () => {
    // Confirm before overwriting existing captions
    const withCaption = references.filter(r => r.caption && r.caption.trim()).length
    if (withCaption > 0) {
      const msg = `This will overwrite ${withCaption} existing caption${withCaption !== 1 ? 's' : ''}. Continue?`
      if (!window.confirm(msg)) return
    }

    setGenerating(true)
    try {
      const result = await generateCaptions(characterId, captionStyle)
      showToast(`✨ Generated ${result.count} caption(s)`)
      // Update local references with new captions
      setReferences(prev =>
        prev.map(ref => {
          const captionItem = result.captions.find(c => c.image_id === ref.image_id)
          if (captionItem) {
            return { ...ref, caption: captionItem.caption }
          }
          return ref
        })
      )
    } catch (err) {
      showToast(`❌ Caption generation failed: ${err.message}`)
      // Reload references to ensure local state is consistent with server
      await loadReferences()
    } finally {
      setGenerating(false)
    }
  }, [characterId, captionStyle, showToast, loadReferences])

  // --- Inline caption editing ---
  const handleStartEdit = useCallback((ref) => {
    setEditingImageId(ref.image_id)
    setEditCaption(ref.caption || '')
  }, [])

  const handleSaveEdit = useCallback(async () => {
    if (!editingImageId) return
    try {
      const updated = await updateCaption(characterId, editingImageId, editCaption)
      setReferences(prev =>
        prev.map(ref => ref.image_id === editingImageId ? { ...ref, caption: updated.caption } : ref)
      )
      showToast('Caption updated')
      // Only clear edit mode on success
      setEditingImageId(null)
      setEditCaption('')
    } catch (err) {
      showToast(`❌ ${err.message}`)
      // Keep editing active on failure so the user can retry
    }
  }, [characterId, editingImageId, editCaption, showToast])

  const handleCancelEdit = useCallback(() => {
    setEditingImageId(null)
    setEditCaption('')
  }, [])

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSaveEdit()
    } else if (e.key === 'Escape') {
      handleCancelEdit()
    }
  }, [handleSaveEdit, handleCancelEdit])

  // --- Stats ---
  const withCaption = references.filter(r => r.caption && r.caption.trim()).length
  const withoutCaption = references.filter(r => !r.caption || !r.caption.trim()).length

  return (
    <div className="mt-4">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-semibold text-white">Caption Editor</h4>
        <div className="flex items-center gap-2">
          {/* Caption style selector */}
          <select
            value={captionStyle}
            onChange={e => setCaptionStyle(e.target.value)}
            className="bg-gray-800 border border-gray-600 rounded text-xs text-white px-2 py-1"
          >
            {CAPTION_STYLE_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>

          {/* Generate button */}
          <button
            onClick={handleGenerateCaptions}
            disabled={generating || references.length === 0}
            className="px-3 py-1 text-xs bg-emerald-700 hover:bg-emerald-600 text-emerald-100 rounded transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {generating ? (
              <>
                <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-gray-600 border-t-emerald-400 mr-1 align-middle" />
                Generating...
              </>
            ) : (
              '✨ Generate All Captions'
            )}
          </button>
        </div>
      </div>

      {/* Caption stats */}
      {references.length > 0 && (
        <div className="flex gap-3 mb-3 text-xs">
          <span className="bg-gray-800 text-gray-300 px-2 py-0.5 rounded border border-gray-700">
            📝 {withCaption} with caption
          </span>
          <span className={`px-2 py-0.5 rounded border ${
            withoutCaption > 0
              ? 'bg-yellow-900/30 text-yellow-300 border-yellow-700'
              : 'bg-emerald-900/30 text-emerald-300 border-emerald-700'
          }`}>
            {withoutCaption > 0 ? `⚠️ ${withoutCaption} missing caption` : '✅ All captions set'}
          </span>
        </div>
      )}

      {/* Loading / Error */}
      {loading && <p className="text-gray-400 text-sm">Loading images...</p>}
      {error && <p className="text-red-400 text-sm">Error: {error}</p>}

      {/* Empty state */}
      {!loading && references.length === 0 && (
        <p className="text-gray-500 text-sm text-center py-4">
          No accepted reference images. Accept some images first to edit captions.
        </p>
      )}

      {/* Image grid with captions */}
      {!loading && references.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {references.map(ref => {
            const isEditing = editingImageId === ref.image_id
            const hasCaption = ref.caption && ref.caption.trim()

            return (
              <div
                key={ref.image_id}
                className="bg-gray-800 border border-gray-700 rounded-lg overflow-hidden"
              >
                <div className="flex gap-3 p-3">
                  {/* Thumbnail */}
                  <div className="w-20 h-20 flex-shrink-0 bg-gray-900 rounded overflow-hidden">
                    <img
                      src={getReferenceFileUrl(characterId, ref.image_id)}
                      alt={ref.original_filename}
                      className="w-full h-full object-cover"
                      loading="lazy"
                    />
                  </div>

                  {/* Caption area */}
                  <div className="flex-1 min-w-0">
                    {/* Header with filename and angle */}
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs text-gray-400 truncate">{ref.original_filename}</span>
                      {ref.angle && (
                        <span className="text-[10px] bg-gray-700 text-gray-300 px-1.5 py-0.5 rounded">
                          {ref.angle}
                        </span>
                      )}
                      {!hasCaption && !isEditing && (
                        <span className="text-[10px] bg-yellow-900/50 text-yellow-400 px-1.5 py-0.5 rounded">
                          No caption
                        </span>
                      )}
                    </div>

                    {/* Caption text or editor */}
                    {isEditing ? (
                      <div className="space-y-1.5">
                        <textarea
                          value={editCaption}
                          onChange={e => setEditCaption(e.target.value)}
                          onKeyDown={handleKeyDown}
                          rows={3}
                          className="w-full bg-gray-900 border border-gray-600 rounded text-xs text-white px-2 py-1.5 resize-none focus:outline-none focus:border-emerald-500"
                          placeholder="Enter caption..."
                          autoFocus
                        />
                        <div className="flex gap-1.5">
                          <button
                            onClick={handleSaveEdit}
                            className="px-2 py-0.5 text-[10px] bg-emerald-700 hover:bg-emerald-600 text-emerald-100 rounded transition-colors cursor-pointer"
                          >
                            Save
                          </button>
                          <button
                            onClick={handleCancelEdit}
                            className="px-2 py-0.5 text-[10px] bg-gray-700 hover:bg-gray-600 text-gray-300 rounded transition-colors cursor-pointer"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div
                        role="button"
                        tabIndex={0}
                        onClick={() => handleStartEdit(ref)}
                        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleStartEdit(ref) } }}
                        className="cursor-pointer group"
                      >
                        {hasCaption ? (
                          <p className="text-xs text-gray-300 leading-relaxed group-hover:text-emerald-300 transition-colors">
                            {ref.caption}
                          </p>
                        ) : (
                          <p className="text-xs text-gray-500 italic group-hover:text-gray-400 transition-colors">
                            Click to add a caption...
                          </p>
                        )}
                        <span className="text-[10px] text-gray-600 group-hover:text-gray-400 transition-colors">
                          Click to edit
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default CaptionEditor