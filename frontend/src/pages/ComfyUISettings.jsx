import { useState, useCallback, useEffect } from 'react'

/**
 * ComfyUISettings — Page for configuring ComfyUI connection settings.
 *
 * Allows the user to:
 * - Set the ComfyUI server URL and test connectivity
 * - Paste or upload a workflow JSON
 * - Map positive, negative, and seed nodes
 * - Save all settings to localStorage
 *
 * ComfyUI is entirely optional — the prompt generator works without it.
 */

const STORAGE_KEY = 'comfyui_settings'

const DEFAULT_SETTINGS = {
  serverUrl: 'http://127.0.0.1:8188',
  workflowJson: '',
  positiveNodeId: '',
  positiveInputName: 'text',
  negativeNodeId: '',
  negativeInputName: 'text',
  seedNodeId: '',
  seedInputName: 'seed',
}

function loadSettings() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      return { ...DEFAULT_SETTINGS, ...JSON.parse(stored) }
    }
  } catch {
    // Ignore parse errors
  }
  return { ...DEFAULT_SETTINGS }
}

function saveSettings(settings) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
}

function ComfyUISettings() {
  const [settings, setSettings] = useState(loadSettings)
  const [testResult, setTestResult] = useState(null)
  const [isTesting, setIsTesting] = useState(false)
  const [validationResult, setValidationResult] = useState(null)
  const [isValidating, setIsValidating] = useState(false)
  const [saveMessage, setSaveMessage] = useState('')
  const [fileError, setFileError] = useState('')

  // Auto-save on change
  useEffect(() => {
    saveSettings(settings)
  }, [settings])

  const handleChange = useCallback((field, value) => {
    setSettings(prev => ({ ...prev, [field]: value }))
    setSaveMessage('')
  }, [])

  const handleTestConnection = useCallback(async () => {
    setIsTesting(true)
    setTestResult(null)
    try {
      const res = await fetch('/api/comfyui/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ server_url: settings.serverUrl }),
      })
      const data = await res.json()
      setTestResult(data)
    } catch (err) {
      setTestResult({
        connected: false,
        message: `Request failed: ${err.message}`,
      })
    } finally {
      setIsTesting(false)
    }
  }, [settings.serverUrl])

  const handleValidateWorkflow = useCallback(async () => {
    if (!settings.workflowJson.trim()) {
      setValidationResult({ valid: false, issues: ['No workflow JSON provided.'], node_ids: [] })
      return
    }
    setIsValidating(true)
    setValidationResult(null)
    try {
      let workflowObj
      try {
        workflowObj = JSON.parse(settings.workflowJson)
      } catch {
        setValidationResult({
          valid: false,
          issues: ['Invalid JSON syntax. Please check your workflow JSON.'],
          node_ids: [],
        })
        setIsValidating(false)
        return
      }
      const res = await fetch('/api/comfyui/validate-workflow', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ workflow_json: workflowObj }),
      })
      const data = await res.json()
      setValidationResult(data)
    } catch (err) {
      setValidationResult({
        valid: false,
        issues: [`Validation request failed: ${err.message}`],
        node_ids: [],
      })
    } finally {
      setIsValidating(false)
    }
  }, [settings.workflowJson])

  const handleFileUpload = useCallback((e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setFileError('')
    const reader = new FileReader()
    reader.onload = (event) => {
      const text = event.target?.result
      if (typeof text === 'string') {
        // Validate it's parseable JSON
        try {
          JSON.parse(text)
          setSettings(prev => ({ ...prev, workflowJson: text }))
        } catch {
          setFileError('The uploaded file is not valid JSON.')
        }
      }
    }
    reader.onerror = () => {
      setFileError('Failed to read the file.')
    }
    reader.readAsText(file)
  }, [])

  const handleSave = useCallback(() => {
    saveSettings(settings)
    setSaveMessage('Settings saved!')
    setTimeout(() => setSaveMessage(''), 2000)
  }, [settings])

  const handleReset = useCallback(() => {
    setSettings({ ...DEFAULT_SETTINGS })
    setTestResult(null)
    setValidationResult(null)
    setSaveMessage('Settings reset to defaults.')
    setTimeout(() => setSaveMessage(''), 2000)
  }, [])

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h2 className="text-lg font-semibold text-white flex items-center gap-2">
          <span>⚙️</span> ComfyUI Settings
        </h2>
        <p className="mt-1 text-sm text-gray-400">
          Configure your ComfyUI connection. This is optional — the prompt generator works
          perfectly without ComfyUI. Only configure this if you want to send prompts directly
          to a ComfyUI workflow.
        </p>
      </div>

      {/* Server URL */}
      <section className="rounded-lg border border-gray-800 bg-gray-900 p-5">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">Server Connection</h3>
        <div className="flex gap-3 items-start">
          <div className="flex-1">
            <label className="block text-xs font-medium text-gray-500 mb-1">
              ComfyUI Server URL
            </label>
            <input
              type="url"
              value={settings.serverUrl}
              onChange={(e) => handleChange('serverUrl', e.target.value)}
              placeholder="http://127.0.0.1:8188"
              className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>
          <button
            onClick={handleTestConnection}
            disabled={isTesting || !settings.serverUrl.trim()}
            className="mt-5 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors cursor-pointer"
          >
            {isTesting ? 'Testing…' : 'Test Connection'}
          </button>
        </div>
        {testResult && (
          <div className={`mt-3 rounded-md p-3 text-sm ${
            testResult.connected
              ? 'bg-emerald-900/30 border border-emerald-700 text-emerald-300'
              : 'bg-red-900/30 border border-red-700 text-red-300'
          }`}>
            <span className="font-medium">{testResult.connected ? '✅' : '❌'}</span>{' '}
            {testResult.message}
          </div>
        )}
      </section>

      {/* Workflow JSON */}
      <section className="rounded-lg border border-gray-800 bg-gray-900 p-5">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">Workflow JSON</h3>
        <p className="text-xs text-gray-500 mb-3">
          Paste a ComfyUI workflow JSON or upload a file. Both API format and UI format
          (exported via "Save" in ComfyUI) are supported — UI-format workflows are
          automatically converted.
        </p>
        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">
              Upload Workflow File
            </label>
            <input
              type="file"
              accept=".json"
              onChange={handleFileUpload}
              className="block w-full text-sm text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-medium file:bg-gray-800 file:text-gray-300 hover:file:bg-gray-700 file:cursor-pointer cursor-pointer"
            />
            {fileError && (
              <p className="mt-1 text-xs text-red-400">{fileError}</p>
            )}
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">
              Or paste workflow JSON directly
            </label>
            <textarea
              value={settings.workflowJson}
              onChange={(e) => handleChange('workflowJson', e.target.value)}
              placeholder='{"3": {"class_type": "KSampler", "inputs": {...}}, ...}'
              rows={8}
              className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-xs text-gray-200 placeholder-gray-600 font-mono focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-y"
            />
          </div>
          <button
            onClick={handleValidateWorkflow}
            disabled={isValidating || !settings.workflowJson.trim()}
            className="rounded-md bg-gray-700 px-4 py-2 text-sm font-medium text-gray-300 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors cursor-pointer"
          >
            {isValidating ? 'Validating…' : 'Validate Workflow'}
          </button>
          {validationResult && (
            <div className={`rounded-md p-3 text-sm ${
              validationResult.valid
                ? 'bg-emerald-900/30 border border-emerald-700 text-emerald-300'
                : 'bg-amber-900/30 border border-amber-700 text-amber-300'
            }`}>
              {validationResult.valid ? (
                <p><span className="font-medium">✅ Valid workflow</span></p>
              ) : (
                <div>
                  <p className="font-medium">⚠️ Issues found:</p>
                  <ul className="list-disc list-inside mt-1">
                    {validationResult.issues.map((issue, i) => (
                      <li key={i}>{issue}</li>
                    ))}
                  </ul>
                </div>
              )}
              {validationResult.node_ids.length > 0 && (
                <div className="mt-2">
                  <p className="text-xs font-medium text-gray-400">Available nodes:</p>
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    {validationResult.node_ids.map((node) => (
                      <span
                        key={node.id}
                        className="inline-flex items-center rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-300 border border-gray-700"
                      >
                        <span className="text-indigo-400 mr-1">ID:{node.id}</span>
                        {node.class_type}
                        {node.title && node.title !== node.class_type && (
                          <span className="text-gray-500 ml-1">({node.title})</span>
                        )}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </section>

      {/* Node Mapping */}
      <section className="rounded-lg border border-gray-800 bg-gray-900 p-5">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">Node Mapping</h3>
        <p className="text-xs text-gray-500 mb-4">
          Map prompt text to specific nodes in your ComfyUI workflow. Use the node IDs from
          the validated workflow above.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Positive prompt node */}
          <div>
            <label className="block text-xs font-medium text-emerald-400 mb-1">
              Positive Prompt Node ID
            </label>
            <input
              type="text"
              value={settings.positiveNodeId}
              onChange={(e) => handleChange('positiveNodeId', e.target.value)}
              placeholder="e.g. 6"
              className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">
              Positive Input Name
            </label>
            <input
              type="text"
              value={settings.positiveInputName}
              onChange={(e) => handleChange('positiveInputName', e.target.value)}
              placeholder="text"
              className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          {/* Negative prompt node */}
          <div>
            <label className="block text-xs font-medium text-red-400 mb-1">
              Negative Prompt Node ID
            </label>
            <input
              type="text"
              value={settings.negativeNodeId}
              onChange={(e) => handleChange('negativeNodeId', e.target.value)}
              placeholder="e.g. 7"
              className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">
              Negative Input Name
            </label>
            <input
              type="text"
              value={settings.negativeInputName}
              onChange={(e) => handleChange('negativeInputName', e.target.value)}
              placeholder="text"
              className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          {/* Seed node (optional) */}
          <div>
            <label className="block text-xs font-medium text-amber-400 mb-1">
              Seed Node ID <span className="text-gray-600">(optional)</span>
            </label>
            <input
              type="text"
              value={settings.seedNodeId}
              onChange={(e) => handleChange('seedNodeId', e.target.value)}
              placeholder="e.g. 3"
              className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">
              Seed Input Name
            </label>
            <input
              type="text"
              value={settings.seedInputName}
              onChange={(e) => handleChange('seedInputName', e.target.value)}
              placeholder="seed"
              className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>
        </div>
      </section>

      {/* Actions */}
      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          className="rounded-md bg-indigo-600 px-5 py-2 text-sm font-medium text-white hover:bg-indigo-500 transition-colors cursor-pointer"
        >
          💾 Save Settings
        </button>
        <button
          onClick={handleReset}
          className="rounded-md bg-gray-700 px-5 py-2 text-sm font-medium text-gray-300 hover:bg-gray-600 transition-colors cursor-pointer"
        >
          🔄 Reset to Defaults
        </button>
        {saveMessage && (
          <span className="text-sm text-emerald-400">{saveMessage}</span>
        )}
      </div>

      {/* Info box */}
      <div className="rounded-lg border border-gray-800 bg-gray-900/50 p-4">
        <h4 className="text-xs font-semibold text-gray-400 mb-2">ℹ️ How to get your workflow JSON</h4>
        <ol className="text-xs text-gray-500 space-y-1 list-decimal list-inside">
          <li>Open ComfyUI and set up your workflow</li>
          <li>Click "Save" (UI format) or "Save (API format)" in the ComfyUI menu</li>
          <li>This downloads a JSON file — upload it here or paste the contents</li>
          <li>Use "Validate Workflow" to see available node IDs and titles</li>
          <li>Enter the node IDs for your positive/negative prompt nodes</li>
        </ol>
      </div>
    </div>
  )
}

export default ComfyUISettings