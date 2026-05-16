/**
 * Unit tests for the API client module.
 *
 * Tests all exported functions with mocked fetch to verify:
 * - Correct URL construction
 * - Request body format
 * - Error handling for non-OK responses
 * - safeJson handling of malformed responses
 * - Pagination parameter encoding
 *
 * Note: fetchWithTimeout wraps fetch with an AbortController signal,
 * so all fetch calls include a `signal` property in the options.
 * We use `expect.objectContaining` to match the relevant options
 * while ignoring the signal.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  fetchAttributes,
  fetchTemplates,
  fetchNegativeProfiles,
  generatePrompts,
  savePreset,
  fetchPresets,
  deletePreset,
  fetchHistory,
  favoriteHistoryItem,
  healthCheck,
} from '../api/client'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Create a mock Response object. */
function mockResponse(body, status = 200, ok = true) {
  const text = body !== null && body !== undefined ? JSON.stringify(body) : ''
  return {
    ok,
    status,
    json: vi.fn().mockResolvedValue(body),
    text: vi.fn().mockResolvedValue(text),
  }
}

/** Create a mock Response that throws on .json() (non-JSON body). */
function mockNonJsonResponse(status = 200) {
  return {
    ok: true,
    status,
    json: vi.fn().mockRejectedValue(new SyntaxError('Unexpected token')),
    text: vi.fn().mockResolvedValue('not json'),
  }
}

/**
 * Assert that fetch was called with the given URL and optional options.
 * Ignores the `signal` property added by fetchWithTimeout.
 */
function expectFetchCalledWith(url, options) {
  if (options) {
    expect(global.fetch).toHaveBeenCalledWith(url, expect.objectContaining(options))
  } else {
    expect(global.fetch).toHaveBeenCalledWith(url, expect.objectContaining({}))
  }
}

// ---------------------------------------------------------------------------
// fetchAttributes
// ---------------------------------------------------------------------------

describe('fetchAttributes', () => {
  beforeEach(() => {
    global.fetch = vi.fn()
  })

  it('fetches all attributes without category filter', async () => {
    const data = { categories: [{ id: 'classes', label: 'Class', attributes: [] }] }
    global.fetch.mockResolvedValue(mockResponse(data))

    const result = await fetchAttributes()

    expect(global.fetch).toHaveBeenCalledWith('/api/attributes', expect.objectContaining({}))
    expect(result).toEqual(data)
  })

  it('fetches attributes with category filter', async () => {
    const data = { categories: [{ id: 'classes', label: 'Class', attributes: [] }] }
    global.fetch.mockResolvedValue(mockResponse(data))

    const result = await fetchAttributes('classes')

    expect(global.fetch).toHaveBeenCalledWith('/api/attributes?category=classes', expect.objectContaining({}))
    expect(result).toEqual(data)
  })

  it('encodes special characters in category filter', async () => {
    global.fetch.mockResolvedValue(mockResponse({ categories: [] }))

    await fetchAttributes('my category')

    expect(global.fetch).toHaveBeenCalledWith('/api/attributes?category=my%20category', expect.objectContaining({}))
  })

  it('throws on non-OK response', async () => {
    global.fetch.mockResolvedValue(mockResponse({}, 500, false))

    await expect(fetchAttributes()).rejects.toThrow('Failed to fetch attributes: 500')
  })
})

// ---------------------------------------------------------------------------
// fetchTemplates
// ---------------------------------------------------------------------------

describe('fetchTemplates', () => {
  beforeEach(() => {
    global.fetch = vi.fn()
  })

  it('fetches templates', async () => {
    const data = { templates: [{ id: 'front_view', label: 'Front View' }] }
    global.fetch.mockResolvedValue(mockResponse(data))

    const result = await fetchTemplates()

    expect(global.fetch).toHaveBeenCalledWith('/api/templates', expect.objectContaining({}))
    expect(result).toEqual(data)
  })

  it('throws on non-OK response', async () => {
    global.fetch.mockResolvedValue(mockResponse({}, 404, false))

    await expect(fetchTemplates()).rejects.toThrow('Failed to fetch templates: 404')
  })
})

// ---------------------------------------------------------------------------
// fetchNegativeProfiles
// ---------------------------------------------------------------------------

describe('fetchNegativeProfiles', () => {
  beforeEach(() => {
    global.fetch = vi.fn()
  })

  it('fetches negative profiles', async () => {
    const data = { profiles: [{ id: 'general', label: 'General' }] }
    global.fetch.mockResolvedValue(mockResponse(data))

    const result = await fetchNegativeProfiles()

    expect(global.fetch).toHaveBeenCalledWith('/api/negative-profiles', expect.objectContaining({}))
    expect(result).toEqual(data)
  })

  it('throws on non-OK response', async () => {
    global.fetch.mockResolvedValue(mockResponse({}, 503, false))

    await expect(fetchNegativeProfiles()).rejects.toThrow('Failed to fetch negative profiles: 503')
  })
})

// ---------------------------------------------------------------------------
// generatePrompts
// ---------------------------------------------------------------------------

describe('generatePrompts', () => {
  beforeEach(() => {
    global.fetch = vi.fn()
  })

  it('sends POST request with default values', async () => {
    const data = { generation_id: 'gen_1', items: [] }
    global.fetch.mockResolvedValue(mockResponse(data))

    const result = await generatePrompts({ attributes: {} })

    expect(global.fetch).toHaveBeenCalledWith('/api/prompts/generate', expect.objectContaining({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        attributes: {},
        variation_count: 1,
        locked_fields: [],
        template_id: undefined,
        negative_profile_id: undefined,
      }),
    }))
    expect(result).toEqual(data)
  })

  it('sends all parameters correctly', async () => {
    const data = { generation_id: 'gen_2', items: [] }
    global.fetch.mockResolvedValue(mockResponse(data))

    await generatePrompts({
      attributes: { classes: 'rogue' },
      variationCount: 5,
      lockedFields: ['classes'],
      templateId: 'front_view_sprite',
      negativeProfileId: 'general_sprite_cleanup',
    })

    expect(global.fetch).toHaveBeenCalledWith('/api/prompts/generate', expect.objectContaining({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        attributes: { classes: 'rogue' },
        variation_count: 5,
        locked_fields: ['classes'],
        template_id: 'front_view_sprite',
        negative_profile_id: 'general_sprite_cleanup',
      }),
    }))
  })

  it('throws on non-OK response', async () => {
    global.fetch.mockResolvedValue(mockResponse({}, 422, false))

    await expect(generatePrompts({ attributes: {} })).rejects.toThrow(
      'Failed to generate prompts: 422'
    )
  })
})

// ---------------------------------------------------------------------------
// savePreset
// ---------------------------------------------------------------------------

describe('savePreset', () => {
  beforeEach(() => {
    global.fetch = vi.fn()
  })

  it('sends POST request with preset data', async () => {
    const preset = { name: 'Test', attributes: { classes: 'rogue' } }
    const response = { preset_id: 'preset_1', ...preset }
    global.fetch.mockResolvedValue(mockResponse(response, 201))

    const result = await savePreset(preset)

    expect(global.fetch).toHaveBeenCalledWith('/api/presets', expect.objectContaining({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(preset),
    }))
    expect(result).toEqual(response)
  })

  it('throws on non-OK response', async () => {
    global.fetch.mockResolvedValue(mockResponse({}, 422, false))

    await expect(savePreset({ name: '' })).rejects.toThrow('Failed to save preset: 422')
  })
})

// ---------------------------------------------------------------------------
// fetchPresets
// ---------------------------------------------------------------------------

describe('fetchPresets', () => {
  beforeEach(() => {
    global.fetch = vi.fn()
  })

  it('fetches all presets', async () => {
    const data = [{ preset_id: 'preset_1', name: 'Test' }]
    global.fetch.mockResolvedValue(mockResponse(data))

    const result = await fetchPresets()

    expect(global.fetch).toHaveBeenCalledWith('/api/presets', expect.objectContaining({}))
    expect(result).toEqual(data)
  })
})

// ---------------------------------------------------------------------------
// deletePreset
// ---------------------------------------------------------------------------

describe('deletePreset', () => {
  beforeEach(() => {
    global.fetch = vi.fn()
  })

  it('sends DELETE request with encoded preset ID', async () => {
    global.fetch.mockResolvedValue(mockResponse(null, 204))

    await deletePreset('preset_abc')

    expect(global.fetch).toHaveBeenCalledWith('/api/presets/preset_abc', expect.objectContaining({
      method: 'DELETE',
    }))
  })

  it('encodes special characters in preset ID', async () => {
    global.fetch.mockResolvedValue(mockResponse(null, 404, false))

    await expect(deletePreset('preset/special')).rejects.toThrow()
    expect(global.fetch).toHaveBeenCalledWith('/api/presets/preset%2Fspecial', expect.objectContaining({
      method: 'DELETE',
    }))
  })

  it('throws on non-OK response', async () => {
    global.fetch.mockResolvedValue(mockResponse({}, 404, false))

    await expect(deletePreset('nonexistent')).rejects.toThrow('Failed to delete preset: 404')
  })
})

// ---------------------------------------------------------------------------
// fetchHistory
// ---------------------------------------------------------------------------

describe('fetchHistory', () => {
  beforeEach(() => {
    global.fetch = vi.fn()
  })

  it('fetches history with default pagination', async () => {
    const data = { items: [], total: 0 }
    global.fetch.mockResolvedValue(mockResponse(data))

    const result = await fetchHistory()

    expect(global.fetch).toHaveBeenCalledWith('/api/history', expect.objectContaining({}))
    expect(result).toEqual(data)
  })

  it('sends limit parameter when not default', async () => {
    const data = { items: [], total: 0 }
    global.fetch.mockResolvedValue(mockResponse(data))

    await fetchHistory({ limit: 10 })

    expect(global.fetch).toHaveBeenCalledWith('/api/history?limit=10', expect.objectContaining({}))
  })

  it('sends offset parameter when not default', async () => {
    const data = { items: [], total: 0 }
    global.fetch.mockResolvedValue(mockResponse(data))

    await fetchHistory({ offset: 20 })

    expect(global.fetch).toHaveBeenCalledWith('/api/history?offset=20', expect.objectContaining({}))
  })

  it('sends both limit and offset', async () => {
    const data = { items: [], total: 0 }
    global.fetch.mockResolvedValue(mockResponse(data))

    await fetchHistory({ limit: 5, offset: 10 })

    expect(global.fetch).toHaveBeenCalledWith('/api/history?limit=5&offset=10', expect.objectContaining({}))
  })

  it('throws on non-OK response', async () => {
    global.fetch.mockResolvedValue(mockResponse({}, 500, false))

    await expect(fetchHistory()).rejects.toThrow('Failed to fetch history: 500')
  })
})

// ---------------------------------------------------------------------------
// favoriteHistoryItem
// ---------------------------------------------------------------------------

describe('favoriteHistoryItem', () => {
  beforeEach(() => {
    global.fetch = vi.fn()
  })

  it('sends POST request with encoded ID', async () => {
    const data = { generation_id: 'gen_1', is_favorite: true }
    global.fetch.mockResolvedValue(mockResponse(data))

    const result = await favoriteHistoryItem('gen_1')

    expect(global.fetch).toHaveBeenCalledWith('/api/history/gen_1/favorite', expect.objectContaining({
      method: 'POST',
    }))
    expect(result).toEqual(data)
  })

  it('encodes special characters in ID', async () => {
    global.fetch.mockResolvedValue(mockResponse({}, 404, false))

    await expect(favoriteHistoryItem('gen/special')).rejects.toThrow()
    expect(global.fetch).toHaveBeenCalledWith('/api/history/gen%2Fspecial/favorite', expect.objectContaining({
      method: 'POST',
    }))
  })

  it('throws on non-OK response', async () => {
    global.fetch.mockResolvedValue(mockResponse({}, 404, false))

    await expect(favoriteHistoryItem('nonexistent')).rejects.toThrow(
      'Failed to favorite history item: 404'
    )
  })
})

// ---------------------------------------------------------------------------
// healthCheck
// ---------------------------------------------------------------------------

describe('healthCheck', () => {
  beforeEach(() => {
    global.fetch = vi.fn()
  })

  it('returns health status', async () => {
    const data = { status: 'ok' }
    global.fetch.mockResolvedValue(mockResponse(data))

    const result = await healthCheck()

    expect(global.fetch).toHaveBeenCalledWith('/api/health', expect.objectContaining({}))
    expect(result).toEqual(data)
  })

  it('throws on non-OK response', async () => {
    global.fetch.mockResolvedValue(mockResponse({}, 503, false))

    await expect(healthCheck()).rejects.toThrow('Health check failed: 503')
  })
})

// ---------------------------------------------------------------------------
// safeJson — non-JSON response handling
// ---------------------------------------------------------------------------

describe('safeJson error handling', () => {
  beforeEach(() => {
    global.fetch = vi.fn()
  })

  it('throws user-friendly error when response body is not JSON', async () => {
    const nonJsonRes = {
      ok: true,
      status: 200,
      json: vi.fn().mockRejectedValue(new SyntaxError('Unexpected token')),
      text: vi.fn().mockResolvedValue('not json'),
    }
    global.fetch.mockResolvedValue(nonJsonRes)

    await expect(fetchAttributes()).rejects.toThrow(
      'Unexpected response format (HTTP 200)'
    )
  })

  it('still throws status-based error for non-OK responses before safeJson', async () => {
    global.fetch.mockResolvedValue(mockResponse({}, 500, false))

    await expect(fetchAttributes()).rejects.toThrow('Failed to fetch attributes: 500')
  })
})