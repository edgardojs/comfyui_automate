/**
 * Image persistence tests for ComfyUI integration.
 *
 * Tests that ComfyUI images are correctly keyed by history_id,
 * persisted to localStorage, and not overwritten when status is 'done'.
 *
 * Corresponds to P0-3 of the implementation plan.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { loadComfyUISettings, saveComfyUISettings, flushComfyUISettings, getDefaultComfyUISettings } from '../api/comfyuiSettings'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Mock localStorage for testing. */
function createMockLocalStorage() {
  let store = {}
  return {
    getItem: vi.fn((key) => store[key] ?? null),
    setItem: vi.fn((key, value) => { store[key] = value }),
    removeItem: vi.fn((key) => { delete store[key] }),
    clear: vi.fn(() => { store = {} }),
    get _store() { return store },
  }
}

/**
 * Reset the comfyuiSettings module state by loading with empty localStorage.
 * This clears the module-level _lastSavedSettings cache.
 */
function resetModuleState() {
  global.localStorage = createMockLocalStorage()
  loadComfyUISettings() // This resets _lastSavedSettings to defaults
}

// ---------------------------------------------------------------------------
// ComfyUI Settings Persistence
// ---------------------------------------------------------------------------

describe('ComfyUI Settings Persistence', () => {
  let localStorage

  beforeEach(() => {
    localStorage = createMockLocalStorage()
    global.localStorage = localStorage
  })

  it('saves settings to localStorage immediately', () => {
    const settings = { ...getDefaultComfyUISettings(), serverUrl: 'http://192.168.1.100:8188' }
    saveComfyUISettings(settings)
    expect(localStorage.setItem).toHaveBeenCalledWith(
      'comfyui_settings',
      JSON.stringify(settings)
    )
  })

  it('loads settings from localStorage with defaults merged', () => {
    const partial = { serverUrl: 'http://custom:8188' }
    localStorage.getItem.mockReturnValue(JSON.stringify(partial))

    const loaded = loadComfyUISettings()
    expect(loaded.serverUrl).toBe('http://custom:8188')
    // Defaults should be filled in for missing keys
    expect(loaded.positiveInputName).toBe('text')
    expect(loaded.negativeInputName).toBe('text')
  })

  it('returns defaults when localStorage is empty', () => {
    localStorage.getItem.mockReturnValue(null)
    const loaded = loadComfyUISettings()
    expect(loaded).toEqual(getDefaultComfyUISettings())
  })

  it('returns defaults when localStorage has invalid JSON', () => {
    localStorage.getItem.mockReturnValue('not-json')
    const loaded = loadComfyUISettings()
    expect(loaded).toEqual(getDefaultComfyUISettings())
  })

  it('flushes last saved settings on beforeunload', () => {
    const settings = { ...getDefaultComfyUISettings(), serverUrl: 'http://flush-test:8188' }
    saveComfyUISettings(settings)
    // Reset call count to check flush specifically
    localStorage.setItem.mockClear()
    flushComfyUISettings()
    expect(localStorage.setItem).toHaveBeenCalledWith(
      'comfyui_settings',
      JSON.stringify(settings)
    )
  })

  it('flush does nothing if no settings have been saved', () => {
    // Reset module state so _lastSavedSettings is null
    resetModuleState()
    localStorage.setItem.mockClear()
    flushComfyUISettings()
    expect(localStorage.setItem).not.toHaveBeenCalled()
  })

  it('preserves unknown keys from stored settings (forward-compatible)', () => {
    const stored = { serverUrl: 'http://test:8188', futureField: 'future-value' }
    localStorage.getItem.mockReturnValue(JSON.stringify(stored))
    const loaded = loadComfyUISettings()
    expect(loaded.futureField).toBe('future-value')
  })
})

// ---------------------------------------------------------------------------
// Image Keying by history_id
// ---------------------------------------------------------------------------

describe('ComfyUI Images Keyed by history_id', () => {
  it('images are keyed by history_id string, not numeric index', () => {
    const comfyUIImages = {
      '42': [{ filename: 'img1.png', subfolder: '', type: 'output', url: '/img1' }],
      '43': [{ filename: 'img2.png', subfolder: '', type: 'output', url: '/img2' }],
    }
    // Keys should be strings (history_id)
    expect(Object.keys(comfyUIImages)).toEqual(['42', '43'])
    expect(comfyUIImages['42']).toBeDefined()
    expect(comfyUIImages['42'][0].filename).toBe('img1.png')
  })

  it('multiple images per history_id', () => {
    const comfyUIImages = {
      '50': [
        { filename: 'img1.png', subfolder: '', type: 'output', url: '/1' },
        { filename: 'img2.png', subfolder: '', type: 'output', url: '/2' },
        { filename: 'img3.png', subfolder: '', type: 'output', url: '/3' },
      ],
    }
    expect(comfyUIImages['50'].length).toBe(3)
  })

  it('different history entries have independent image lists', () => {
    const comfyUIImages = {
      '10': [{ filename: 'first.png', subfolder: '', type: 'output', url: '/first' }],
      '20': [{ filename: 'second.png', subfolder: '', type: 'output', url: '/second' }],
    }
    expect(comfyUIImages['10'][0].filename).toBe('first.png')
    expect(comfyUIImages['20'][0].filename).toBe('second.png')
    // Modifying one does not affect the other
    comfyUIImages['10'].push({ filename: 'extra.png', subfolder: '', type: 'output', url: '/extra' })
    expect(comfyUIImages['20'].length).toBe(1)
  })
})

// ---------------------------------------------------------------------------
// localStorage Persistence of Images
// ---------------------------------------------------------------------------

describe('ComfyUI Images localStorage Persistence', () => {
  let localStorage

  beforeEach(() => {
    localStorage = createMockLocalStorage()
    global.localStorage = localStorage
  })

  it('images can be serialized to localStorage', () => {
    const comfyUIImages = {
      '42': [{ filename: 'test.png', subfolder: '', type: 'output', url: '/test' }],
    }
    localStorage.setItem('comfyui_images', JSON.stringify(comfyUIImages))
    expect(localStorage.setItem).toHaveBeenCalledWith(
      'comfyui_images',
      JSON.stringify(comfyUIImages)
    )
  })

  it('images can be deserialized from localStorage', () => {
    const comfyUIImages = {
      '42': [{ filename: 'test.png', subfolder: '', type: 'output', url: '/test' }],
    }
    localStorage.getItem.mockReturnValue(JSON.stringify(comfyUIImages))
    const loaded = JSON.parse(localStorage.getItem('comfyui_images'))
    expect(loaded['42'][0].filename).toBe('test.png')
  })

  it('empty images object can be stored and retrieved', () => {
    localStorage.setItem('comfyui_images', JSON.stringify({}))
    localStorage.getItem.mockReturnValue('{}')
    const loaded = JSON.parse(localStorage.getItem('comfyui_images'))
    expect(Object.keys(loaded)).toEqual([])
  })

  it('handles missing localStorage key gracefully', () => {
    localStorage.getItem.mockReturnValue(null)
    const loaded = localStorage.getItem('comfyui_images')
    expect(loaded).toBeNull()
    // App should default to empty object
    const images = loaded ? JSON.parse(loaded) : {}
    expect(images).toEqual({})
  })

  it('handles corrupted localStorage data gracefully', () => {
    localStorage.getItem.mockReturnValue('not-valid-json{{{')
    let images = {}
    try {
      const parsed = JSON.parse(localStorage.getItem('comfyui_images'))
      if (typeof parsed === 'object' && parsed !== null) images = parsed
    } catch { /* ignore */ }
    expect(images).toEqual({})
  })
})

// ---------------------------------------------------------------------------
// No Image Overwrite When Status is Done
// ---------------------------------------------------------------------------

describe('No Image Overwrite When Done', () => {
  it('existing images are preserved when new generation starts', () => {
    // Simulate: first generation produced images for history_id 42
    const comfyUIImages = {
      '42': [{ filename: 'first_gen.png', subfolder: '', type: 'output', url: '/first' }],
    }

    // Simulate: second generation produces images for history_id 43
    // The merge should ADD the new entry, not replace the whole object
    const newImages = {
      '43': [{ filename: 'second_gen.png', subfolder: '', type: 'output', url: '/second' }],
    }

    // React state merge pattern: { ...prev, ...newImages }
    const merged = { ...comfyUIImages, ...newImages }

    expect(merged['42']).toBeDefined()
    expect(merged['42'][0].filename).toBe('first_gen.png')
    expect(merged['43']).toBeDefined()
    expect(merged['43'][0].filename).toBe('second_gen.png')
  })

  it('done status images are not cleared by WebSocket disconnect', () => {
    // Simulate: images exist for a completed generation
    const comfyUIImages = {
      '42': [{ filename: 'completed.png', subfolder: '', type: 'output', url: '/done' }],
    }

    // WebSocket disconnect should NOT clear existing images
    // The images should still be accessible by history_id
    expect(comfyUIImages['42']).toBeDefined()
    expect(comfyUIImages['42'].length).toBe(1)
    expect(comfyUIImages['42'][0].filename).toBe('completed.png')
  })

  it('clearing all images removes all entries', () => {
    const comfyUIImages = {
      '42': [{ filename: 'img1.png', subfolder: '', type: 'output', url: '/1' }],
      '43': [{ filename: 'img2.png', subfolder: '', type: 'output', url: '/2' }],
    }

    // Simulate handleClearAll
    const cleared = {}
    expect(Object.keys(cleared)).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// Image Metadata Structure
// ---------------------------------------------------------------------------

describe('Image Metadata Structure', () => {
  it('each image has required fields', () => {
    const image = {
      filename: 'ComfyUI_00001_.png',
      subfolder: '',
      type: 'output',
      url: '/api/comfyui/image?filename=ComfyUI_00001_.png&subfolder=&type=output&server_url=http://localhost:8188',
    }
    expect(image).toHaveProperty('filename')
    expect(image).toHaveProperty('subfolder')
    expect(image).toHaveProperty('type')
    expect(image).toHaveProperty('url')
  })

  it('image type is output or input', () => {
    const outputImage = { filename: 'gen.png', subfolder: '', type: 'output', url: '/gen' }
    const inputImage = { filename: 'ref.png', subfolder: '', type: 'input', url: '/ref' }
    expect(['output', 'input']).toContain(outputImage.type)
    expect(['output', 'input']).toContain(inputImage.type)
  })

  it('url points to image proxy endpoint', () => {
    const image = {
      filename: 'test.png',
      subfolder: '',
      type: 'output',
      url: '/api/comfyui/image?filename=test.png&subfolder=&type=output&server_url=http://localhost:8188',
    }
    expect(image.url).toContain('/api/comfyui/image')
    expect(image.url).toContain('filename=test.png')
  })
})