import { useState, useEffect, useCallback, useRef } from 'react'
import {
  uploadReferences,
  fetchReferences,
  updateReference,
  deleteReference,
  getReferenceFileUrl,
  validateDataset,
} from '../api/client'

/**
 * ReferenceManager — Upload, curate, and manage reference images for a character.
 *
 * Props:
 * - characterId: the character profile ID
 * - showToast: callback to show a toast notification
 */

const STATUS_CONFIG = {
  pending: { label: 'Pending', icon: '⬜', color: 'text-gray-400 bg-gray-700/50 border-gray-600' },
  accepted: { label: 'Accepted', icon: '✅', color: 'text-emerald-300 bg-emerald-900/30 border-emerald-700' },
  rejected: { label: 'Rejected', icon: '❌', color: 'text-red-300 bg-red-900/30 border-red-700' },
  maybe: { label: 'Maybe', icon: '🟡', color: 'text-yellow-300 bg-yellow-900/30 border-yellow-700' },
}

const ANGLE_OPTIONS = ['front', 'side', 'back', 'three-quarter']

function ReferenceManager({ characterId, showToast }) {
  const [references, setReferences] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [statusFilter, setStatusFilter] = useState('')
  const [validation, setValidation] = useState(null)
  const [validating, setValidating] = useState(false)
  const [selectedImage, setSelectedImage] = useState(null)
  const fileInputRef = useRef(null)

  const loadReferences = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await fetchReferences(characterId, statusFilter || undefined)
      setReferences(data || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [characterId, statusFilter])

  useEffect(() => {
    if (characterId) loadReferences()
  }, [characterId, loadReferences])

  // --- Upload ---
  const handleFiles = useCallback(async (files) => {
    if (!files || files.length === 0) return
    setUploading(true)
    try {
      await uploadReferences(characterId, Array.from(files))
      showToast(`📸 Uploaded ${files.length} image(s)`)
      await loadReferences()
    } catch (err) {
      showToast(`❌ Upload failed: ${err.message}`)
    } finally {
      setUploading(false)
    }
  }, [characterId, showToast, loadReferences])

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
    const files = e.dataTransfer?.files
    if (files) handleFiles(files)
  }, [handleFiles])

  const handleDragOver = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
  }, [])

  // --- Status change ---
  const handleStatusChange = useCallback(async (imageId, newStatus) => {
    try {
      await updateReference(characterId, imageId, { status: newStatus })
      showToast(`Marked as ${newStatus}`)
      await loadReferences()
    } catch (err) {
      showToast(`❌ ${err.message}`)
    }
  }, [characterId, showToast, loadReferences])

  // --- Angle change ---
  const handleAngleChange = useCallback(async (imageId, newAngle) => {
    try {
      await updateReference(characterId, imageId, { angle: newAngle || null })
      await loadReferences()
    } catch (err) {
      showToast(`❌ ${err.message}`)
    }
  }, [characterId, loadReferences, showToast])

  // --- Delete ---
  const handleDelete = useCallback(async (imageId) => {
    try {
      await deleteReference(characterId, imageId)
      showToast('🗑️ Image deleted')
      setSelectedImage(null)
      await loadReferences()
    } catch (err) {
      showToast(`❌ ${err.message}`)
    }
  }, [characterId, showToast, loadReferences])

  // --- Validation ---
  const handleValidate = useCallback(async () => {
    setValidating(true)
    try {
      const result = await validateDataset(characterId)
      setValidation(result)
    } catch (err) {
      showToast(`❌ Validation failed: ${err.message}`)
    } finally {
      setValidating(false)
    }
  }, [characterId, showToast])

  // --- Status counts ---
  const statusCounts = references.reduce((acc, ref) => {
    acc[ref.status] = (acc[ref.status] || 0) + 1
    return acc
  }, {})

  return (
    <div className="mt-4">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-semibold text-white">Reference Images</h4>
        <div className="flex gap-2">
          <button
            onClick={handleValidate}
            disabled={validating}
            className="px-3 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-gray-300 rounded transition-colors cursor-pointer disabled:opacity-50"
          >
            {validating ? 'Checking...' : '🔍 Validate Dataset'}
          </button>
        </div>
      </div>

      {/* Status summary */}
      <div className="flex gap-3 mb-3 text-xs">
        {Object.entries(STATUS_CONFIG).map(([key, cfg]) => (
          <span key={key} className={`${cfg.color} px-2 py-0.5 rounded border`}>
            {cfg.icon} {statusCounts[key] || 0} {cfg.label}
          </span>
        ))}
      </div>

      {/* Validation warnings */}
      {validation && (
        <div className={`mb-3 rounded-lg border p-3 ${
          validation.is_ready
            ? 'bg-emerald-900/20 border-emerald-700'
            : 'bg-yellow-900/20 border-yellow-700'
        }`}>
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-semibold text-white">
              Dataset Quality
            </span>
            <span className={`text-xs font-medium ${validation.is_ready ? 'text-emerald-400' : 'text-yellow-400'}`}>
              {validation.is_ready ? '✅ Ready for training' : '⚠️ Needs attention'}
            </span>
          </div>
          <p className="text-xs text-gray-400">
            {validation.accepted_count} accepted / {validation.total_images} total images
          </p>
          {validation.warnings.length > 0 && (
            <ul className="mt-2 space-y-1">
              {validation.warnings.map((w, i) => (
                <li key={i} className="text-xs text-yellow-300">
                  {w.severity === 'error' ? '🚫' : '⚠️'} {w.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Upload area */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onClick={() => fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors mb-4
          ${uploading ? 'border-emerald-500 bg-emerald-900/10' : 'border-gray-600 hover:border-gray-500 bg-gray-800/30'}`}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".png,.jpg,.jpeg,.webp"
          className="hidden"
          onChange={e => handleFiles(e.target.files)}
        />
        {uploading ? (
          <div className="text-emerald-400 text-sm">
            <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-gray-600 border-t-emerald-500 mr-2 align-middle" />
            Uploading...
          </div>
        ) : (
          <div>
            <p className="text-gray-400 text-sm">Drop images here or click to upload</p>
            <p className="text-gray-500 text-xs mt-1">PNG, JPG, WEBP</p>
          </div>
        )}
      </div>

      {/* Status filter */}
      <div className="flex gap-1 mb-3">
        <button
          onClick={() => setStatusFilter('')}
          className={`px-2 py-1 text-xs rounded transition-colors cursor-pointer ${!statusFilter ? 'bg-gray-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}
        >
          All
        </button>
        {Object.entries(STATUS_CONFIG).map(([key, cfg]) => (
          <button
            key={key}
            onClick={() => setStatusFilter(key)}
            className={`px-2 py-1 text-xs rounded transition-colors cursor-pointer ${statusFilter === key ? 'bg-gray-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}
          >
            {cfg.icon} {cfg.label}
          </button>
        ))}
      </div>

      {/* Loading / Error */}
      {loading && <p className="text-gray-400 text-sm">Loading images...</p>}
      {error && <p className="text-red-400 text-sm">Error: {error}</p>}

      {/* Empty state */}
      {!loading && references.length === 0 && (
        <p className="text-gray-500 text-sm text-center py-4">
          No reference images yet. Upload some to get started!
        </p>
      )}

      {/* Image grid */}
      {!loading && references.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
          {references.map(ref => {
            const cfg = STATUS_CONFIG[ref.status] || STATUS_CONFIG.pending
            return (
              <div
                key={ref.image_id}
                className={`relative bg-gray-800 border rounded-lg overflow-hidden cursor-pointer transition-colors
                  ${selectedImage === ref.image_id ? 'border-emerald-500 ring-1 ring-emerald-500' : 'border-gray-700 hover:border-gray-500'}`}
                onClick={() => setSelectedImage(selectedImage === ref.image_id ? null : ref.image_id)}
              >
                {/* Thumbnail */}
                <div className="aspect-square bg-gray-900 flex items-center justify-center overflow-hidden">
                  <img
                    src={getReferenceFileUrl(characterId, ref.image_id)}
                    alt={ref.original_filename}
                    className="w-full h-full object-cover"
                    loading="lazy"
                  />
                </div>

                {/* Status badge */}
                <div className={`absolute top-1 right-1 text-xs px-1.5 py-0.5 rounded border ${cfg.color}`}>
                  {cfg.icon}
                </div>

                {/* Angle badge */}
                {ref.angle && (
                  <div className="absolute top-1 left-1 text-[10px] bg-gray-900/80 text-gray-300 px-1.5 py-0.5 rounded">
                    {ref.angle}
                  </div>
                )}

                {/* Info bar */}
                <div className="p-1.5">
                  <p className="text-[10px] text-gray-400 truncate">{ref.original_filename}</p>
                </div>

                {/* Expanded actions */}
                {selectedImage === ref.image_id && (
                  <div className="absolute inset-0 bg-black/70 flex flex-col items-center justify-center gap-1.5 p-2">
                    {/* Status buttons */}
                    <div className="flex gap-1">
                      {Object.entries(STATUS_CONFIG).map(([key, sc]) => (
                        <button
                          key={key}
                          onClick={(e) => { e.stopPropagation(); handleStatusChange(ref.image_id, key) }}
                          className={`px-1.5 py-0.5 text-[10px] rounded border transition-colors cursor-pointer
                            ${ref.status === key ? sc.color : 'bg-gray-800 border-gray-600 text-gray-400 hover:text-white'}`}
                        >
                          {sc.icon}
                        </button>
                      ))}
                    </div>

                    {/* Angle selector */}
                    <select
                      value={ref.angle || ''}
                      onClick={e => e.stopPropagation()}
                      onChange={e => handleAngleChange(ref.image_id, e.target.value)}
                      className="bg-gray-800 border border-gray-600 rounded text-xs text-white px-1 py-0.5 w-full"
                    >
                      <option value="">No angle</option>
                      {ANGLE_OPTIONS.map(a => (
                        <option key={a} value={a}>{a}</option>
                      ))}
                    </select>

                    {/* Delete */}
                    <button
                      onClick={(e) => { e.stopPropagation(); handleDelete(ref.image_id) }}
                      className="px-2 py-0.5 text-[10px] bg-red-900/50 hover:bg-red-800 text-red-300 rounded transition-colors cursor-pointer"
                    >
                      🗑️ Delete
                    </button>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default ReferenceManager