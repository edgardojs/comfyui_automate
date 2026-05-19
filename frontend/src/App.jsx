import { useState, useCallback, useRef, useEffect } from 'react'
import AttributePanel from './components/AttributePanel'
import PromptOptions from './components/PromptOptions'
import PromptResults from './components/PromptResults'
import PresetManager from './components/PresetManager'
import PromptHistory from './components/PromptHistory'
import ComfyUISettings from './pages/ComfyUISettings'
import CharactersPage from './pages/CharactersPage'
import ErrorBoundary from './components/ErrorBoundary'
import { generatePrompts, submitToComfyUI } from './api/client'
import { loadComfyUISettings } from './api/comfyuiSettings'
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

  // Lift ComfyUI settings to App-level state so handleSendToComfyUI
  // doesn't need to read from localStorage on every call
  const [comfyUISettings, setComfyUISettings] = useState(() => loadComfyUISettings())

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
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
  }, [])

  const handleGenerate = useCallback(async () => {
    setIsGenerating(true)
    setError(null)
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

    try {
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

      const result = await submitToComfyUI({
        serverUrl: settings.serverUrl,
        workflowJson: workflowObj,
        positivePrompt: item.positive_prompt,
        negativePrompt: item.negative_prompt,
        nodeMapping,
      })

      // Use stable index based on positive_prompt content instead of object reference
      const index = results?.items?.findIndex(i => i.positive_prompt === item.positive_prompt) ?? 0
      setComfyUIResult({
        index,
        success: result.success,
        message: result.message,
        promptId: result.prompt_id,
      })
      showToast(result.success ? '🚀 Sent to ComfyUI!' : '❌ ComfyUI submission failed')
    } catch (err) {
      const index = results?.items?.findIndex(i => i.positive_prompt === item.positive_prompt) ?? 0
      setComfyUIResult({
        index,
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
                  onClick={() => setGenerateMode('single')}
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
