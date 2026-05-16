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

// ---------------------------------------------------------------------------
// ComfyUI Integration API
// ---------------------------------------------------------------------------

/**
 * Test connection to a ComfyUI server.
 * @param {string} serverUrl - The ComfyUI server URL (e.g. "http://127.0.0.1:8188")
 * @returns {Promise<object>} Connection test result with connected, message, and system_info
 */
export async function testComfyUIConnection(serverUrl) {
  const res = await fetch(`${API_BASE}/comfyui/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ server_url: serverUrl }),
  });
  if (!res.ok) throw new Error(`Connection test failed: ${res.status}`);
  return safeJson(res);
}

/**
 * Validate a ComfyUI workflow JSON and extract node IDs.
 * @param {object} workflowJson - The workflow JSON object to validate
 * @returns {Promise<object>} Validation result with valid, issues, and node_ids
 */
export async function validateComfyUIWorkflow(workflowJson) {
  const res = await fetch(`${API_BASE}/comfyui/validate-workflow`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workflow_json: workflowJson }),
  });
  if (!res.ok) throw new Error(`Workflow validation failed: ${res.status}`);
  return safeJson(res);
}

/**
 * Submit a prompt to ComfyUI.
 * @param {object} params
 * @param {string} params.serverUrl - ComfyUI server URL
 * @param {object} params.workflowJson - The workflow JSON to patch and submit
 * @param {string} params.positivePrompt - Positive prompt text
 * @param {string} params.negativePrompt - Negative prompt text
 * @param {object} params.nodeMapping - Node ID mapping for prompt injection
 * @param {number} [params.seed] - Optional seed value
 * @returns {Promise<object>} Submission result with success, prompt_id, and message
 */
export async function submitToComfyUI({
  serverUrl,
  workflowJson,
  positivePrompt,
  negativePrompt,
  nodeMapping,
  seed,
}) {
  const res = await fetch(`${API_BASE}/comfyui/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      server_url: serverUrl,
      workflow_json: workflowJson,
      positive_prompt: positivePrompt,
      negative_prompt: negativePrompt,
      node_mapping: nodeMapping,
      seed: seed ?? null,
    }),
  });
  if (!res.ok) {
    let detail = `Submission failed: ${res.status}`;
    try {
      const errBody = await res.json();
      if (errBody.detail) detail = errBody.detail;
    } catch {
      // Ignore parse errors
    }
    throw new Error(detail);
  }
  return safeJson(res);
}

/**
 * Check the status of a ComfyUI generation.
 * @param {string} promptId - The prompt ID returned from submission
 * @param {string} [serverUrl] - ComfyUI server URL (defaults to localhost)
 * @returns {Promise<object>} Status result with prompt_id, status, and message
 */
export async function checkComfyUIStatus(promptId, serverUrl) {
  const params = new URLSearchParams();
  if (serverUrl) params.set("server_url", serverUrl);
  const qs = params.toString();
  const url = qs
    ? `${API_BASE}/comfyui/status/${encodeURIComponent(promptId)}?${qs}`
    : `${API_BASE}/comfyui/status/${encodeURIComponent(promptId)}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Status check failed: ${res.status}`);
  return safeJson(res);
}