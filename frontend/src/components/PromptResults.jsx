/**
 * PromptResults — Displays generated prompt pairs with copy buttons.
 *
 * Shows each variation as a card with positive/negative prompts,
 * copy buttons, and the resolved attributes used. Optionally includes
 * a "Send to ComfyUI" button when ComfyUI settings are configured.
 * When a LoRA trigger token is active, it is visually highlighted in
 * the positive prompt display.
 */
function PromptResults({ results, error, isGenerating, onCopy, onSendToComfyUI, comfyUISubmitting, comfyUIResult, comfyUIProgress, loraTriggerToken }) {
  // Loading state
  if (isGenerating && !results) {
    return (
      <div className="rounded-lg border border-gray-800 bg-gray-900 p-5">
        <div className="flex items-center justify-center gap-3 py-8 text-gray-400">
          <span className="inline-block h-5 w-5 animate-spin rounded-full border-2 border-gray-600 border-t-indigo-500" />
          <span>Generating prompts…</span>
        </div>
      </div>
    )
  }

  // Error state
  if (error) {
    return (
      <div className="rounded-lg border border-red-900 bg-gray-900 p-5">
        <div className="flex items-start gap-3 py-4">
          <span className="text-xl">⚠️</span>
          <div>
            <h3 className="text-sm font-semibold text-red-400">Generation Failed</h3>
            <p className="mt-1 text-sm text-gray-400">{error}</p>
          </div>
        </div>
      </div>
    )
  }

  // Empty state
  if (!results) {
    return (
      <div className="rounded-lg border border-gray-800 bg-gray-900 p-5">
        <div className="py-8 text-center">
          <span className="text-3xl">🎨</span>
          <h3 className="mt-3 text-sm font-semibold text-gray-400">No prompts yet</h3>
          <p className="mt-1 text-xs text-gray-600">
            Select attributes and click Generate to create sprite prompts.
          </p>
        </div>
      </div>
    )
  }

  const items = results?.items ?? []
  const generationId = results?.generation_id ?? ''

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">
          Generated Prompts
          <span className="ml-2 text-sm font-normal text-gray-500">
            ({items.length} {items.length === 1 ? 'variation' : 'variations'})
          </span>
        </h2>
        <span className="text-xs text-gray-600 font-mono">{generationId}</span>
      </div>

      {items.map((item, index) => (
        <div
          key={index}
          className="rounded-lg border border-gray-800 bg-gray-900 p-5"
        >
          {/* Variation header */}
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-300">
              Variation {index + 1}
            </h3>
            <div className="flex gap-1.5">
              <button
                onClick={() => onCopy(item.positive_prompt, 'Positive')}
                className="rounded bg-gray-800 px-2.5 py-1 text-xs font-medium text-gray-400 hover:bg-gray-700 hover:text-white transition-colors cursor-pointer border border-gray-700"
              >
                📋 Positive
              </button>
              <button
                onClick={() => onCopy(item.negative_prompt, 'Negative')}
                className="rounded bg-gray-800 px-2.5 py-1 text-xs font-medium text-gray-400 hover:bg-gray-700 hover:text-white transition-colors cursor-pointer border border-gray-700"
              >
                📋 Negative
              </button>
              <button
                onClick={() => onCopy(
                  `Positive: ${item.positive_prompt}\n\nNegative: ${item.negative_prompt}`,
                  'Both'
                )}
                className="rounded bg-indigo-600/20 px-2.5 py-1 text-xs font-medium text-indigo-300 hover:bg-indigo-600/30 transition-colors cursor-pointer border border-indigo-600/40"
              >
                📋 Both
              </button>
              {onSendToComfyUI && (
                <button
                  onClick={() => onSendToComfyUI(item)}
                  disabled={comfyUISubmitting}
                  className="rounded bg-purple-600/20 px-2.5 py-1 text-xs font-medium text-purple-300 hover:bg-purple-600/30 transition-colors cursor-pointer border border-purple-600/40 disabled:opacity-50 disabled:cursor-not-allowed"
                  title="Send this prompt to ComfyUI (configure in Settings)"
                >
                  {comfyUISubmitting ? '⏳ Sending…' : '🚀 ComfyUI'}
                </button>
              )}
            </div>
          </div>

          {/* Positive prompt */}
          <div className="mb-3">
            <label className="mb-1 block text-xs font-medium text-emerald-400 uppercase tracking-wider">
              Positive Prompt
              {loraTriggerToken && (
                <span className="ml-2 inline-flex items-center rounded bg-indigo-600/20 px-1.5 py-0.5 text-[10px] font-medium text-indigo-300 border border-indigo-600/30">
                  LoRA: <code className="ml-1 font-mono">{loraTriggerToken}</code>
                </span>
              )}
            </label>
            <div className="rounded-md bg-gray-800/50 border border-gray-700 p-3 text-sm text-gray-200 leading-relaxed select-all">
              {loraTriggerToken && item.positive_prompt.startsWith(loraTriggerToken + ',') ? (
                <>
                  <span className="rounded bg-indigo-600/25 px-1 py-0.5 text-indigo-300 font-medium font-mono">{loraTriggerToken}</span>
                  <span>{item.positive_prompt.slice(loraTriggerToken.length)}</span>
                </>
              ) : (
                item.positive_prompt
              )}
            </div>
          </div>

          {/* Negative prompt */}
          <div className="mb-3">
            <label className="mb-1 block text-xs font-medium text-red-400 uppercase tracking-wider">
              Negative Prompt
            </label>
            <div className="rounded-md bg-gray-800/50 border border-gray-700 p-3 text-sm text-gray-200 leading-relaxed select-all">
              {item.negative_prompt}
            </div>
          </div>

          {/* Resolved attributes */}
          <details className="group">
            <summary className="cursor-pointer text-xs text-gray-500 hover:text-gray-300 transition-colors">
              ▶ Resolved Attributes
            </summary>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {Object.entries(item.attributes || {}).map(([key, value]) => (
                <span
                  key={key}
                  className="inline-flex items-center rounded-full bg-gray-800 px-2.5 py-0.5 text-xs text-gray-400 border border-gray-700"
                >
                  <span className="text-gray-500 mr-1">{key}:</span>
                  {value}
                </span>
              ))}
            </div>
          </details>

          {/* ComfyUI submission result */}
          {comfyUIResult && comfyUIResult.index === index && (
            <div className={`mt-3 rounded-md p-2.5 text-xs ${
              comfyUIResult.success
                ? 'bg-emerald-900/30 border border-emerald-700 text-emerald-300'
                : 'bg-red-900/30 border border-red-700 text-red-300'
            }`}>
              <span className="font-medium">{comfyUIResult.success ? '✅' : '❌'}</span>{' '}
              {comfyUIResult.message}
              {comfyUIResult.promptId && (
                <span className="ml-2 font-mono text-gray-400">ID: {comfyUIResult.promptId}</span>
              )}
            </div>
          )}

          {/* ComfyUI generation progress */}
          {comfyUIProgress && comfyUIResult && comfyUIResult.index === index && (
            <div className="mt-2 rounded-md border border-gray-700 bg-gray-800/50 p-2.5 text-xs">
              {/* Progress status */}
              {comfyUIProgress.status === 'connecting' && (
                <div className="flex items-center gap-2 text-gray-400">
                  <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-gray-600 border-t-indigo-500" />
                  Connecting to ComfyUI WebSocket…
                </div>
              )}
              {comfyUIProgress.status === 'connected' && (
                <div className="flex items-center gap-2 text-gray-400">
                  <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-gray-600 border-t-indigo-500" />
                  Connected — waiting for generation to start…
                </div>
              )}
              {comfyUIProgress.status === 'generating' && (
                <div>
                  <div className="flex items-center justify-between text-gray-300 mb-1.5">
                    <span className="flex items-center gap-2">
                      <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-gray-600 border-t-purple-500" />
                      Generating…
                    </span>
                    {comfyUIProgress.maxStep > 0 && (
                      <span className="font-mono text-gray-500">
                        {comfyUIProgress.step}/{comfyUIProgress.maxStep}
                      </span>
                    )}
                  </div>
                  {comfyUIProgress.maxStep > 0 && (
                    <div className="w-full bg-gray-700 rounded-full h-1.5 overflow-hidden">
                      <div
                        className="bg-purple-500 h-1.5 rounded-full transition-all duration-300"
                        style={{ width: `${Math.round((comfyUIProgress.step / comfyUIProgress.maxStep) * 100)}%` }}
                      />
                    </div>
                  )}
                </div>
              )}
              {comfyUIProgress.status === 'polling' && (
                <div className="flex items-center gap-2 text-gray-400">
                  <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-gray-600 border-t-indigo-500" />
                  Checking generation status…
                </div>
              )}
              {comfyUIProgress.status === 'fetching' && (
                <div className="flex items-center gap-2 text-gray-400">
                  <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-gray-600 border-t-emerald-500" />
                  Fetching generated images…
                </div>
              )}
              {comfyUIProgress.status === 'done' && (
                <div>
                  <div className="flex items-center gap-2 text-emerald-400 mb-2">
                    <span>✅</span>
                    <span className="font-medium">Generation complete!</span>
                  </div>
                  {comfyUIProgress.images && comfyUIProgress.images.length > 0 && (
                    <div className="grid grid-cols-2 gap-2 mt-2">
                      {comfyUIProgress.images.map((img, imgIdx) => (
                        <a
                          key={imgIdx}
                          href={img.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="block overflow-hidden rounded-md border border-gray-600 hover:border-indigo-500 transition-colors"
                        >
                          <img
                            src={img.url}
                            alt={`Generated image ${imgIdx + 1}`}
                            className="w-full h-auto"
                            loading="lazy"
                          />
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              )}
              {comfyUIProgress.status === 'error' && (
                <div className="text-red-400">
                  <span className="font-medium">❌ Generation error:</span>{' '}
                  {comfyUIProgress.errorMessage || 'Unknown error'}
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

export default PromptResults