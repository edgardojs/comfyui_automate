import { useState, useEffect, useCallback } from 'react'
import { fetchPresets, savePreset, deletePreset } from '../api/client'

/**
 * PresetManager — Save, load, and delete attribute presets.
 *
 * Props:
 * - currentAttributes: the currently selected attributes
 * - currentLockedFields: currently locked fields
 * - currentTemplateId: currently selected template
 * - currentNegativeProfileId: currently selected negative profile
 * - onLoadPreset: callback to apply a preset's settings to the app state
 * - showToast: callback to show a toast notification
 */
function PresetManager({
  currentAttributes,
  currentLockedFields,
  currentTemplateId,
  currentNegativeProfileId,
  onLoadPreset,
  showToast,
}) {
  const [presets, setPresets] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [retryKey, setRetryKey] = useState(0)

  // Save dialog state
  const [showSaveDialog, setShowSaveDialog] = useState(false)
  const [presetName, setPresetName] = useState('')
  const [isSaving, setIsSaving] = useState(false)

  // Delete confirmation state
  const [deleteTarget, setDeleteTarget] = useState(null)

  const handleRetry = useCallback(() => {
    setLoading(true)
    setError(null)
    setRetryKey(k => k + 1)
  }, [])

  // Fetch presets on mount
  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        setError(null)
        const data = await fetchPresets()
        if (!cancelled) setPresets(data || [])
      } catch (err) {
        if (!cancelled) setError(err.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [retryKey])

  // Refresh presets after save/delete
  const refreshPresets = useCallback(async () => {
    try {
      const data = await fetchPresets()
      setPresets(data || [])
    } catch {
      showToast('Failed to refresh preset list')
    }
  }, [showToast])

  // Save a new preset
  const handleSave = useCallback(async () => {
    const name = presetName.trim()
    if (!name) return

    setIsSaving(true)
    try {
      await savePreset({
        name,
        attributes: currentAttributes,
        locked_fields: currentLockedFields,
        positive_template_id: currentTemplateId,
        negative_profile_id: currentNegativeProfileId,
      })
      setShowSaveDialog(false)
      setPresetName('')
      showToast(`Preset "${name}" saved!`)
      await refreshPresets()
    } catch (err) {
      showToast(`Failed to save preset: ${err.message}`)
    } finally {
      setIsSaving(false)
    }
  }, [presetName, currentAttributes, currentLockedFields, currentTemplateId, currentNegativeProfileId, showToast, refreshPresets])

  // Load a preset
  const handleLoad = useCallback((preset) => {
    onLoadPreset({
      attributes: preset.attributes || {},
      lockedFields: preset.locked_fields || [],
      templateId: preset.positive_template_id || 'front_view_sprite',
      negativeProfileId: preset.negative_profile_id || 'general_sprite_cleanup',
    })
    showToast(`Loaded preset "${preset.name}"`)
  }, [onLoadPreset, showToast])

  // Delete a preset
  const handleDelete = useCallback(async (presetId) => {
    try {
      await deletePreset(presetId)
      setDeleteTarget(null)
      showToast('Preset deleted')
      await refreshPresets()
    } catch (err) {
      showToast(`Failed to delete preset: ${err.message}`)
    }
  }, [showToast, refreshPresets])

  // --- Loading state ---
  if (loading) {
    return (
      <div className="rounded-lg border border-gray-800 bg-gray-900 p-5">
        <h2 className="mb-4 text-lg font-semibold text-white">Presets</h2>
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-12 rounded bg-gray-800 animate-pulse" />
          ))}
        </div>
      </div>
    )
  }

  // --- Error state ---
  if (error) {
    return (
      <div className="rounded-lg border border-red-900 bg-gray-900 p-5">
        <h2 className="mb-2 text-lg font-semibold text-white">Presets</h2>
        <p className="text-sm text-red-400">Failed to load presets: {error}</p>
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
    <div className="space-y-6">
      {/* Header with Save button */}
      <div className="rounded-lg border border-gray-800 bg-gray-900 p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">Presets</h2>
          <button
            onClick={() => setShowSaveDialog(true)}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 transition-colors cursor-pointer"
          >
            💾 Save Current
          </button>
        </div>

        {/* Save dialog */}
        {showSaveDialog && (
          <div className="mb-4 rounded-md border border-gray-700 bg-gray-800 p-4">
            <label className="mb-1 block text-xs font-medium text-gray-400 uppercase tracking-wider">
              Preset Name
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={presetName}
                onChange={e => setPresetName(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handleSave() }}
                placeholder="My favorite combo..."
                maxLength={255}
                className="flex-1 rounded-md border border-gray-600 bg-gray-700 px-3 py-1.5 text-sm text-gray-200 placeholder-gray-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                autoFocus
              />
              <button
                onClick={handleSave}
                disabled={!presetName.trim() || isSaving}
                className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer transition-colors"
              >
                {isSaving ? 'Saving…' : 'Save'}
              </button>
              <button
                onClick={() => { setShowSaveDialog(false); setPresetName('') }}
                className="rounded-md bg-gray-700 px-3 py-1.5 text-xs font-medium text-gray-400 hover:text-white hover:bg-gray-600 cursor-pointer transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Preset list */}
        {presets.length === 0 ? (
          <div className="py-6 text-center">
            <span className="text-2xl">📦</span>
            <p className="mt-2 text-sm text-gray-500">No presets saved yet.</p>
            <p className="text-xs text-gray-600">
              Configure attributes and click "Save Current" to create a preset.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {presets.map(preset => (
              <div
                key={preset.preset_id}
                className="group flex items-center gap-3 rounded-md border border-gray-700 bg-gray-800 p-3 hover:border-gray-600 transition-colors"
              >
                {/* Preset info */}
                <div className="flex-1 min-w-0">
                  <h3 className="text-sm font-medium text-white truncate">
                    {preset.name}
                  </h3>
                  <div className="mt-0.5 flex flex-wrap gap-1">
                    {Object.entries(preset.attributes || {})
                      .filter(([, v]) => v)
                      .slice(0, 4)
                      .map(([key, val]) => (
                        <span
                          key={key}
                          className="inline-flex items-center rounded bg-gray-700 px-1.5 py-0.5 text-[10px] text-gray-400"
                        >
                          {val}
                        </span>
                      ))}
                    {Object.values(preset.attributes || {}).filter(Boolean).length > 4 && (
                      <span className="text-[10px] text-gray-500">
                        +{Object.values(preset.attributes).filter(Boolean).length - 4} more
                      </span>
                    )}
                  </div>
                </div>

                {/* Action buttons */}
                <div className="flex gap-1.5 opacity-100 lg:opacity-0 lg:group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={() => handleLoad(preset)}
                    className="rounded bg-indigo-600/20 px-2 py-1 text-xs font-medium text-indigo-300 hover:bg-indigo-600/30 cursor-pointer border border-indigo-600/40 transition-colors"
                    title="Load this preset"
                  >
                    Load
                  </button>
                  <button
                    onClick={() => setDeleteTarget(preset)}
                    className="rounded bg-red-900/20 px-2 py-1 text-xs font-medium text-red-400 hover:bg-red-900/30 cursor-pointer border border-red-800/40 transition-colors"
                    title="Delete this preset"
                  >
                    🗑️
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Delete confirmation dialog */}
      {deleteTarget && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="rounded-lg border border-gray-700 bg-gray-900 p-6 shadow-xl max-w-sm w-full mx-4">
            <h3 className="text-base font-semibold text-white">Delete Preset</h3>
            <p className="mt-2 text-sm text-gray-400">
              Are you sure you want to delete <span className="text-white font-medium">"{deleteTarget.name}"</span>?
              This cannot be undone.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setDeleteTarget(null)}
                className="rounded-md bg-gray-700 px-3 py-1.5 text-sm font-medium text-gray-300 hover:bg-gray-600 cursor-pointer transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDelete(deleteTarget.preset_id)}
                className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-500 cursor-pointer transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default PresetManager