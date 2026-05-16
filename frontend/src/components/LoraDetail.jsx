import { useState, useEffect, useCallback } from 'react'
import {
  fetchLoRAMetadata,
  fetchPreviewImages,
  exportLoRA,
  fetchWorkflowTemplate,
} from '../api/client'

/**
 * LoraDetail — LoRA metadata display, preview images, and export UI.
 *
 * Props:
 * - jobId: the completed LoRA job ID
 * - characterId: the character profile ID
 * - showToast: callback to show a toast notification
 *
 * Features:
 * - LoRA metadata display (trigger token, recommended strength, etc.)
 * - Preview images grid
 * - "Export to ComfyUI" button
 * - "Generate ComfyUI Workflow" button
 * - Version history list
 */
function LoraDetail({ jobId, characterId, showToast }) {
  // Metadata
  const [metadata, setMetadata] = useState(null)
  const [metadataLoading, setMetadataLoading] = useState(true)

  // Previews
  const [previews, setPreviews] = useState([])
  const [previewsLoading, setPreviewsLoading] = useState(true)

  // Export
  const [comfyuiDir, setComfyuiDir] = useState('')
  const [exporting, setExporting] = useState(false)

  // Workflow
  const [workflow, setWorkflow] = useState(null)
  const [workflowLoading, setWorkflowLoading] = useState(false)

  // Load metadata
  const loadMetadata = useCallback(async () => {
    try {
      setMetadataLoading(true)
      const data = await fetchLoRAMetadata(jobId)
      setMetadata(data.metadata || null)
    } catch (err) {
      showToast(`❌ Failed to load metadata: ${err.message}`)
    } finally {
      setMetadataLoading(false)
    }
  }, [jobId, showToast])

  // Load preview images
  const loadPreviews = useCallback(async () => {
    try {
      setPreviewsLoading(true)
      const data = await fetchPreviewImages(jobId)
      setPreviews(data.previews || [])
    } catch {
      // Previews may not exist yet
    } finally {
      setPreviewsLoading(false)
    }
  }, [jobId])

  // Initial load
  useEffect(() => {
    loadMetadata()
    loadPreviews()
  }, [loadMetadata, loadPreviews])

  // Export to ComfyUI
  const handleExport = useCallback(async () => {
    if (!comfyuiDir.trim()) {
      showToast('❌ Please enter the ComfyUI models/loras/ directory path')
      return
    }
    setExporting(true)
    try {
      const result = await exportLoRA(jobId, comfyuiDir.trim())
      showToast(`✅ LoRA exported to ${result.export_path}`)
    } catch (err) {
      showToast(`❌ Export failed: ${err.message}`)
    } finally {
      setExporting(false)
    }
  }, [jobId, comfyuiDir, showToast])

  // Generate workflow template
  const handleGenerateWorkflow = useCallback(async () => {
    setWorkflowLoading(true)
    try {
      const data = await fetchWorkflowTemplate(characterId)
      setWorkflow(data)
      showToast('✅ Workflow template generated')
    } catch (err) {
      showToast(`❌ Failed to generate workflow: ${err.message}`)
    } finally {
      setWorkflowLoading(false)
    }
  }, [characterId, showToast])

  // Copy workflow JSON to clipboard
  const handleCopyWorkflow = useCallback(() => {
    if (!workflow?.workflow) return
    // Remove internal metadata keys before copying
    const cleanWorkflow = { ...workflow.workflow }
    delete cleanWorkflow._preview_name
    delete cleanWorkflow._preview_prompt
    delete cleanWorkflow._preview_view
    delete cleanWorkflow._preview_pose
    navigator.clipboard.writeText(JSON.stringify(cleanWorkflow, null, 2))
      .then(() => showToast('📋 Workflow JSON copied to clipboard'))
      .catch(() => showToast('❌ Failed to copy to clipboard'))
  }, [workflow, showToast])

  if (metadataLoading) {
    return (
      <div className="mt-4 p-4 bg-gray-800 rounded-lg border border-gray-700">
        <div className="animate-pulse space-y-3">
          <div className="h-4 bg-gray-700 rounded w-1/3" />
          <div className="h-4 bg-gray-700 rounded w-2/3" />
        </div>
      </div>
    )
  }

  return (
    <div className="mt-4 space-y-4">
      {/* Metadata Display */}
      {metadata && (
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-3">
          <h5 className="text-xs font-semibold text-white mb-2">LoRA Metadata</h5>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
            <div className="text-gray-500">Name</div>
            <div className="text-gray-300">{metadata.lora_name || '—'}</div>
            <div className="text-gray-500">Trigger Token</div>
            <div className="text-emerald-400 font-mono">{metadata.trigger_token || '—'}</div>
            <div className="text-gray-500">Base Model</div>
            <div className="text-gray-300">{metadata.base_model_filename || metadata.base_model || '—'}</div>
            <div className="text-gray-500">Recommended Strength</div>
            <div className="text-gray-300">{metadata.recommended_strength || '—'}</div>
            <div className="text-gray-500">Dataset Count</div>
            <div className="text-gray-300">{metadata.dataset_count ?? '—'}</div>
            <div className="text-gray-500">Learning Rate</div>
            <div className="text-gray-300">{metadata.learning_rate || '—'}</div>
            <div className="text-gray-500">Epochs</div>
            <div className="text-gray-300">{metadata.epochs || '—'}</div>
            <div className="text-gray-500">Created</div>
            <div className="text-gray-300">
              {metadata.created_at ? new Date(metadata.created_at).toLocaleDateString() : '—'}
            </div>
          </div>

          {/* Recommended Prompt Prefix */}
          {metadata.recommended_prompt_prefix && (
            <div className="mt-3 pt-2 border-t border-gray-700">
              <div className="text-[10px] text-gray-500 mb-1">Recommended Prompt Prefix</div>
              <div className="bg-gray-900 rounded p-2 text-xs text-emerald-300 font-mono break-all">
                {metadata.recommended_prompt_prefix}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Preview Images */}
      <div className="bg-gray-800 border border-gray-700 rounded-lg p-3">
        <h5 className="text-xs font-semibold text-white mb-2">Preview Images</h5>
        {previewsLoading ? (
          <div className="animate-pulse h-24 bg-gray-700 rounded" />
        ) : previews.length > 0 ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {previews.map(preview => (
              <div key={preview.filename} className="bg-gray-900 rounded overflow-hidden">
                <div className="aspect-square bg-gray-700 flex items-center justify-center text-[10px] text-gray-400">
                  🖼 {preview.filename}
                </div>
                <div className="px-1 py-0.5 text-[9px] text-gray-500 truncate">
                  {(preview.size / 1024).toFixed(1)} KB
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-gray-500">
            No preview images yet. Generate previews from a completed training job.
          </p>
        )}
      </div>

      {/* Export to ComfyUI */}
      <div className="bg-gray-800 border border-gray-700 rounded-lg p-3">
        <h5 className="text-xs font-semibold text-white mb-2">Export to ComfyUI</h5>
        <div className="flex gap-2">
          <input
            type="text"
            value={comfyuiDir}
            onChange={e => setComfyuiDir(e.target.value)}
            placeholder="/path/to/ComfyUI/models/loras"
            className="flex-1 bg-gray-900 border border-gray-600 rounded text-xs text-white px-2 py-1.5 focus:outline-none focus:border-emerald-500"
          />
          <button
            onClick={handleExport}
            disabled={exporting || !comfyuiDir.trim()}
            className="px-3 py-1.5 text-xs font-medium rounded transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed bg-emerald-700 hover:bg-emerald-600 text-emerald-100"
          >
            {exporting ? 'Exporting...' : '📤 Export'}
          </button>
        </div>
        <p className="text-[10px] text-gray-500 mt-1">
          Enter the path to your ComfyUI models/loras/ directory
        </p>
      </div>

      {/* Workflow Template */}
      <div className="bg-gray-800 border border-gray-700 rounded-lg p-3">
        <h5 className="text-xs font-semibold text-white mb-2">ComfyUI Workflow Template</h5>
        <div className="flex gap-2 mb-2">
          <button
            onClick={handleGenerateWorkflow}
            disabled={workflowLoading}
            className="px-3 py-1.5 text-xs font-medium rounded transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed bg-blue-700 hover:bg-blue-600 text-blue-100"
          >
            {workflowLoading ? 'Generating...' : '🔧 Generate Workflow'}
          </button>
          {workflow && (
            <button
              onClick={handleCopyWorkflow}
              className="px-3 py-1.5 text-xs font-medium rounded transition-colors cursor-pointer bg-gray-700 hover:bg-gray-600 text-gray-200"
            >
              📋 Copy JSON
            </button>
          )}
        </div>
        {workflow && (
          <div className="bg-gray-900 rounded p-2 max-h-48 overflow-y-auto">
            <pre className="text-[10px] text-gray-300 font-mono whitespace-pre-wrap break-all">
              {JSON.stringify(workflow.workflow, null, 2).slice(0, 2000)}
              {JSON.stringify(workflow.workflow, null, 2).length > 2000 && '\n... (truncated)'}
            </pre>
          </div>
        )}
      </div>
    </div>
  )
}

export default LoraDetail