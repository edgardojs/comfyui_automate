import { useState, useEffect, useCallback, useRef } from 'react'
import {
  fetchLoRAJob,
  fetchLoRAJobStatus,
  fetchLoRAJobLogs,
  startLoRAJob,
  cancelLoRAJob,
  fetchTrainingBackends,
} from '../api/client'

/**
 * TrainingProgress — Training job monitoring and control UI.
 *
 * Props:
 * - jobId: the LoRA job ID to monitor
 * - showToast: callback to show a toast notification
 * - onJobComplete: optional callback when job reaches 'completed' status
 *
 * Features:
 * - Real-time status display with auto-refresh (5s interval for running jobs)
 * - Configuration summary
 * - Scrollable log output
 * - Cancel button for running jobs
 * - Start button for pending jobs
 * - Backend selector for starting jobs
 */
function TrainingProgress({ jobId, showToast, onJobComplete }) {
  // Job data
  const [job, setJob] = useState(null)
  const [loading, setLoading] = useState(true)

  // Training status (real-time)
  const [trainingStatus, setTrainingStatus] = useState(null)

  // Log output
  const [logs, setLogs] = useState('')
  const [logTail, setLogTail] = useState(100)

  // Backends
  const [backends, setBackends] = useState([])
  const [selectedBackend, setSelectedBackend] = useState('kohya_ss')

  // Actions
  const [starting, setStarting] = useState(false)
  const [cancelling, setCancelling] = useState(false)

  // Auto-refresh
  const [autoRefresh, setAutoRefresh] = useState(true)
  const refreshIntervalRef = useRef(null)

  // Log container ref for auto-scroll
  const logContainerRef = useRef(null)

  // Load job data
  const loadJob = useCallback(async () => {
    try {
      const data = await fetchLoRAJob(jobId)
      setJob(data)
      // If job completed or failed, stop auto-refresh
      if (data.status === 'completed' || data.status === 'failed') {
        setAutoRefresh(false)
        if (data.status === 'completed' && onJobComplete) {
          onJobComplete(data)
        }
      }
    } catch (err) {
      showToast(`❌ Failed to load job: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }, [jobId, showToast, onJobComplete])

  // Load training status
  const loadStatus = useCallback(async () => {
    try {
      const data = await fetchLoRAJobStatus(jobId)
      setTrainingStatus(data)
    } catch {
      // Status endpoint may not be available for all jobs
    }
  }, [jobId])

  // Load logs
  const loadLogs = useCallback(async () => {
    try {
      const data = await fetchLoRAJobLogs(jobId, logTail)
      setLogs(data.logs || '')
    } catch {
      // Logs may not be available for all jobs
    }
  }, [jobId, logTail])

  // Load backends
  useEffect(() => {
    async function loadBackends() {
      try {
        const data = await fetchTrainingBackends()
        setBackends(data || [])
      } catch {
        // Backends may not be available
      }
    }
    loadBackends()
  }, [])

  // Initial load
  useEffect(() => {
    loadJob()
  }, [loadJob])

  // Auto-refresh for running jobs
  useEffect(() => {
    if (!autoRefresh || !job) return

    // Clear existing interval
    if (refreshIntervalRef.current) {
      clearInterval(refreshIntervalRef.current)
    }

    // Only auto-refresh for running/pending jobs
    if (job.status === 'running' || job.status === 'pending') {
      refreshIntervalRef.current = setInterval(() => {
        loadJob()
        if (job.status === 'running') {
          loadStatus()
          loadLogs()
        }
      }, 5000)
    }

    return () => {
      if (refreshIntervalRef.current) {
        clearInterval(refreshIntervalRef.current)
      }
    }
  }, [autoRefresh, job?.status, loadJob, loadStatus, loadLogs])

  // Auto-scroll logs
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
    }
  }, [logs])

  // Start job
  const handleStart = useCallback(async () => {
    setStarting(true)
    try {
      await startLoRAJob(jobId, selectedBackend)
      showToast('✅ Training job started!')
      setAutoRefresh(true)
      await loadJob()
    } catch (err) {
      showToast(`❌ ${err.message}`)
    } finally {
      setStarting(false)
    }
  }, [jobId, selectedBackend, showToast, loadJob])

  // Cancel job
  const handleCancel = useCallback(async () => {
    if (!window.confirm('Are you sure you want to cancel this training job?')) return

    setCancelling(true)
    try {
      await cancelLoRAJob(jobId)
      showToast('🛑 Training job cancelled')
      setAutoRefresh(false)
      await loadJob()
    } catch (err) {
      showToast(`❌ ${err.message}`)
    } finally {
      setCancelling(false)
    }
  }, [jobId, showToast, loadJob])

  // Status badge color
  const statusColors = {
    pending: 'bg-yellow-900/50 text-yellow-300',
    running: 'bg-blue-900/50 text-blue-300',
    completed: 'bg-emerald-900/50 text-emerald-300',
    failed: 'bg-red-900/50 text-red-300',
  }

  if (loading) {
    return (
      <div className="mt-4 p-4 bg-gray-800 rounded-lg border border-gray-700">
        <div className="animate-pulse space-y-3">
          <div className="h-4 bg-gray-700 rounded w-1/3" />
          <div className="h-4 bg-gray-700 rounded w-2/3" />
          <div className="h-20 bg-gray-700 rounded" />
        </div>
      </div>
    )
  }

  if (!job) {
    return (
      <div className="mt-4 p-4 bg-gray-800 rounded-lg border border-gray-700">
        <p className="text-gray-400 text-sm">Job not found.</p>
      </div>
    )
  }

  return (
    <div className="mt-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-white">Training Progress</h4>
        <span className={`text-xs font-medium px-2 py-1 rounded ${statusColors[job.status] || 'bg-gray-700 text-gray-300'}`}>
          {job.status.toUpperCase()}
        </span>
      </div>

      {/* Configuration Summary */}
      <div className="bg-gray-800 border border-gray-700 rounded-lg p-3">
        <h5 className="text-xs font-semibold text-gray-400 mb-2">Configuration</h5>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
          <div className="text-gray-500">Job ID</div>
          <div className="text-gray-300 font-mono">{job.job_id}</div>
          <div className="text-gray-500">Base Model</div>
          <div className="text-gray-300">{job.config?.base_model || '—'}</div>
          <div className="text-gray-500">Learning Rate</div>
          <div className="text-gray-300">{job.config?.learning_rate || '—'}</div>
          <div className="text-gray-500">Epochs</div>
          <div className="text-gray-300">{job.config?.epochs || '—'}</div>
          <div className="text-gray-500">LoRA Strength</div>
          <div className="text-gray-300">{job.config?.lora_strength || '—'}</div>
          <div className="text-gray-500">Output Format</div>
          <div className="text-gray-300">{job.config?.output_format || '—'}</div>
          {job.config?.preset_id && (
            <>
              <div className="text-gray-500">Preset</div>
              <div className="text-gray-300">{job.config.preset_id}</div>
            </>
          )}
        </div>
      </div>

      {/* Real-time Status (for running jobs) */}
      {trainingStatus && job.status === 'running' && (
        <div className="bg-gray-800 border border-blue-900/50 rounded-lg p-3">
          <h5 className="text-xs font-semibold text-blue-400 mb-2">Process Status</h5>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
            <div className="text-gray-500">Running</div>
            <div className="text-blue-300">{trainingStatus.is_running ? 'Yes' : 'No'}</div>
            {trainingStatus.pid && (
              <>
                <div className="text-gray-500">PID</div>
                <div className="text-blue-300 font-mono">{trainingStatus.pid}</div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex gap-2">
        {job.status === 'pending' && (
          <div className="flex items-center gap-2 w-full">
            {backends.length > 0 && (
              <select
                value={selectedBackend}
                onChange={e => setSelectedBackend(e.target.value)}
                className="bg-gray-800 border border-gray-600 rounded text-xs text-white px-2 py-1.5 focus:outline-none focus:border-emerald-500"
              >
                {backends.map(b => (
                  <option key={b.id} value={b.id}>{b.label}</option>
                ))}
              </select>
            )}
            <button
              onClick={handleStart}
              disabled={starting}
              className="flex-1 px-4 py-2 text-sm font-medium rounded-lg transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed bg-emerald-700 hover:bg-emerald-600 text-emerald-100"
            >
              {starting ? (
                <>
                  <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-gray-600 border-t-emerald-400 mr-2 align-middle" />
                  Starting...
                </>
              ) : (
                '▶ Start Training'
              )}
            </button>
          </div>
        )}
        {job.status === 'running' && (
          <button
            onClick={handleCancel}
            disabled={cancelling}
            className="flex-1 px-4 py-2 text-sm font-medium rounded-lg transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed bg-red-800 hover:bg-red-700 text-red-100"
          >
            {cancelling ? 'Cancelling...' : '🛑 Cancel Training'}
          </button>
        )}
      </div>

      {/* Log Output */}
      {(job.status === 'running' || job.log_output) && (
        <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
          <div className="flex items-center justify-between px-3 py-2 bg-gray-800 border-b border-gray-700">
            <h5 className="text-xs font-semibold text-gray-400">Training Log</h5>
            <div className="flex items-center gap-2">
              <label className="text-[10px] text-gray-500">
                Last
                <select
                  value={logTail}
                  onChange={e => setLogTail(Number(e.target.value))}
                  className="ml-1 bg-gray-900 border border-gray-600 rounded text-[10px] text-white px-1 py-0.5"
                >
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                  <option value={500}>500</option>
                  <option value={1000}>1000</option>
                </select>
                lines
              </label>
              {job.status === 'running' && (
                <button
                  onClick={loadLogs}
                  className="text-[10px] text-emerald-400 hover:text-emerald-300 transition-colors cursor-pointer"
                >
                  ↻ Refresh
                </button>
              )}
            </div>
          </div>
          <div
            ref={logContainerRef}
            className="p-3 max-h-64 overflow-y-auto font-mono text-[11px] text-gray-300 whitespace-pre-wrap"
          >
            {logs || job.log_output || 'No log output available.'}
          </div>
        </div>
      )}

      {/* Auto-refresh indicator */}
      {job.status === 'running' && autoRefresh && (
        <div className="flex items-center gap-2 text-[10px] text-gray-500">
          <span className="inline-block h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
          Auto-refreshing every 5 seconds
          <button
            onClick={() => setAutoRefresh(false)}
            className="text-gray-400 hover:text-white transition-colors cursor-pointer"
          >
            Pause
          </button>
        </div>
      )}

      {/* Timestamps */}
      <div className="text-[10px] text-gray-600 space-y-0.5">
        {job.created_at && (
          <div>Created: {new Date(job.created_at).toLocaleString()}</div>
        )}
        {job.updated_at && (
          <div>Updated: {new Date(job.updated_at).toLocaleString()}</div>
        )}
      </div>
    </div>
  )
}

export default TrainingProgress