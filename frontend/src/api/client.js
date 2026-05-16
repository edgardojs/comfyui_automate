/**
 * API client for the Sprite Prompt Generator backend.
 *
 * All calls go through Vite's proxy to http://localhost:8000/api
 * so we can use relative paths.
 */

const API_BASE = "/api";

/**
 * Safely parse a JSON response, handling non-JSON error bodies.
 * @param {Response} res - Fetch Response object
 * @returns {Promise<object>} Parsed JSON body
 * @throws {Error} If response is not valid JSON
 */
async function safeJson(res) {
  try {
    return await res.json();
  } catch {
    throw new Error(`Unexpected response format (HTTP ${res.status})`);
  }
}

/**
 * Fetch the full attribute library.
 * @param {string} [category] - Optional category filter (e.g. "classes")
 * @returns {Promise<object>} The attribute library or filtered category
 */
export async function fetchAttributes(category) {
  const url = category
    ? `${API_BASE}/attributes?category=${encodeURIComponent(category)}`
    : `${API_BASE}/attributes`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch attributes: ${res.status}`);
  return safeJson(res);
}

/**
 * Fetch available prompt templates.
 * @returns {Promise<object>} The templates list
 */
export async function fetchTemplates() {
  const res = await fetch(`${API_BASE}/templates`);
  if (!res.ok) throw new Error(`Failed to fetch templates: ${res.status}`);
  return safeJson(res);
}

/**
 * Fetch available negative prompt profiles.
 * @returns {Promise<object>} The negative profiles list
 */
export async function fetchNegativeProfiles() {
  const res = await fetch(`${API_BASE}/negative-profiles`);
  if (!res.ok) throw new Error(`Failed to fetch negative profiles: ${res.status}`);
  return safeJson(res);
}

/**
 * Generate prompt pair(s) from selected attributes.
 * @param {object} params
 * @param {object} params.attributes - Selected attributes keyed by category
 * @param {number} [params.variationCount=1] - Number of variations to generate
 * @param {string[]} [params.lockedFields=[]] - Fields to lock across variations
 * @param {string} [params.templateId] - Prompt template ID
 * @param {string} [params.negativeProfileId] - Negative prompt profile ID
 * @returns {Promise<object>} Generated prompt pairs
 */
export async function generatePrompts({
  attributes,
  variationCount = 1,
  lockedFields = [],
  templateId,
  negativeProfileId,
}) {
  const res = await fetch(`${API_BASE}/prompts/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      attributes,
      variation_count: variationCount,
      locked_fields: lockedFields,
      template_id: templateId,
      negative_profile_id: negativeProfileId,
    }),
  });
  if (!res.ok) throw new Error(`Failed to generate prompts: ${res.status}`);
  return safeJson(res);
}

/**
 * Save a new preset.
 * @param {object} preset - Preset data
 * @returns {Promise<object>} The saved preset
 */
export async function savePreset(preset) {
  const res = await fetch(`${API_BASE}/presets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(preset),
  });
  if (!res.ok) throw new Error(`Failed to save preset: ${res.status}`);
  return safeJson(res);
}

/**
 * Fetch all presets.
 * @returns {Promise<object[]>} List of presets
 */
export async function fetchPresets() {
  const res = await fetch(`${API_BASE}/presets`);
  if (!res.ok) throw new Error(`Failed to fetch presets: ${res.status}`);
  return safeJson(res);
}

/**
 * Delete a preset by ID.
 * @param {string} presetId - The preset ID to delete
 * @returns {Promise<void>}
 */
export async function deletePreset(presetId) {
  const res = await fetch(`${API_BASE}/presets/${encodeURIComponent(presetId)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`Failed to delete preset: ${res.status}`);
}

/**
 * Fetch prompt generation history.
 * @param {object} [params] - Pagination parameters
 * @param {number} [params.limit=20] - Max items to return
 * @param {number} [params.offset=0] - Number of items to skip
 * @returns {Promise<object>} Paginated history response with items and total
 */
export async function fetchHistory({ limit = 20, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (limit !== 20) params.set('limit', String(limit));
  if (offset !== 0) params.set('offset', String(offset));
  const qs = params.toString();
  const url = qs ? `${API_BASE}/history?${qs}` : `${API_BASE}/history`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch history: ${res.status}`);
  return safeJson(res);
}

/**
 * Mark a history item as favorite.
 * @param {string} id - The history item ID
 * @returns {Promise<object>} Updated history item
 */
export async function favoriteHistoryItem(id) {
  const res = await fetch(`${API_BASE}/history/${encodeURIComponent(id)}/favorite`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`Failed to favorite history item: ${res.status}`);
  return safeJson(res);
}

/**
 * Health check.
 * @returns {Promise<object>} Health status
 */
export async function healthCheck() {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return safeJson(res);
}