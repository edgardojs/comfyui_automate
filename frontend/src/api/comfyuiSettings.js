/**
 * ComfyUI settings utility — shared between App.jsx and ComfyUISettings.jsx.
 *
 * Provides a single source of truth for loading/saving ComfyUI settings
 * from localStorage, so both components read the same data consistently.
 *
 * Persistence guarantees:
 * - Settings are saved immediately (no debounce) on every change.
 * - A `beforeunload` handler flushes pending saves before the page closes.
 * - On load, stored settings are merged with defaults so new fields get
 *   sensible values even if they were added after the user first saved.
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
  seedInputName: '',  // Empty = auto-detect based on node type (e.g. "noise_seed" for RandomNoise)
}

// Module-level cache of the last saved settings, used by the beforeunload
// handler to guarantee the most recent state is persisted.
let _lastSavedSettings = null

/**
 * Load ComfyUI settings from localStorage, merging with defaults.
 *
 * Any keys present in localStorage but missing from DEFAULT_SETTINGS are
 * preserved (forward-compatible). Any keys in DEFAULT_SETTINGS that are
 * missing from the stored data get the default value (backward-compatible).
 *
 * @returns {object} The settings object
 */
export function loadComfyUISettings() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      const parsed = JSON.parse(stored)
      const merged = { ...DEFAULT_SETTINGS, ...parsed }
      _lastSavedSettings = merged
      return merged
    }
  } catch {
    // Ignore parse errors
  }
  const defaults = { ...DEFAULT_SETTINGS }
  _lastSavedSettings = defaults
  return defaults
}

/**
 * Save ComfyUI settings to localStorage immediately.
 *
 * This function writes synchronously to localStorage — there is no debounce.
 * The write is fast (sub-millisecond for typical settings objects) and
 * ensures settings are never lost on page navigation or refresh.
 *
 * @param {object} settings - The settings object to persist
 */
export function saveComfyUISettings(settings) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
    _lastSavedSettings = settings
  } catch {
    // Ignore storage errors (e.g. quota exceeded, private browsing)
  }
}

/**
 * Flush the most recent settings to localStorage.
 *
 * Called by the `beforeunload` handler to guarantee that any in-flight
 * state changes are persisted before the page closes.
 */
export function flushComfyUISettings() {
  if (_lastSavedSettings) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(_lastSavedSettings))
    } catch {
      // Ignore storage errors
    }
  }
}

/**
 * Get the default settings object (a fresh copy).
 * @returns {object} Default settings
 */
export function getDefaultComfyUISettings() {
  return { ...DEFAULT_SETTINGS }
}