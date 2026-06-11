/**
 * API client for the Sprite Prompt Generator backend.
 *
 * All calls go through Vite's proxy to http://localhost:8000/api
 * so we can use relative paths.
 */

const API_BASE = "/api";

/** Default request timeout in milliseconds (30 seconds). */
const DEFAULT_TIMEOUT = 30_000;

/**
 * Fetch wrapper with timeout support.
 * Uses AbortController to cancel requests that exceed the timeout.
 * @param {string} url - URL to fetch
 * @param {object} [options] - Fetch options
 * @param {number} [timeout=DEFAULT_TIMEOUT] - Timeout in milliseconds
 * @returns {Promise<Response>} Fetch Response object
 */
async function fetchWithTimeout(url, options = {}, timeout = DEFAULT_TIMEOUT) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    return res;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Safely parse a JSON response, handling non-JSON and empty response bodies.
 * @param {Response} res - Fetch Response object
 * @returns {Promise<object>} Parsed JSON body
 * @throws {Error} If response is not valid JSON or body is empty
 */
async function safeJson(res) {
  // Allow empty bodies for 204 No Content responses
  if (res.status === 204) return {}
  const text = await res.text();
  if (!text) {
    throw new Error(`Empty response body (HTTP ${res.status})`);
  }
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`Unexpected response format (HTTP ${res.status})`);
  }
}

/**
 * Centralized error handler for API responses.
 * Parses error details from the response body when available.
 * @param {Response} res - Fetch Response object
 * @param {string} action - Description of the action for error messages
 * @throws {Error} With parsed detail from the server or a generic message
 */
async function handleApiError(res, action) {
  let detail = ''
  try {
    const body = await safeJson(res)
    detail = body.detail || body.message || ''
  } catch {
    // If we can't parse the error body, use status text
    detail = res.statusText || ''
  }
  throw new Error(detail || `${action} failed (HTTP ${res.status})`)
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
  const res = await fetchWithTimeout(url);
  if (!res.ok) await handleApiError(res, 'Fetch attributes');
  return safeJson(res);
}

/**
 * Fetch available prompt templates.
 * @returns {Promise<object>} The templates list
 */
export async function fetchTemplates() {
  const res = await fetchWithTimeout(`${API_BASE}/templates`);
  if (!res.ok) await handleApiError(res, 'Fetch templates');
  return safeJson(res);
}

/**
 * Fetch available negative prompt profiles.
 * @returns {Promise<object>} The negative profiles list
 */
export async function fetchNegativeProfiles() {
  const res = await fetchWithTimeout(`${API_BASE}/negative-profiles`);
  if (!res.ok) await handleApiError(res, 'Fetch negative profiles');
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
  loraTriggerToken,
}) {
  const body = {
    attributes,
    variation_count: variationCount,
    locked_fields: lockedFields,
    template_id: templateId,
    negative_profile_id: negativeProfileId,
  };
  if (loraTriggerToken) {
    body.lora_trigger_token = loraTriggerToken;
  }
  const res = await fetchWithTimeout(`${API_BASE}/prompts/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) await handleApiError(res, 'Generate prompts');
  return safeJson(res);
}

/**
 * Save a new preset.
 * @param {object} preset - Preset data
 * @returns {Promise<object>} The saved preset
 */
export async function savePreset(preset) {
  const res = await fetchWithTimeout(`${API_BASE}/presets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(preset),
  });
  if (!res.ok) await handleApiError(res, 'Save preset');
  return safeJson(res);
}

/**
 * Fetch all presets.
 * @returns {Promise<object[]>} List of presets
 */
export async function fetchPresets() {
  const res = await fetchWithTimeout(`${API_BASE}/presets`);
  if (!res.ok) await handleApiError(res, 'Fetch presets');
  return safeJson(res);
}

/**
 * Delete a preset by ID.
 * @param {string} presetId - The preset ID to delete
 * @returns {Promise<void>}
 */
export async function deletePreset(presetId) {
  const res = await fetchWithTimeout(`${API_BASE}/presets/${encodeURIComponent(presetId)}`, {
    method: "DELETE",
  });
  if (!res.ok) await handleApiError(res, 'Delete preset');
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
  const res = await fetchWithTimeout(url);
  if (!res.ok) await handleApiError(res, 'Fetch history');
  return safeJson(res);
}

/**
 * Mark a history item as favorite.
 * @param {string} id - The history item ID
 * @returns {Promise<object>} Updated history item
 */
export async function favoriteHistoryItem(id) {
  const res = await fetchWithTimeout(`${API_BASE}/history/${encodeURIComponent(id)}/favorite`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`Failed to favorite history item: ${res.status}`);
  return safeJson(res);
}

/**
 * Save ComfyUI output images to a history entry.
 * @param {number} id - The history entry ID
 * @param {object} params
 * @param {string|null} params.comfyuiPromptId - ComfyUI prompt ID
 * @param {Array} params.comfyuiImages - List of image objects with filename, subfolder, type, url
 * @returns {Promise<object>} Updated history entry
 */
export async function saveComfyUIImages(id, { comfyuiPromptId, comfyuiImages }) {
  const res = await fetchWithTimeout(`${API_BASE}/history/${id}/comfyui-images`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      comfyui_prompt_id: comfyuiPromptId ?? null,
      comfyui_images: comfyuiImages ?? [],
    }),
  });
  if (!res.ok) {
    let detail = `Failed to save ComfyUI images: ${res.status}`;
    try {
      const errBody = await res.json();
      if (errBody.detail) detail = errBody.detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }
  return safeJson(res);
}

/**
 * Health check.
 * @returns {Promise<object>} Health status
 */
export async function healthCheck() {
  const res = await fetchWithTimeout(`${API_BASE}/health`);
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
  const res = await fetchWithTimeout(`${API_BASE}/comfyui/test`, {
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
  const res = await fetchWithTimeout(`${API_BASE}/comfyui/validate-workflow`, {
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
  clientId,
}) {
  const body = {
    server_url: serverUrl,
    workflow_json: workflowJson,
    positive_prompt: positivePrompt,
    negative_prompt: negativePrompt,
    node_mapping: nodeMapping,
    seed: seed ?? null,
  };
  if (clientId) body.client_id = clientId;
  const res = await fetchWithTimeout(`${API_BASE}/comfyui/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
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
  const res = await fetchWithTimeout(url);
  if (!res.ok) throw new Error(`Status check failed: ${res.status}`);
  return safeJson(res);
}

/**
 * Fetch detailed generation history from ComfyUI (including output images).
 * @param {string} promptId - The prompt ID to look up
 * @param {string} serverUrl - ComfyUI server URL
 * @returns {Promise<object>} History detail with status, outputs, and images
 */
export async function fetchComfyUIHistory(promptId, serverUrl) {
  const params = new URLSearchParams({ server_url: serverUrl });
  const res = await fetchWithTimeout(
    `${API_BASE}/comfyui/history/${encodeURIComponent(promptId)}?${params.toString()}`,
    {},
    30_000 // 30s timeout for history fetch
  );
  if (!res.ok) {
    let detail = `History fetch failed: ${res.status}`;
    try {
      const errBody = await res.json();
      if (errBody.detail) detail = errBody.detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }
  return safeJson(res);
}

/**
 * Build a URL for proxying a ComfyUI image through the backend.
 * @param {object} imageInfo - Image info from history (filename, subfolder, type)
 * @param {string} serverUrl - ComfyUI server URL
 * @returns {string} URL to fetch the image through the backend proxy
 */
export function buildComfyUIImageUrl(imageInfo, serverUrl) {
  const params = new URLSearchParams({
    server_url: serverUrl,
    filename: imageInfo.filename,
    subfolder: imageInfo.subfolder || "",
    type: imageInfo.type || "output",
  });
  return `${API_BASE}/comfyui/image?${params.toString()}`;
}

/**
 * Fetch a unique client ID for ComfyUI WebSocket connections.
 * @returns {Promise<string>} A unique client ID
 */
export async function fetchComfyUIClientId() {
  const res = await fetchWithTimeout(`${API_BASE}/comfyui/client-id`);
  if (!res.ok) {
    // Fallback to a local UUID
    return crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }
  const data = await safeJson(res);
  return data.client_id;
}

// ---------------------------------------------------------------------------
// Character Profile API
// ---------------------------------------------------------------------------

/**
 * Create a new character profile.
 * @param {object} profile - Character profile data
 * @returns {Promise<object>} The created character profile
 */
export async function createCharacter(profile) {
  const res = await fetchWithTimeout(`${API_BASE}/characters`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile),
  });
  if (!res.ok) {
    let detail = `Failed to create character: ${res.status}`;
    try {
      const errBody = await res.json();
      if (errBody.detail) detail = errBody.detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }
  return safeJson(res);
}

/**
 * Fetch all character profiles, optionally filtered by project.
 * @param {string} [projectName] - Optional project name filter
 * @returns {Promise<object[]>} List of character profiles
 */
export async function fetchCharacters(projectName) {
  const params = new URLSearchParams();
  if (projectName) params.set("project_name", projectName);
  const qs = params.toString();
  const url = qs ? `${API_BASE}/characters?${qs}` : `${API_BASE}/characters`;
  const res = await fetchWithTimeout(url);
  if (!res.ok) throw new Error(`Failed to fetch characters: ${res.status}`);
  return safeJson(res);
}

/**
 * Fetch a single character profile by ID.
 * @param {string} characterId - The character profile ID
 * @returns {Promise<object>} The character profile
 */
export async function fetchCharacter(characterId) {
  const res = await fetchWithTimeout(`${API_BASE}/characters/${encodeURIComponent(characterId)}`);
  if (!res.ok) throw new Error(`Failed to fetch character: ${res.status}`);
  return safeJson(res);
}

/**
 * Update a character profile.
 * @param {string} characterId - The character profile ID
 * @param {object} updates - Fields to update
 * @returns {Promise<object>} The updated character profile
 */
export async function updateCharacter(characterId, updates) {
  const res = await fetchWithTimeout(`${API_BASE}/characters/${encodeURIComponent(characterId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  if (!res.ok) {
    let detail = `Failed to update character: ${res.status}`;
    try {
      const errBody = await res.json();
      if (errBody.detail) detail = errBody.detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }
  return safeJson(res);
}

/**
 * Delete a character profile.
 * @param {string} characterId - The character profile ID
 * @returns {Promise<void>}
 */
export async function deleteCharacter(characterId) {
  const res = await fetchWithTimeout(`${API_BASE}/characters/${encodeURIComponent(characterId)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`Failed to delete character: ${res.status}`);
}

/**
 * Upload reference images for a character.
 * @param {string} characterId - The character profile ID
 * @param {File[]} files - Array of File objects to upload
 * @returns {Promise<object[]>} List of created reference image records
 */
export async function uploadReferences(characterId, files) {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }
  const res = await fetchWithTimeout(`${API_BASE}/characters/${encodeURIComponent(characterId)}/references`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    let detail = `Failed to upload references: ${res.status}`;
    try {
      const errBody = await res.json();
      if (errBody.detail) detail = errBody.detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }
  return safeJson(res);
}

/**
 * Fetch reference images for a character.
 * @param {string} characterId - The character profile ID
 * @param {string} [statusFilter] - Optional status filter
 * @returns {Promise<object[]>} List of reference images
 */
export async function fetchReferences(characterId, statusFilter) {
  const params = new URLSearchParams();
  if (statusFilter) params.set("status_filter", statusFilter);
  const qs = params.toString();
  const url = qs
    ? `${API_BASE}/characters/${encodeURIComponent(characterId)}/references?${qs}`
    : `${API_BASE}/characters/${encodeURIComponent(characterId)}/references`;
  const res = await fetchWithTimeout(url);
  if (!res.ok) throw new Error(`Failed to fetch references: ${res.status}`);
  return safeJson(res);
}

/**
 * Update a reference image's curation metadata.
 * @param {string} characterId - The character profile ID
 * @param {string} imageId - The reference image ID
 * @param {object} updates - Fields to update (status, angle, caption, rejection_reason)
 * @returns {Promise<object>} The updated reference image
 */
export async function updateReference(characterId, imageId, updates) {
  const res = await fetchWithTimeout(
    `${API_BASE}/characters/${encodeURIComponent(characterId)}/references/${encodeURIComponent(imageId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    }
  );
  if (!res.ok) throw new Error(`Failed to update reference: ${res.status}`);
  return safeJson(res);
}

/**
 * Delete a reference image.
 * @param {string} characterId - The character profile ID
 * @param {string} imageId - The reference image ID
 * @returns {Promise<void>}
 */
export async function deleteReference(characterId, imageId) {
  const res = await fetchWithTimeout(
    `${API_BASE}/characters/${encodeURIComponent(characterId)}/references/${encodeURIComponent(imageId)}`,
    { method: "DELETE" }
  );
  if (!res.ok) throw new Error(`Failed to delete reference: ${res.status}`);
}

/**
 * Get the URL for a reference image file.
 * @param {string} characterId - The character profile ID
 * @param {string} imageId - The reference image ID
 * @returns {string} The URL to the image file
 */
export function getReferenceFileUrl(characterId, imageId) {
  return `${API_BASE}/characters/${encodeURIComponent(characterId)}/references/${encodeURIComponent(imageId)}/file`;
}

/**
 * Validate a character's dataset quality.
 * @param {string} characterId - The character profile ID
 * @returns {Promise<object>} Validation result with warnings and counts
 */
export async function validateDataset(characterId) {
  const res = await fetchWithTimeout(
    `${API_BASE}/characters/${encodeURIComponent(characterId)}/dataset-validation`
  );
  if (!res.ok) throw new Error(`Failed to validate dataset: ${res.status}`);
  return safeJson(res);
}

// ---------------------------------------------------------------------------
// Caption API
// ---------------------------------------------------------------------------

/**
 * Auto-generate captions for all accepted reference images of a character.
 * @param {string} characterId - The character profile ID
 * @param {string} [captionStyle='detailed'] - Caption style: 'detailed' or 'simple'
 * @returns {Promise<object>} Caption generation response with captions list and count
 */
export async function generateCaptions(characterId, captionStyle = 'detailed') {
  const res = await fetchWithTimeout(
    `${API_BASE}/characters/${encodeURIComponent(characterId)}/generate-captions`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ caption_style: captionStyle }),
    }
  );
  if (!res.ok) {
    let detail = `Failed to generate captions: ${res.status}`;
    try {
      const errBody = await res.json();
      if (errBody.detail) detail = errBody.detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }
  return safeJson(res);
}

/**
 * Update the caption for a specific reference image.
 * @param {string} characterId - The character profile ID
 * @param {string} imageId - The reference image ID
 * @param {string} caption - The new caption text
 * @returns {Promise<object>} The updated reference image
 */
export async function updateCaption(characterId, imageId, caption) {
  const res = await fetchWithTimeout(
    `${API_BASE}/characters/${encodeURIComponent(characterId)}/references/${encodeURIComponent(imageId)}/caption`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ caption }),
    }
  );
  if (!res.ok) {
    let detail = `Failed to update caption: ${res.status}`;
    try {
      const errBody = await res.json();
      if (errBody.detail) detail = errBody.detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }
  return safeJson(res);
}

// ---------------------------------------------------------------------------
// Training Presets API
// ---------------------------------------------------------------------------

/**
 * Fetch all available LoRA training presets.
 * @returns {Promise<object[]>} List of training presets
 */
export async function fetchTrainingPresets() {
  const res = await fetchWithTimeout(`${API_BASE}/training-presets`);
  if (!res.ok) throw new Error(`Failed to fetch training presets: ${res.status}`);
  return safeJson(res);
}

// ---------------------------------------------------------------------------
// LoRA Jobs API
// ---------------------------------------------------------------------------

/**
 * Create a new LoRA training job.
 * @param {object} params
 * @param {string} params.character_id - The character profile ID
 * @param {string} [params.preset_id] - Training preset ID
 * @param {string} [params.base_model] - Base model path
 * @param {number} [params.learning_rate] - Learning rate
 * @param {number} [params.epochs] - Number of training epochs
 * @param {number} [params.preview_interval] - Preview interval
 * @param {string} [params.output_format] - Output format (e.g. "safetensors")
 * @param {number} [params.lora_strength] - LoRA strength
 * @param {object} [params.custom_args] - Custom training arguments
 * @returns {Promise<object>} The created LoRA job
 */
export async function createLoRAJob(params) {
  const res = await fetchWithTimeout(`${API_BASE}/lora/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    let detail = `Failed to create LoRA job: ${res.status}`;
    try {
      const errBody = await res.json();
      if (errBody.detail) detail = errBody.detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }
  return safeJson(res);
}

/**
 * List LoRA training jobs, optionally filtered.
 * @param {object} [params] - Filter parameters
 * @param {string} [params.character_id] - Filter by character ID
 * @param {string} [params.status_filter] - Filter by status
 * @returns {Promise<object[]>} List of LoRA job summaries
 */
export async function fetchLoRAJobs(params = {}) {
  const searchParams = new URLSearchParams();
  if (params.character_id) searchParams.set('character_id', params.character_id);
  if (params.status_filter) searchParams.set('status_filter', params.status_filter);
  const qs = searchParams.toString();
  const url = qs ? `${API_BASE}/lora/jobs?${qs}` : `${API_BASE}/lora/jobs`;
  const res = await fetchWithTimeout(url);
  if (!res.ok) throw new Error(`Failed to fetch LoRA jobs: ${res.status}`);
  return safeJson(res);
}

/**
 * Fetch a single LoRA training job by ID.
 * @param {string} jobId - The LoRA job ID
 * @returns {Promise<object>} The LoRA job details
 */
export async function fetchLoRAJob(jobId) {
  const res = await fetchWithTimeout(`${API_BASE}/lora/jobs/${encodeURIComponent(jobId)}`);
  if (!res.ok) throw new Error(`Failed to fetch LoRA job: ${res.status}`);
  return safeJson(res);
}
// ---------------------------------------------------------------------------
// LoRA Training Execution API
// ---------------------------------------------------------------------------

/**
 * Start a pending LoRA training job.
 * @param {string} jobId - The LoRA job ID
 * @param {string} [backendId='kohya_ss'] - Training backend to use
 * @returns {Promise<object>} The updated LoRA job
 */
export async function startLoRAJob(jobId, backendId = 'kohya_ss') {
  const res = await fetchWithTimeout(
    `${API_BASE}/lora/jobs/${encodeURIComponent(jobId)}/start?backend_id=${encodeURIComponent(backendId)}`,
    { method: 'POST' },
  )
  if (!res.ok) {
    let detail = `Failed to start LoRA job: ${res.status}`
    try {
      const errBody = await res.json()
      if (errBody.detail) detail = errBody.detail
    } catch { /* ignore */ }
    throw new Error(detail)
  }
  return safeJson(res)
}

/**
 * Cancel a running LoRA training job.
 * @param {string} jobId - The LoRA job ID
 * @returns {Promise<object>} The updated LoRA job
 */
export async function cancelLoRAJob(jobId) {
  const res = await fetchWithTimeout(
    `${API_BASE}/lora/jobs/${encodeURIComponent(jobId)}/cancel`,
    { method: 'POST' },
  )
  if (!res.ok) {
    let detail = `Failed to cancel LoRA job: ${res.status}`
    try {
      const errBody = await res.json()
      if (errBody.detail) detail = errBody.detail
    } catch { /* ignore */ }
    throw new Error(detail)
  }
  return safeJson(res)
}

/**
 * Get real-time training status for a LoRA job.
 * @param {string} jobId - The LoRA job ID
 * @returns {Promise<object>} Training status info
 */
export async function fetchLoRAJobStatus(jobId) {
  const res = await fetchWithTimeout(
    `${API_BASE}/lora/jobs/${encodeURIComponent(jobId)}/status`,
  )
  if (!res.ok) throw new Error(`Failed to fetch job status: ${res.status}`)
  return safeJson(res)
}

/**
 * Get training logs for a LoRA job.
 * @param {string} jobId - The LoRA job ID
 * @param {number} [tail=100] - Number of lines to read from the end
 * @returns {Promise<object>} Log output
 */
export async function fetchLoRAJobLogs(jobId, tail = 100) {
  const res = await fetchWithTimeout(
    `${API_BASE}/lora/jobs/${encodeURIComponent(jobId)}/logs?tail=${tail}`,
  )
  if (!res.ok) throw new Error(`Failed to fetch job logs: ${res.status}`)
  return safeJson(res)
}

/**
 * List available training backends.
 * @returns {Promise<object[]>} List of training backend configurations
 */
export async function fetchTrainingBackends() {
  const res = await fetchWithTimeout(`${API_BASE}/lora/training-backends`)
  if (!res.ok) throw new Error(`Failed to fetch training backends: ${res.status}`)
  return safeJson(res)
}

/**
 * Generate preview images for a completed LoRA job.
 * @param {string} jobId - The LoRA job ID
 * @param {string} serverUrl - ComfyUI server URL
 * @param {object} [options] - Optional generation parameters
 * @returns {Promise<object>} Preview generation results
 */
export async function generatePreviews(jobId, serverUrl, options = {}) {
  const params = new URLSearchParams({ server_url: serverUrl })
  if (options.negativePrompt) params.set('negative_prompt', options.negativePrompt)
  if (options.width) params.set('width', String(options.width))
  if (options.height) params.set('height', String(options.height))
  if (options.steps) params.set('steps', String(options.steps))
  if (options.cfg) params.set('cfg', String(options.cfg))
  if (options.seed) params.set('seed', String(options.seed))
  const res = await fetchWithTimeout(
    `${API_BASE}/lora/jobs/${encodeURIComponent(jobId)}/generate-previews?${params}`,
    { method: 'POST' },
    60_000, // 60s timeout for preview generation
  )
  if (!res.ok) {
    let detail = `Failed to generate previews: ${res.status}`
    try {
      const errBody = await res.json()
      if (errBody.detail) detail = errBody.detail
    } catch { /* ignore */ }
    throw new Error(detail)
  }
  return safeJson(res)
}

/**
 * List preview images for a LoRA job.
 * @param {string} jobId - The LoRA job ID
 * @returns {Promise<object>} Preview images info
 */
export async function fetchPreviewImages(jobId) {
  const res = await fetchWithTimeout(
    `${API_BASE}/lora/jobs/${encodeURIComponent(jobId)}/previews`,
  )
  if (!res.ok) throw new Error(`Failed to fetch preview images: ${res.status}`)
  return safeJson(res)
}

/**
 * Get LoRA metadata for a training job.
 * @param {string} jobId - The LoRA job ID
 * @returns {Promise<object>} LoRA metadata
 */
export async function fetchLoRAMetadata(jobId) {
  const res = await fetchWithTimeout(
    `${API_BASE}/lora/jobs/${encodeURIComponent(jobId)}/metadata`,
  )
  if (!res.ok) throw new Error(`Failed to fetch LoRA metadata: ${res.status}`)
  return safeJson(res)
}

/**
 * Export a trained LoRA to ComfyUI.
 * @param {string} jobId - The LoRA job ID
 * @param {string} comfyuiLoraDir - Path to ComfyUI's models/loras/ directory
 * @returns {Promise<object>} Export result
 */
export async function exportLoRA(jobId, comfyuiLoraDir) {
  const params = new URLSearchParams({ comfyui_lora_dir: comfyuiLoraDir })
  const res = await fetchWithTimeout(
    `${API_BASE}/lora/jobs/${encodeURIComponent(jobId)}/export?${params}`,
    { method: 'POST' },
  )
  if (!res.ok) {
    let detail = `Failed to export LoRA: ${res.status}`
    try {
      const errBody = await res.json()
      if (errBody.detail) detail = errBody.detail
    } catch { /* ignore */ }
    throw new Error(detail)
  }
  return safeJson(res)
}

/**
 * Get a ComfyUI workflow template for a character's LoRA.
 * @param {string} characterId - The character profile ID
 * @param {object} [options] - Optional workflow parameters
 * @returns {Promise<object>} Workflow template with metadata
 */
export async function fetchWorkflowTemplate(characterId, options = {}) {
  const params = new URLSearchParams()
  if (options.positivePrompt) params.set('positive_prompt', options.positivePrompt)
  if (options.negativePrompt) params.set('negative_prompt', options.negativePrompt)
  if (options.width) params.set('width', String(options.width))
  if (options.height) params.set('height', String(options.height))
  if (options.steps) params.set('steps', String(options.steps))
  if (options.cfg) params.set('cfg', String(options.cfg))
  if (options.seed) params.set('seed', String(options.seed))
  const qs = params.toString()
  const url = qs
    ? `${API_BASE}/lora/workflow-template/${encodeURIComponent(characterId)}?${qs}`
    : `${API_BASE}/lora/workflow-template/${encodeURIComponent(characterId)}`
  const res = await fetchWithTimeout(url)
  if (!res.ok) throw new Error(`Failed to fetch workflow template: ${res.status}`)
  return safeJson(res)
}

// ---------------------------------------------------------------------------
// LoRA Job Management API
// ---------------------------------------------------------------------------

/**
 * Get the download URL for a trained LoRA file.
 * This returns a URL string (not a fetch) because the browser handles
 * the download natively via an <a> tag or window.open.
 * @param {string} jobId - The LoRA job ID
 * @returns {string} The download URL
 */
export function getLoRADownloadUrl(jobId) {
  return `${API_BASE}/lora/jobs/${encodeURIComponent(jobId)}/download`
}

/**
 * Fetch version history for a LoRA job.
 * Returns a list of versioned LoRA files with metadata.
 * @param {string} jobId - The LoRA job ID
 * @returns {Promise<object>} Version list response with versions array
 */
export async function fetchLoRAVersions(jobId) {
  const res = await fetchWithTimeout(
    `${API_BASE}/lora/jobs/${encodeURIComponent(jobId)}/versions`,
  )
  if (!res.ok) {
    let detail = `Failed to fetch LoRA versions: ${res.status}`
    try {
      const errBody = await res.json()
      if (errBody.detail) detail = errBody.detail
    } catch { /* ignore */ }
    throw new Error(detail)
  }
  return safeJson(res)
}

/**
 * Delete a LoRA training job and its associated files.
 * Only completed, failed, or cancelled jobs can be deleted.
 * @param {string} jobId - The LoRA job ID to delete
 * @returns {Promise<object>} Deletion result with job_id and deleted_files
 */
export async function deleteLoRAJob(jobId) {
  const res = await fetchWithTimeout(
    `${API_BASE}/lora/jobs/${encodeURIComponent(jobId)}`,
    { method: 'DELETE' },
  )
  if (!res.ok) {
    let detail = `Failed to delete LoRA job: ${res.status}`
    try {
      const errBody = await res.json()
      if (errBody.detail) detail = errBody.detail
    } catch { /* ignore */ }
    throw new Error(detail)
  }
  return safeJson(res)
}

// ---------------------------------------------------------------------------
// Pose Batch API
// ---------------------------------------------------------------------------

/**
 * Fetch available pose batch templates.
 * @returns {Promise<object>} Pose batch templates list
 */
export async function fetchPoseBatches() {
  const res = await fetchWithTimeout(`${API_BASE}/pose-batches`);
  if (!res.ok) throw new Error(`Failed to fetch pose batches: ${res.status}`);
  return safeJson(res);
}

/**
 * Generate a pose batch of prompt pairs.
 * @param {object} params
 * @param {string} [params.characterId] - Character profile ID (auto-fills trigger token & profile)
 * @param {string} [params.loraTriggerToken] - LoRA trigger token to prepend
 * @param {string} [params.batchId] - Predefined pose batch template ID
 * @param {object[]} [params.poses] - Custom pose definitions [{name, pose}]
 * @param {string[]} [params.views] - Custom view angles
 * @param {object} [params.attributes] - Attribute selections
 * @param {string[]} [params.lockedFields] - Locked attribute categories
 * @param {string} [params.templateId] - Prompt template ID
 * @param {string} [params.negativeProfileId] - Negative profile ID
 * @param {string} [params.characterName] - Character name for output filename generation
 * @returns {Promise<object>} Pose batch response with batch_id and items (each with output_name)
 */
export async function generatePoseBatch(params = {}) {
  const body = {};
  if (params.characterId) body.character_id = params.characterId;
  if (params.loraTriggerToken) body.lora_trigger_token = params.loraTriggerToken;
  if (params.batchId) body.batch_id = params.batchId;
  if (params.poses) body.poses = params.poses;
  if (params.views) body.views = params.views;
  if (params.attributes) body.attributes = params.attributes;
  if (params.lockedFields?.length) body.locked_fields = params.lockedFields;
  if (params.templateId) body.template_id = params.templateId;
  if (params.negativeProfileId) body.negative_profile_id = params.negativeProfileId;
  if (params.characterName) body.character_name = params.characterName;

  const res = await fetchWithTimeout(`${API_BASE}/prompts/generate-batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `Failed to generate pose batch: ${res.status}`;
    try {
      const errBody = await res.json();
      if (errBody.detail) detail = errBody.detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }
  return safeJson(res);
}