import { useState, useEffect, useCallback } from 'react'
import { fetchPoseBatches, generatePoseBatch, submitToComfyUI } from '../api/client'

/**
 * PoseBatchGenerator — UI for generating batch prompts from pose templates.
 *
 * Allows the user to:
 * - Select a pose batch template (or use custom poses/views)
 * - Optionally select a LoRA model for trigger token injection
 * - Preview the prompts that will be generated
 * - Generate the batch and view results as a grid
 * - Send all prompts to ComfyUI sequentially
 * - Copy all prompts as JSON
 */
function PoseBatchGenerator({
  loraSelection,
  attributes,
  lockedFields,
  templateId,
  negativeProfileId,
  characterName,
  comfyUISettings,
  onCopy,
  showToast,
}) {
  // --- Pose batch template state ---
  const [batchTemplates, setBatchTemplates] = useState([])
  const [selectedBatchId, setSelectedBatchId] = useState('')
  const [loadingTemplates, setLoadingTemplates] = useState(true)

  // --- Generation state ---
  const [isGenerating, setIsGenerating] = useState(false)
  const [batchResult, setBatchResult] = useState(null)
  const [error, setError] = useState(null)

  // --- ComfyUI sequential submission state ---
  const [sendingToComfyUI, setSendingToComfyUI] = useState(false)
  const [comfyUIProgress, setComfyUIProgress] = useState({ sent: 0, total: 0, errors: 0 })

  // --- Load pose batch templates ---
  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const data = await fetchPoseBatches()
        if (!cancelled) setBatchTemplates(data.batches || [])
      } catch (err) {
        if (!cancelled) setError(err.message)
      } finally {
        if (!cancelled) setLoadingTemplates(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  // --- Generate batch ---
  const handleGenerate = useCallback(async () => {
    setIsGenerating(true)
    setError(null)
    setBatchResult(null)
    try {
      const params = {}
      if (selectedBatchId) {
        params.batchId = selectedBatchId
      }
      if (loraSelection?.triggerToken) {
        params.loraTriggerToken = loraSelection.triggerToken
      }
      if (attributes && Object.keys(attributes).length > 0) {
        params.attributes = attributes
      }
      if (lockedFields?.length > 0) {
        params.lockedFields = lockedFields
      }
      if (templateId) {
        params.templateId = templateId
      }
      if (negativeProfileId) {
        params.negativeProfileId = negativeProfileId
      }
      if (characterName) {
        params.characterName = characterName
      }
      const result = await generatePoseBatch(params)
      setBatchResult(result)
    } catch (err) {
      setError(err.message || 'Failed to generate pose batch')
    } finally {
      setIsGenerating(false)
    }
  }, [selectedBatchId, loraSelection, attributes, lockedFields, templateId, negativeProfileId, characterName])

  // --- Send all to ComfyUI sequentially ---
  const handleSendAllToComfyUI = useCallback(async () => {
    if (!batchResult?.items?.length) return

    const settings = comfyUISettings
    if (!settings?.serverUrl || !settings.workflowJson || !settings.positiveNodeId) {
      showToast?.('⚠️ Configure ComfyUI settings first (Settings page)')
      return
    }

    let workflowObj
    try {
      workflowObj = typeof settings.workflowJson === 'string'
        ? JSON.parse(settings.workflowJson)
        : settings.workflowJson
    } catch {
      showToast?.('❌ Invalid workflow JSON in settings')
      return
    }

    setSendingToComfyUI(true)
    setComfyUIProgress({ sent: 0, total: batchResult.items.length, errors: 0 })

    const nodeMapping = {
      positive_node_id: settings.positiveNodeId || '',
      positive_input_name: settings.positiveInputName || 'text',
      negative_node_id: settings.negativeNodeId || '',
      negative_input_name: settings.negativeInputName || 'text',
    }
    if (settings.seedNodeId) {
      nodeMapping.seed_node_id = settings.seedNodeId
      nodeMapping.seed_input_name = settings.seedInputName || 'seed'
    }

    let sent = 0
    let errors = 0

    for (const item of batchResult.items) {
      try {
        await submitToComfyUI({
          serverUrl: settings.serverUrl,
          workflowJson: workflowObj,
          positivePrompt: item.positive_prompt,
          negativePrompt: item.negative_prompt,
          nodeMapping,
        })
        sent++
      } catch {
        errors++
      }
      setComfyUIProgress({ sent, total: batchResult.items.length, errors })
      // Small delay between submissions to avoid overwhelming ComfyUI
      await new Promise(resolve => setTimeout(resolve, 500))
    }

    setSendingToComfyUI(false)
    showToast?.(
      `✅ Sent ${sent}/${batchResult.items.length} prompts to ComfyUI` +
      (errors > 0 ? ` (${errors} errors)` : '')
    )
  }, [batchResult, showToast])

  // --- Copy all prompts as JSON ---
  const handleCopyAll = useCallback(async () => {
    if (!batchResult?.items?.length) return
    const data = batchResult.items.map(item => ({
      name: item.name,
      pose: item.pose,
      view: item.view,
      positive_prompt: item.positive_prompt,
      negative_prompt: item.negative_prompt,
      ...(item.output_name ? { output_name: item.output_name } : {}),
    }))
    const json = JSON.stringify(data, null, 2)
    try {
      await navigator.clipboard.writeText(json)
      showToast?.('📋 All prompts copied as JSON!')
    } catch {
      // Fallback
      try {
        const textarea = document.createElement('textarea')
        textarea.value = json
        textarea.style.position = 'fixed'
        textarea.style.opacity = '0'
        document.body.appendChild(textarea)
        textarea.select()
        document.execCommand('copy')
        document.body.removeChild(textarea)
        showToast?.('📋 All prompts copied as JSON!')
      } catch {
        showToast?.('❌ Copy failed — please copy manually')
      }
    }
  }, [batchResult, showToast])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">Pose Batch Generator</h2>
        {loraSelection && (
          <span className="inline-flex items-center rounded bg-indigo-600/20 px-2.5 py-1 text-xs font-medium text-indigo-300 border border-indigo-600/30">
            LoRA: <code className="ml-1 font-mono">{loraSelection.triggerToken}</code>
            <span className="ml-2 text-amber-400">str: {loraSelection.recommendedStrength}</span>
          </span>
        )}
      </div>

      {/* Batch Template Selector */}
      <div className="rounded-lg border border-gray-800 bg-gray-900 p-5">
        <h3 className="mb-3 text-sm font-semibold text-gray-300">Pose Batch Template</h3>
        {loadingTemplates ? (
          <div className="h-9 rounded bg-gray-800 animate-pulse" />
        ) : batchTemplates.length === 0 ? (
          <p className="text-sm text-gray-500">No pose batch templates available</p>
        ) : (
          <select
            value={selectedBatchId}
            onChange={e => setSelectedBatchId(e.target.value)}
            className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm text-gray-200 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="">— Custom (default poses & views) —</option>
            {batchTemplates.map(batch => (
              <option key={batch.id} value={batch.id}>
                {batch.label} ({batch.poses.length} poses)
              </option>
            ))}
          </select>
        )}

        {/* Template description */}
        {selectedBatchId && batchTemplates.length > 0 && (
          <div className="mt-3">
            {(() => {
              const batch = batchTemplates.find(b => b.id === selectedBatchId)
              if (!batch) return null
              return (
                <div className="rounded-md bg-gray-800/50 border border-gray-700 p-3">
                  <p className="text-xs text-gray-400 mb-2">{batch.description}</p>
                  <div className="flex flex-wrap gap-1.5">
                    {batch.poses.map(pose => (
                      <span
                        key={pose.name}
                        className="inline-flex items-center rounded-full bg-gray-700 px-2 py-0.5 text-xs text-gray-300 border border-gray-600"
                      >
                        {pose.name}
                      </span>
                    ))}
                  </div>
                </div>
              )
            })()}
          </div>
        )}

        {/* Generate Button */}
        <div className="mt-4">
          <button
            onClick={handleGenerate}
            disabled={isGenerating}
            className="w-full rounded-md bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-gray-900 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          >
            {isGenerating ? (
              <span className="flex items-center justify-center gap-2">
                <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                Generating Batch…
              </span>
            ) : (
              <span className="flex items-center justify-center gap-2">
                🎭 Generate Pose Batch
              </span>
            )}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-900 bg-gray-900 p-4">
          <div className="flex items-start gap-3">
            <span className="text-xl">⚠️</span>
            <div>
              <h3 className="text-sm font-semibold text-red-400">Batch Generation Failed</h3>
              <p className="mt-1 text-sm text-gray-400">{error}</p>
            </div>
          </div>
        </div>
      )}

      {/* Results */}
      {batchResult && Array.isArray(batchResult.items) && batchResult.items.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-white">
              Batch Results
              <span className="ml-2 text-sm font-normal text-gray-500">
                ({batchResult.items.length} prompts)
              </span>
            </h3>
            <div className="flex gap-2">
              <button
                onClick={handleCopyAll}
                disabled={!batchResult.items.length}
                className="rounded-md bg-gray-700 px-3 py-1.5 text-xs font-medium text-gray-300 hover:bg-gray-600 hover:text-white transition-colors cursor-pointer border border-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                📋 Copy All as JSON
              </button>
              <button
                onClick={handleSendAllToComfyUI}
                disabled={sendingToComfyUI || !batchResult.items.length}
                className="rounded-md bg-purple-600/20 px-3 py-1.5 text-xs font-medium text-purple-300 hover:bg-purple-600/30 transition-colors cursor-pointer border border-purple-600/40 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {sendingToComfyUI
                  ? `🚀 Sending ${comfyUIProgress.sent}/${comfyUIProgress.total}…`
                  : '🚀 Send All to ComfyUI'}
              </button>
            </div>
          </div>

          {/* ComfyUI progress */}
          {sendingToComfyUI && (
            <div className="rounded-md bg-purple-900/20 border border-purple-700 p-3">
              <div className="flex items-center gap-3">
                <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-purple-400/30 border-t-purple-400" />
                <span className="text-sm text-purple-300">
                  Sending to ComfyUI: {comfyUIProgress.sent}/{comfyUIProgress.total}
                  {comfyUIProgress.errors > 0 && ` (${comfyUIProgress.errors} errors)`}
                </span>
              </div>
              <div className="mt-2 h-1.5 rounded-full bg-gray-800 overflow-hidden">
                <div
                  className="h-full bg-purple-500 transition-all duration-300"
                  style={{ width: `${(comfyUIProgress.sent / Math.max(comfyUIProgress.total, 1)) * 100}%` }}
                />
              </div>
            </div>
          )}

          {/* Prompt grid */}
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {batchResult.items.map((item, index) => (
              <div
                key={item.name || index}
                className="rounded-lg border border-gray-800 bg-gray-900 p-4"
              >
                <div className="mb-2 flex items-center justify-between">
                  <h4 className="text-sm font-semibold text-gray-200">{item.name}</h4>
                  <div className="flex gap-1">
                    <span className="rounded bg-gray-700 px-1.5 py-0.5 text-[10px] text-gray-400">
                      {item.view}
                    </span>
                  </div>
                </div>
                {item.output_name && (
                  <div className="mb-2 rounded bg-gray-800/60 border border-gray-700 px-2 py-1">
                    <label className="mb-0.5 block text-[10px] font-medium text-amber-400 uppercase tracking-wider">
                      Output Filename
                    </label>
                    <p className="text-xs text-amber-200 font-mono leading-relaxed" title={item.output_name}>
                      {item.output_name}
                    </p>
                  </div>
                )}
                <div className="mb-2">
                  <label className="mb-0.5 block text-[10px] font-medium text-emerald-400 uppercase tracking-wider">
                    Positive
                  </label>
                  <p className="text-xs text-gray-300 leading-relaxed line-clamp-3" title={item.positive_prompt}>
                    {loraSelection?.triggerToken && item.positive_prompt.startsWith(loraSelection.triggerToken + ',') ? (
                      <>
                        <span className="rounded bg-indigo-600/25 px-0.5 text-indigo-300 font-mono font-medium">{loraSelection.triggerToken}</span>
                        <span>{item.positive_prompt.slice(loraSelection.triggerToken.length)}</span>
                      </>
                    ) : item.positive_prompt}
                  </p>
                </div>
                <div>
                  <label className="mb-0.5 block text-[10px] font-medium text-red-400 uppercase tracking-wider">
                    Negative
                  </label>
                  <p className="text-xs text-gray-400 leading-relaxed line-clamp-2" title={item.negative_prompt}>
                    {item.negative_prompt}
                  </p>
                </div>
                <div className="mt-2 flex gap-1.5">
                  <button
                    onClick={() => onCopy?.(item.positive_prompt, 'Positive')}
                    className="rounded bg-gray-800 px-2 py-0.5 text-[10px] font-medium text-gray-400 hover:bg-gray-700 hover:text-white transition-colors cursor-pointer border border-gray-700"
                  >
                    📋 Pos
                  </button>
                  <button
                    onClick={() => onCopy?.(item.negative_prompt, 'Negative')}
                    className="rounded bg-gray-800 px-2 py-0.5 text-[10px] font-medium text-gray-400 hover:bg-gray-700 hover:text-white transition-colors cursor-pointer border border-gray-700"
                  >
                    📋 Neg
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default PoseBatchGenerator