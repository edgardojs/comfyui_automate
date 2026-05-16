/**
 * ComfyUI settings utility — shared between App.jsx and ComfyUISettings.jsx.
 *
 * Provides a single source of truth for loading/saving ComfyUI settings
 * from localStorage, so both components read the same data consistently.
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

/**
 * Load ComfyUI settings from localStorage, merging with defaults.
 * @returns {object} The settings object
 */
export function loadComfyUISettings() {
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

/**
 * Save ComfyUI settings to localStorage.
 * @param {object} settings - The settings object to persist
 */
export function saveComfyUISettings(settings) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
}

/**
 * Get the default settings object (a fresh copy).
 * @returns {object} Default settings
 */
export function getDefaultComfyUISettings() {
  return { ...DEFAULT_SETTINGS }
}