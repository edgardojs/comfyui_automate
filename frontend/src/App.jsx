import { useState, useCallback, useRef, useEffect } from 'react'
import AttributePanel from './components/AttributePanel'
import PromptOptions from './components/PromptOptions'
import PromptResults from './components/PromptResults'
import PresetManager from './components/PresetManager'
import PromptHistory from './components/PromptHistory'
import ComfyUISettings from './pages/ComfyUISettings'
import CharactersPage from './pages/CharactersPage'
import ErrorBoundary from './components/ErrorBoundary'
import { generatePrompts, submitToComfyUI, fetchComfyUIHistory, buildComfyUIImageUrl, fetchComfyUIClientId, saveComfyUIImages, fetchHistory } from './api/client'
import { loadComfyUISettings, flushComfyUISettings } from './api/comfyuiSettings'
import { ComfyUIWebSocket } from './api/comfyuiWs'
import PoseBatchGenerator from './components/PoseBatchGenerator'

/**
 * App — Root component for the Sprite Prompt Generator.
 *
 * Manages global state:
 * - selected attributes (category → attribute ID)
 * - locked fields (set of category IDs)
 * - generation options (variation count, template, negative profile)
 * - generated prompt results
 * - current page (Generate, Presets, History, Settings)
 */
function App() {
  // --- Page navigation ---
  const [currentPage, setCurrentPage] = useState('generate')

  // --- Attribute state ---
  const [attributes, setAttributes] = useState({})
  const [lockedFields, setLockedFields] = useState([])

  // --- Generation options ---
  const [variationCount, setVariationCount] = useState(1)
  const [templateId, setTemplateId] = useState('front_view_sprite')
  const [negativeProfileId, setNegativeProfileId] = useState('general_sprite_cleanup')

  // --- LoRA state ---
  const [loraSelection, setLoraSelection] = useState(null) // { jobId, characterId, characterName, triggerToken, recommendedStrength }

  // --- Generate mode tab ---
  const [generateMode, setGenerateMode] = useState('single') // 'single' or 'batch'

  // --- Results state ---
  const [results, setResults] = useState(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [error, setError] = useState(null)

  // --- Toast state ---
  const [toast, setToast] = useState(null)
  const toastTimerRef = useRef(null)

  // --- ComfyUI state ---
  const [comfyUISubmitting, setComfyUISubmitting] = useState(false)
  const [comfyUIResult, setComfyUIResult] = useState(null) // { index, success, message, promptId }

  // --- ComfyUI generation progress state ---
  const [comfyUIProgress, setComfyUIProgress] = useState(null)
  // { promptId, status: 'connecting'|'connected'|'generating'|'done'|'error', step, maxStep, images, errorMessage, nodeId }

  // --- ComfyUI persistent images state ---
  // Stores generated images keyed by history_id so they survive across re-renders,
  // state resets, and page refreshes. Value is array of { filename, subfolder, type, url }.
  // Also persisted to localStorage so images survive page refreshes.
  const [comfyUIImages, setComfyUIImages] = useState(() => {
    try {
      const stored = localStorage.getItem('comfyui_images')
      if (stored) {
        const parsed = JSON.parse(stored)
        if (typeof parsed === 'object' && parsed !== null) return parsed
      }
    } catch { /* ignore parse errors */ }
    return {}
  })

  const comfyUIWsRef = useRef(null)
  const comfyUIPollRef = useRef(null)

  // Lift ComfyUI settings to App-level state so handleSendToComfyUI
  // doesn't need to read from localStorage on every call
  const [comfyUISettings, setComfyUISettings] = useState(() => loadComfyUISettings())

  // Persist comfyUIImages to localStorage whenever it changes
  useEffect(() => {
    try {
      localStorage.setItem('comfyui_images', JSON.stringify(comfyUIImages))
    } catch { /* ignore storage errors */ }
  }, [comfyUIImages])

  // On startup, load recent history entries that have ComfyUI images
  // so they appear on the Generate page even after a page refresh
  useEffect(() => {
    ;(async () => {
      try {
        const history = await fetchHistory({ limit: 50 })
        if (history?.items) {
          const imagesFromHistory = {}
          history.items.forEach((item) => {
            if (item.comfyui_images && item.comfyui_images.length > 0) {
              // Key by history_id so images persist across different prompt generations
              imagesFromHistory[item.id] = item.comfyui_images
            }
          })
          if (Object.keys(imagesFromHistory).length > 0) {
            setComfyUIImages(prev => ({ ...prev, ...imagesFromHistory }))
          }
        }
      } catch { /* ignore — images will load on next generation */ }
    })()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Flush ComfyUI settings to localStorage before the page unloads.
  // This ensures settings are never lost even if the user closes the tab
  // or navigates away before a React re-render completes.
  useEffect(() => {
    const handleBeforeUnload = () => {
      flushComfyUISettings()
    }
    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload)
    }
  }, [])

  // Startup reconciliation: if the App-level comfyUISettings state
  // differs from what's in localStorage, re-read localStorage.
  // This handles the case where another tab or a previous session
  // saved settings that are newer than the initial React state.
  useEffect(() => {
    const stored = loadComfyUISettings()
    // Only update if the stored settings differ from current state
    // (comparing JSON strings to avoid deep-equal dependency)
    if (JSON.stringify(stored) !== JSON.stringify(comfyUISettings)) {
      setComfyUISettings(stored)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
      if (comfyUIWsRef.current) comfyUIWsRef.current.disconnect()
      if (comfyUIPollRef.current) clearTimeout(comfyUIPollRef.current)
    }
  }, [])

  const showToast = useCallback((message, duration = 2000) => {
    setToast(message)
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
    toastTimerRef.current = setTimeout(() => setToast(null), duration)
  }, [])

  // --- Handlers ---
  const handleAttributeChange = useCallback((categoryId, value) => {
    setAttributes(prev => ({ ...prev, [categoryId]: value || null }))
  }, [])

  const handleLockToggle = useCallback((categoryId) => {
    setLockedFields(prev =>
      prev.includes(categoryId)
        ? prev.filter(f => f !== categoryId)
        : [...prev, categoryId]
    )
  }, [])

  const handleRandomizeAll = useCallback(() => {
    setAttributes({})
    setLockedFields([])
  }, [])

  const handleClearAll = useCallback(() => {
    setAttributes({})
    setLockedFields([])
    setResults(null)
    setError(null)
    setLoraSelection(null)
    setComfyUIResult(null)
    setComfyUIProgress(null)
    setComfyUIImages({})
    localStorage.removeItem('comfyui_images')
  }, [])

  const handleGenerate = useCallback(async () => {
    setIsGenerating(true)
    setError(null)
    // Reset ComfyUI progress/result state when generating new prompts
    setComfyUIResult(null)
    setComfyUIProgress(null)
    try {
      const response = await generatePrompts({
        attributes,
        variationCount,
        lockedFields,
        templateId,
        negativeProfileId,
        loraTriggerToken: loraSelection?.triggerToken || undefined,
      })
      setResults(response)
      // Populate comfyUIImages from any previously saved ComfyUI images in the response
      // so they appear immediately without needing to re-send to ComfyUI
      // Key by history_id for stable persistence across page refreshes
      if (response?.items) {
        const existingImages = {}
        response.items.forEach((item) => {
          if (item.history_id && item.comfyui_images && item.comfyui_images.length > 0) {
            existingImages[item.history_id] = item.comfyui_images
          }
        })
        if (Object.keys(existingImages).length > 0) {
          setComfyUIImages(prev => ({ ...prev, ...existingImages }))
        }
      }
    } catch (err) {
      setError(err.message || 'Failed to generate prompts')
      setResults(null)
    } finally {
      setIsGenerating(false)
    }
  }, [attributes, variationCount, lockedFields, templateId, negativeProfileId, loraSelection])

  const handleCopy = useCallback(async (text, label = 'Prompt') => {
    try {
      await navigator.clipboard.writeText(text)
      showToast(`${label} copied!`)
    } catch {
      // Fallback for older browsers or non-HTTPS contexts
      try {
        const textarea = document.createElement('textarea')
        textarea.value = text
        textarea.style.position = 'fixed'
        textarea.style.opacity = '0'
        document.body.appendChild(textarea)
        textarea.select()
        document.execCommand('copy')
        document.body.removeChild(textarea)
        showToast(`${label} copied!`)
      } catch {
        showToast(`❌ Copy failed — please copy manually`)
      }
    }
  }, [showToast])

  const handleSendToComfyUI = useCallback(async (item) => {
    // Use App-level state instead of reading from localStorage on every call
    const settings = comfyUISettings

    if (!settings.serverUrl || !settings.workflowJson || !settings.positiveNodeId) {
      showToast('⚠️ Configure ComfyUI settings first (Settings page)')
      return
    }

    let workflowObj
    try {
      workflowObj = typeof settings.workflowJson === 'string'
        ? JSON.parse(settings.workflowJson)
        : settings.workflowJson
    } catch {
      showToast('❌ Invalid workflow JSON in settings')
      return
    }

    setComfyUISubmitting(true)
    setComfyUIResult(null)
    setComfyUIProgress(null)
    // Note: we do NOT reset comfyUIImages here so previously generated images persist

    // Clean up any previous WebSocket connection
    if (comfyUIWsRef.current) {
      comfyUIWsRef.current.disconnect()
      comfyUIWsRef.current = null
    }
    if (comfyUIPollRef.current) {
      clearTimeout(comfyUIPollRef.current)
      comfyUIPollRef.current = null
    }

    try {
      const nodeMapping = {
        positive_node_id: settings.positiveNodeId || '',
        positive_input_name: settings.positiveInputName || 'text',
        negative_node_id: settings.negativeNodeId || '',
        negative_input_name: settings.negativeInputName || 'text',
      }
      if (settings.seedNodeId) {
        nodeMapping.seed_node_id = settings.seedNodeId
        // Only send seed_input_name if explicitly set; otherwise let the backend auto-detect
        // (e.g. "noise_seed" for RandomNoise nodes, "seed" for KSampler nodes)
        if (settings.seedInputName) {
          nodeMapping.seed_input_name = settings.seedInputName
        }
      }

      // Get a client ID for WebSocket tracking
      let clientId
      try {
        clientId = await fetchComfyUIClientId()
      } catch {
        clientId = crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`
      }

      const result = await submitToComfyUI({
        serverUrl: settings.serverUrl,
        workflowJson: workflowObj,
        positivePrompt: item.positive_prompt,
        negativePrompt: item.negative_prompt,
        nodeMapping,
        clientId,
      })

      // Use stable index based on positive_prompt content instead of object reference
      // Clamp to >= 0 to handle the case where findIndex returns -1 (not found)
      const index = Math.max(0, results?.items?.findIndex(i => i.positive_prompt === item.positive_prompt) ?? 0)
      const historyId = item.history_id
      setComfyUIResult({
        index,
        historyId,
        success: result.success,
        message: result.message,
        promptId: result.prompt_id,
      })

      if (result.success && result.prompt_id) {
        // Start tracking progress via WebSocket
        setComfyUIProgress({
          promptId: result.prompt_id,
          status: 'connecting',
          step: 0,
          maxStep: 0,
          images: [],
          errorMessage: null,
          nodeId: null,
        })

        try {
          const ws = new ComfyUIWebSocket(clientId, settings.serverUrl)

          ws.onStatusChange = (status) => {
            // Don't overwrite 'done', 'error', or 'fetching' statuses with connection status changes
            // (e.g., WebSocket disconnecting after generation is complete)
            setComfyUIProgress(prev => {
              if (!prev) return null
              if (prev.status === 'done' || prev.status === 'error' || prev.status === 'fetching') return prev
              return { ...prev, status: status === 'connected' ? 'generating' : status }
            })
          }

          ws.onProgress = (step, maxStep) => {
            setComfyUIProgress(prev => prev ? { ...prev, step, maxStep, status: 'generating' } : null)
          }

          ws.onNodeExecuting = (nodeId, promptId) => {
            setComfyUIProgress(prev => prev ? { ...prev, nodeId: nodeId || null } : null)
          }

          ws.onComplete = async (promptId) => {
            setComfyUIProgress(prev => prev ? { ...prev, status: 'fetching', step: prev.maxStep, maxStep: prev.maxStep } : null)

            // Fetch history to get output images — retry up to 5 times with a short delay
            // because ComfyUI may not have finished writing output to history yet
            // when the 'executing node=null' message arrives
            const MAX_RETRIES = 5
            const RETRY_DELAY_MS = 1000
            let images = []
            let fetchSuccess = false

            for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
              try {
                const history = await fetchComfyUIHistory(promptId, settings.serverUrl)
                if (history.outputs?.images?.length > 0) {
                  images = history.outputs.images.map(img => ({
                    ...img,
                    url: buildComfyUIImageUrl(img, settings.serverUrl),
                  }))
                  fetchSuccess = true
                  break
                }
                // History returned but no images yet — retry after delay
                if (attempt < MAX_RETRIES) {
                  await new Promise(resolve => setTimeout(resolve, RETRY_DELAY_MS))
                }
              } catch {
                // History fetch failed — retry after delay
                if (attempt < MAX_RETRIES) {
                  await new Promise(resolve => setTimeout(resolve, RETRY_DELAY_MS))
                }
              }
            }

            setComfyUIProgress(prev => prev ? { ...prev, status: 'done', images } : { promptId, status: 'done', step: 0, maxStep: 0, images, errorMessage: null, nodeId: null })
            // Also store images persistently so they survive state resets
            // Key by history_id for stable persistence across page refreshes
            if (images.length > 0) {
              const historyId = results?.items?.[index]?.history_id
              if (historyId) {
                setComfyUIImages(prev => ({ ...prev, [historyId]: images }))
                // Save images to history so they appear in the History page
                try {
                  await saveComfyUIImages(historyId, {
                    comfyuiPromptId: promptId,
                    comfyuiImages: images,
                  })
                } catch {
                  // Non-critical — images still show in current session
                }
              } else {
                // Fallback: key by index if no history_id yet
                setComfyUIImages(prev => ({ ...prev, [index]: images }))
              }
            }
            if (fetchSuccess && images.length > 0) {
              showToast('✅ Image generated! Check the results below.')
            } else {
              showToast('✅ Generation complete (could not fetch images)')
            }

            // Disconnect WebSocket after completion
            ws.disconnect()
          }

          ws.onError = (errorMessage) => {
            // Only show error for generation errors, not connection failures
            // Connection failures are handled by the catch block below (fallback to polling)
            if (comfyUIWsRef.current === ws) {
              // This is still our active WebSocket — it's a generation error
              setComfyUIProgress(prev => prev ? { ...prev, status: 'error', errorMessage } : { promptId: result.prompt_id, status: 'error', step: 0, maxStep: 0, images: [], errorMessage, nodeId: null })
              showToast('❌ ComfyUI generation error: ' + errorMessage)
              ws.disconnect()
            }
          }

          comfyUIWsRef.current = ws
          await ws.connect()
        } catch {
          // WebSocket connection failed — fall back to polling
          setComfyUIProgress(prev => prev ? { ...prev, status: 'polling' } : null)

          const MAX_POLL_ATTEMPTS = 40 // 40 × 3s = ~2 minutes max
          let pollAttempts = 0

          const pollStatus = async () => {
            pollAttempts++
            if (pollAttempts > MAX_POLL_ATTEMPTS) {
              setComfyUIProgress(prev => prev ? { ...prev, status: 'error', errorMessage: 'Generation timed out. Try again or check ComfyUI status.' } : { promptId: result.prompt_id, status: 'error', step: 0, maxStep: 0, images: [], errorMessage: 'Generation timed out. Try again or check ComfyUI status.', nodeId: null })
              showToast('❌ Generation timed out after 2 minutes')
              return // Stop polling
            }
            try {
              const history = await fetchComfyUIHistory(result.prompt_id, settings.serverUrl)
              if (history.status === 'done' && history.outputs?.images?.length > 0) {
                const images = history.outputs.images.map(img => ({
                  ...img,
                  url: buildComfyUIImageUrl(img, settings.serverUrl),
                }))
                setComfyUIProgress(prev => prev ? { ...prev, status: 'done', images } : { promptId: result.prompt_id, status: 'done', step: 0, maxStep: 0, images, errorMessage: null, nodeId: null })
                // Also store images persistently so they survive state resets
                // Key by history_id for stable persistence across page refreshes
                const historyId = results?.items?.[index]?.history_id
                if (historyId) {
                  setComfyUIImages(prev => ({ ...prev, [historyId]: images }))
                  // Save images to history so they appear in the History page
                  try {
                    await saveComfyUIImages(historyId, {
                      comfyuiPromptId: result.prompt_id,
                      comfyuiImages: images,
                    })
                  } catch {
                    // Non-critical — images still show in current session
                  }
                } else {
                  // Fallback: key by index if no history_id yet
                  setComfyUIImages(prev => ({ ...prev, [index]: images }))
                }
                showToast('✅ Image generated! Check the results below.')
                return // Stop polling
              }
              if (history.status === 'done') {
                // Done but no images yet — ComfyUI may still be writing output.
                // Retry a few times before giving up.
                if (pollAttempts < 5) {
                  // Retry after a short delay
                  comfyUIPollRef.current = setTimeout(pollStatus, 2000)
                  return
                }
                // Still no images after retries — mark as done with empty images
                setComfyUIProgress(prev => prev ? { ...prev, status: 'done', images: [] } : { promptId: result.prompt_id, status: 'done', step: 0, maxStep: 0, images: [], errorMessage: null, nodeId: null })
                showToast('✅ Generation complete (no images found in output)')
                return // Stop polling
              }
              // Still running — poll again in 3 seconds
              comfyUIPollRef.current = setTimeout(pollStatus, 3000)
            } catch {
              // Poll failed — try again in 3 seconds (up to max attempts)
              comfyUIPollRef.current = setTimeout(pollStatus, 3000)
            }
          }
          // Start polling after a short delay to give ComfyUI time to start
          comfyUIPollRef.current = setTimeout(pollStatus, 2000)
        }
      }

      showToast(result.success ? '🚀 Sent to ComfyUI!' : '❌ ComfyUI submission failed')
    } catch (err) {
      const index = Math.max(0, results?.items?.findIndex(i => i.positive_prompt === item.positive_prompt) ?? 0)
      const historyId = item.history_id
      setComfyUIResult({
        index,
        historyId,
        success: false,
        message: err.message || 'Failed to submit to ComfyUI',
        promptId: null,
      })
      showToast('❌ ComfyUI error: ' + (err.message || 'Unknown error'))
    } finally {
      setComfyUISubmitting(false)
    }
  }, [showToast, results, comfyUISettings])

  const handleLoadPreset = useCallback(({ attributes: attrs, lockedFields: locks, templateId: tmpl, negativeProfileId: prof }) => {
    setAttributes(attrs)
    setLockedFields(locks)
    setTemplateId(tmpl)
    setNegativeProfileId(prof)
    setCurrentPage('generate')
  }, [])

  // --- Navigation items ---
  const navItems = [
    { id: 'generate', label: 'Generate', icon: '🎲' },
    { id: 'characters', label: 'Characters', icon: '🧙' },
    { id: 'presets', label: 'Presets', icon: '💾' },
    { id: 'history', label: 'History', icon: '📜' },
    { id: 'settings', label: 'Settings', icon: '⚙️' },
  ]

  return (
    <ErrorBoundary>
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Header */}
      <header className="sticky top-0 z-30 border-b border-gray-800 bg-gray-900/95 backdrop-blur-sm px-6 py-3">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
            <span className="text-2xl">🎮</span>
            <span>Sprite Prompt Generator</span>
          </h1>
          <nav className="flex gap-1">
            {navItems.map(item => (
              <button
                key={item.id}
                onClick={() => setCurrentPage(item.id)}
                className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors cursor-pointer
                  ${currentPage === item.id
                    ? 'bg-gray-700 text-white'
                    : 'text-gray-400 hover:text-white hover:bg-gray-800'
                  }`}
              >
                <span className="mr-1.5">{item.icon}</span>
                {item.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main className="mx-auto max-w-7xl px-6 py-6">
        {currentPage === 'generate' && (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            {/* Attribute Selection Panel */}
            <aside className="lg:col-span-1">
              <AttributePanel
                attributes={attributes}
                lockedFields={lockedFields}
                onAttributeChange={handleAttributeChange}
                onLockToggle={handleLockToggle}
                onRandomizeAll={handleRandomizeAll}
                onClearAll={handleClearAll}
                loraSelection={loraSelection}
                onLoRAChange={setLoraSelection}
              />
            </aside>

            {/* Prompt Options & Results */}
            <section className="flex flex-col gap-6 lg:col-span-2">
              {/* Mode Tabs */}
              <div className="flex gap-2">
                <button
                  onClick={() => { setGenerateMode('single'); handleGenerate(); }}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors cursor-pointer ${
                    generateMode === 'single'
                      ? 'bg-indigo-600 text-white'
                      : 'bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700 border border-gray-700'
                  }`}
                >
                  🎲 Single Generate
                </button>
                <button
                  onClick={() => setGenerateMode('batch')}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors cursor-pointer ${
                    generateMode === 'batch'
                      ? 'bg-indigo-600 text-white'
                      : 'bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700 border border-gray-700'
                  }`}
                >
                  🎭 Pose Batch
                </button>
              </div>

              {generateMode === 'single' ? (<>
              <PromptOptions
                variationCount={variationCount}
                templateId={templateId}
                negativeProfileId={negativeProfileId}
                onVariationCountChange={setVariationCount}
                onTemplateIdChange={setTemplateId}
                onNegativeProfileIdChange={setNegativeProfileId}
                onGenerate={handleGenerate}
                isGenerating={isGenerating}
              />
              <PromptResults
                results={results}
                error={error}
                isGenerating={isGenerating}
                onCopy={handleCopy}
                onSendToComfyUI={handleSendToComfyUI}
                comfyUISubmitting={comfyUISubmitting}
                comfyUIResult={comfyUIResult}
                comfyUIProgress={comfyUIProgress}
                comfyUIImages={comfyUIImages}
                loraTriggerToken={loraSelection?.triggerToken || null}
              />
              </>) : (
              <PoseBatchGenerator
                loraSelection={loraSelection}
                attributes={attributes}
                lockedFields={lockedFields}
                templateId={templateId}
                negativeProfileId={negativeProfileId}
                characterName={loraSelection?.characterName || null}
                comfyUISettings={comfyUISettings}
                onCopy={handleCopy}
                showToast={showToast}
              />
              )}
            </section>
          </div>
        )}

        {currentPage === 'characters' && (
          <CharactersPage showToast={showToast} />
        )}

        {currentPage === 'presets' && (
          <PresetManager
            currentAttributes={attributes}
            currentLockedFields={lockedFields}
            currentTemplateId={templateId}
            currentNegativeProfileId={negativeProfileId}
            onLoadPreset={handleLoadPreset}
            showToast={showToast}
          />
        )}

        {currentPage === 'history' && (
          <PromptHistory
            onCopy={handleCopy}
            showToast={showToast}
          />
        )}

        {currentPage === 'settings' && (
          <ComfyUISettings onSettingsChange={setComfyUISettings} />
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-800 px-6 py-3 text-center text-xs text-gray-600">
        ComfyUI Sprite Character Prompt Generator — MVP
      </footer>

      {/* Toast notification */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white shadow-lg animate-fade-in">
          {toast}
        </div>
      )}
    </div>
    </ErrorBoundary>
  )
}

export default App
