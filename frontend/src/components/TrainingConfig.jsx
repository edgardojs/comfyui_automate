import { useState, useEffect, useCallback } from 'react'
import {
  fetchTrainingPresets,
  fetchReferences,
  validateDataset,
  createLoRAJob,
  fetchLoRAJobs,
} from '../api/client'

/**
 * TrainingConfig — LoRA training configuration and job creation UI.
 *
 * Props:
 * - characterId: the character profile ID
 * - showToast: callback to show a toast notification
 *
 * Features:
 * - Training preset selector dropdown
 * - Auto-fill parameters when preset selected
 * - Manual override fields for all training parameters
 * - Base model path input
 * - LoRA strength slider (0.1–2.0, default 1.0)
 * - Dataset readiness indicator
 * - "Start Training" button (disabled until dataset is ready)
 * - Existing jobs list
 */

const OUTPUT_FORMATS = ['safetensors', 'pt', 'ckpt']

const DEFAULT_CONFIG = {
  base_model: 'stabilityai/stable-diffusion-xl-base-1.0',
  learning_rate: 0.0002,
  epochs: 18,
  preview_interval: 2,
  output_format: 'safetensors',
  lora_strength: 1.0,
}

function TrainingConfig({ characterId, showToast }) {
  // Presets
  const [presets, setPresets] = useState([])
  const [presetsLoading, setPresetsLoading] = useState(true)
  const [selectedPresetId, setSelectedPresetId] = useState('')

  // Config form state
  const [config, setConfig] = useState({ ...DEFAULT_CONFIG })
  const [customArgs, setCustomArgs] = useState('')

  // Dataset readiness
  const [datasetInfo, setDatasetInfo] = useState(null)
  const [datasetLoading, setDatasetLoading] = useState(true)

  // Jobs
  const [jobs, setJobs] = useState([])
  const [creating, setCreating] = useState(false)
  const [showAllJobs, setShowAllJobs] = useState(false)

  // Load presets
  useEffect(() => {
    async function loadPresets() {
      try {
        setPresetsLoading(true)
        const data = await fetchTrainingPresets()
        setPresets(data || [])
      } catch (err) {
        showToast(`❌ Failed to load presets: ${err.message}`)
      } finally {
        setPresetsLoading(false)
      }
    }
    loadPresets()
  }, [showToast])

  // Load dataset info
  const loadDatasetInfo = useCallback(async () => {
    try {
      setDatasetLoading(true)
      const [validation, refs] = await Promise.all([
        validateDataset(characterId),
        fetchReferences(characterId, 'accepted'),
      ])
      setDatasetInfo({
        ...validation,
        acceptedImages: refs || [],
      })
    } catch (err) {
      // Show error state instead of silently defaulting to "not ready"
      setDatasetInfo({
        is_ready: false,
        warnings: [{ severity: 'error', message: `Failed to load dataset: ${err.message}` }],
        accepted_count: 0,
        total_images: 0,
        acceptedImages: [],
      })
    } finally {
      setDatasetLoading(false)
    }
  }, [characterId])

  useEffect(() => {
    if (characterId) loadDatasetInfo()
  }, [characterId, loadDatasetInfo])

  // Load existing jobs
  const loadJobs = useCallback(async () => {
    try {
      const data = await fetchLoRAJobs({ character_id: characterId })
      setJobs(data || [])
    } catch (err) {
      // Silently fail — jobs may not exist yet for new characters
      console.error('Failed to load LoRA jobs:', err.message)
    }
  }, [characterId])

  useEffect(() => {
    if (characterId) loadJobs()
  }, [characterId, loadJobs])

  // Handle preset selection
  const handlePresetChange = useCallback((e) => {
    const presetId = e.target.value
    setSelectedPresetId(presetId)

    if (presetId) {
      const preset = presets.find(p => String(p.id) === presetId)
      if (preset) {
        setConfig({
          base_model: preset.base_model || config.base_model,
          learning_rate: preset.learning_rate ?? config.learning_rate,
          epochs: preset.epochs ?? config.epochs,
          preview_interval: preset.preview_interval ?? config.preview_interval,
          output_format: preset.output_format || config.output_format,
          lora_strength: config.lora_strength,
        })
      }
    } else {
      // Reset to defaults when deselecting preset
      setConfig({ ...DEFAULT_CONFIG })
    }
  }, [presets, config.base_model, config.lora_strength])

  // Handle config field changes
  const handleConfigChange = useCallback((field, value) => {
    setConfig(prev => ({ ...prev, [field]: value }))
  }, [])

  // Handle create job
  const handleCreateJob = useCallback(async () => {
    setCreating(true)
    try {
      const params = {
        character_id: characterId,
        preset_id: selectedPresetId || undefined,
        base_model: config.base_model,
        learning_rate: config.learning_rate,
        epochs: config.epochs,
        preview_interval: config.preview_interval,
        output_format: config.output_format,
        lora_strength: config.lora_strength,
      }
      // Add custom args if provided
      if (customArgs.trim()) {
        try {
          params.custom_args = JSON.parse(customArgs)
        } catch {
          showToast('❌ Custom args must be valid JSON')
          return
        }
      }
      // Remove undefined values
      Object.keys(params).forEach(key => params[key] === undefined && delete params[key])

      await createLoRAJob(params)
      showToast('✅ Training job created!')
      await loadJobs()
    } catch (err) {
      showToast(`❌ ${err.message}`)
    } finally {
      setCreating(false)
    }
  }, [characterId, selectedPresetId, config, customArgs, showToast, loadJobs])

  // Dataset readiness checks
  const hasEnoughImages = datasetInfo?.accepted_count >= 10
  const allHaveCaptions = datasetInfo?.acceptedImages?.every(r => r.caption && r.caption.trim()) ?? false
  const isReady = hasEnoughImages && allHaveCaptions

  // Selected preset info
  const selectedPreset = presets.find(p => p.id === selectedPresetId)

  return (
    <div className="mt-4">
      <h4 className="text-sm font-semibold text-white mb-3">LoRA Training Configuration</h4>

      {/* Dataset Readiness */}
      <div className={`rounded-lg border p-3 mb-4 ${
        isReady
          ? 'bg-emerald-900/20 border-emerald-700'
          : 'bg-yellow-900/20 border-yellow-700'
      }`}>
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs font-semibold text-white">Dataset Readiness</span>
          <span className={`text-xs font-medium ${isReady ? 'text-emerald-400' : 'text-yellow-400'}`}>
            {isReady ? '✅ Ready for training' : '⚠️ Needs attention'}
          </span>
        </div>
        {datasetLoading ? (
          <p className="text-xs text-gray-400">Checking dataset...</p>
        ) : (
          <div className="space-y-1">
            <p className={`text-xs ${hasEnoughImages ? 'text-emerald-400' : 'text-red-400'}`}>
              {hasEnoughImages ? '✅' : '❌'} {datasetInfo?.accepted_count || 0} accepted images (minimum 10)
            </p>
            <p className={`text-xs ${allHaveCaptions ? 'text-emerald-400' : 'text-red-400'}`}>
              {allHaveCaptions ? '✅' : '❌'} All accepted images have captions
            </p>
          </div>
        )}
      </div>

      {/* Preset Selector */}
      <div className="mb-4">
        <label className="block text-xs font-medium text-gray-400 mb-1">Training Preset</label>
        {presetsLoading ? (
          <div className="h-8 bg-gray-800 rounded animate-pulse" />
        ) : (
          <select
            value={selectedPresetId}
            onChange={handlePresetChange}
            className="w-full bg-gray-800 border border-gray-600 rounded text-sm text-white px-3 py-2 focus:outline-none focus:border-emerald-500"
          >
            <option value="">— Custom (no preset) —</option>
            {presets.map(preset => (
              <option key={preset.id} value={preset.id}>
                {preset.label}
              </option>
            ))}
          </select>
        )}
        {selectedPreset && (
          <p className="text-xs text-gray-500 mt-1">{selectedPreset.description}</p>
        )}
      </div>

      {/* Training Parameters */}
      <div className="space-y-3 mb-4">
        {/* Base Model */}
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1">
            Base Model
          </label>
          <input
            type="text"
            value={config.base_model}
            onChange={e => handleConfigChange('base_model', e.target.value)}
            className="w-full bg-gray-800 border border-gray-600 rounded text-sm text-white px-3 py-2 focus:outline-none focus:border-emerald-500"
            placeholder="stabilityai/stable-diffusion-xl-base-1.0"
          />
          <p className="text-[10px] text-gray-500 mt-0.5">HuggingFace model ID or local path</p>
        </div>

        {/* Learning Rate */}
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1">
            Learning Rate: <span className="text-emerald-400">{config.learning_rate}</span>
          </label>
          <div className="flex items-center gap-2">
            <input
              type="range"
              min="0.0000001"
              max="0.01"
              step="0.0000001"
              value={config.learning_rate}
              onChange={e => handleConfigChange('learning_rate', parseFloat(e.target.value))}
              className="flex-1 h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-emerald-500"
            />
            <input
              type="text"
              value={config.learning_rate}
              onChange={e => {
                const val = parseFloat(e.target.value)
                if (!isNaN(val) && val > 0 && val <= 0.01) {
                  handleConfigChange('learning_rate', val)
                }
              }}
              className="w-24 bg-gray-900 border border-gray-600 rounded text-xs text-white px-2 py-1 font-mono focus:outline-none focus:border-emerald-500"
              title="Enter a learning rate value between 0 and 0.01"
            />
          </div>
          <div className="flex justify-between text-[10px] text-gray-500">
            <span>1e-7</span>
            <span>Common: 1e-4, 2e-4, 1e-3</span>
            <span>0.01</span>
          </div>
        </div>

        {/* Epochs */}
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1">
            Epochs: <span className="text-emerald-400">{config.epochs}</span>
          </label>
          <input
            type="range"
            min="1"
            max="200"
            step="1"
            value={config.epochs}
            onChange={e => handleConfigChange('epochs', parseInt(e.target.value, 10))}
            className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-emerald-500"
          />
          <div className="flex justify-between text-[10px] text-gray-500">
            <span>1</span>
            <span>200</span>
          </div>
        </div>

        {/* Preview Interval */}
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1">
            Preview Interval: <span className="text-emerald-400">every {config.preview_interval} epoch{config.preview_interval !== 1 ? 's' : ''}</span>
          </label>
          <input
            type="range"
            min="1"
            max="50"
            step="1"
            value={config.preview_interval}
            onChange={e => handleConfigChange('preview_interval', parseInt(e.target.value, 10))}
            className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-emerald-500"
          />
          <div className="flex justify-between text-[10px] text-gray-500">
            <span>1</span>
            <span>50</span>
          </div>
        </div>

        {/* Output Format */}
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1">Output Format</label>
          <select
            value={config.output_format}
            onChange={e => handleConfigChange('output_format', e.target.value)}
            className="w-full bg-gray-800 border border-gray-600 rounded text-sm text-white px-3 py-2 focus:outline-none focus:border-emerald-500"
          >
            {OUTPUT_FORMATS.map(fmt => (
              <option key={fmt} value={fmt}>{fmt}</option>
            ))}
          </select>
        </div>

        {/* LoRA Strength */}
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1">
            LoRA Strength: <span className="text-emerald-400">{config.lora_strength.toFixed(2)}</span>
          </label>
          <input
            type="range"
            min="0.1"
            max="2.0"
            step="0.05"
            value={config.lora_strength}
            onChange={e => handleConfigChange('lora_strength', parseFloat(e.target.value))}
            className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-emerald-500"
          />
          <div className="flex justify-between text-[10px] text-gray-500">
            <span>0.1</span>
            <span>2.0</span>
          </div>
        </div>

        {/* Custom Args (advanced) */}
        <details className="border border-gray-700 rounded-lg">
          <summary className="text-xs text-gray-400 px-3 py-2 cursor-pointer hover:text-white transition-colors">
            Advanced: Custom Training Arguments (JSON)
          </summary>
          <div className="p-3">
            <textarea
              value={customArgs}
              onChange={e => setCustomArgs(e.target.value)}
              rows={3}
              className="w-full bg-gray-900 border border-gray-600 rounded text-xs text-white px-2 py-1.5 font-mono resize-none focus:outline-none focus:border-emerald-500"
              placeholder='{"network_dim": 32, "network_alpha": 16}'
            />
            <p className="text-[10px] text-gray-500 mt-1">
              Optional JSON object with additional training arguments
            </p>
          </div>
        </details>
      </div>

      {/* Create Job Button */}
      <button
        onClick={handleCreateJob}
        disabled={creating || !isReady}
        className="w-full px-4 py-2.5 text-sm font-medium rounded-lg transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed bg-emerald-700 hover:bg-emerald-600 text-emerald-100"
        title={!isReady ? 'Dataset must be ready (≥10 accepted images, all with captions)' : 'Start LoRA training'}
      >
        {creating ? (
          <>
            <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-gray-600 border-t-emerald-400 mr-2 align-middle" />
            Creating Job...
          </>
        ) : (
          '🚀 Create Training Job'
        )}
      </button>

      {/* Existing Jobs */}
      {jobs.length > 0 && (
        <div className="mt-4 pt-3 border-t border-gray-700">
          <h5 className="text-xs font-semibold text-gray-400 mb-2">Training Jobs</h5>
          <div className="space-y-2">
            {(showAllJobs ? jobs : jobs.slice(0, 5)).map(job => (
              <div
                key={job.job_id}
                className="flex items-center justify-between bg-gray-800 border border-gray-700 rounded-lg px-3 py-2"
              >
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-medium px-1.5 py-0.5 rounded ${
                    job.status === 'pending' ? 'bg-yellow-900/50 text-yellow-300' :
                    job.status === 'running' ? 'bg-blue-900/50 text-blue-300' :
                    job.status === 'completed' ? 'bg-emerald-900/50 text-emerald-300' :
                    'bg-red-900/50 text-red-300'
                  }`}>
                    {job.status}
                  </span>
                  <span className="text-xs text-gray-400">
                    LR: {job.learning_rate} · {job.epochs} epochs
                  </span>
                </div>
                <span className="text-[10px] text-gray-500 font-mono">{job.job_id}</span>
              </div>
            ))}
          </div>
          {jobs.length > 5 && (
            <button
              onClick={() => setShowAllJobs(prev => !prev)}
              className="mt-2 text-xs text-emerald-400 hover:text-emerald-300 transition-colors cursor-pointer"
            >
              {showAllJobs
                ? `Show recent 5 of ${jobs.length}`
                : `Show all ${jobs.length} jobs`}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

export default TrainingConfig