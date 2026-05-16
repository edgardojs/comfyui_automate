/**
 * Unit tests for the LoraDetail component.
 *
 * Tests:
 * - Loading state
 * - Metadata display
 * - Preview images display
 * - Export to ComfyUI
 * - Workflow template generation
 * - Copy workflow JSON
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import LoraDetail from '../components/LoraDetail'

vi.mock('../api/client', () => ({
  fetchLoRAMetadata: vi.fn(),
  fetchPreviewImages: vi.fn(),
  exportLoRA: vi.fn(),
  fetchWorkflowTemplate: vi.fn(),
}))

import {
  fetchLoRAMetadata,
  fetchPreviewImages,
  exportLoRA,
  fetchWorkflowTemplate,
} from '../api/client'

const MOCK_METADATA = {
  lora_name: 'DungeonRPG_Hero_Pixel32_v1',
  trigger_token: 'hero_v1',
  project: 'DungeonRPG',
  character: 'Hero',
  base_model: 'stabilityai/stable-diffusion-xl-base-1.0',
  base_model_filename: 'stable-diffusion-xl-base-1.0.safetensors',
  recommended_strength: 1.0,
  recommended_prompt_prefix: 'hero_v1, warrior full body pixel art sprite',
  dataset_count: 18,
  learning_rate: 0.0002,
  epochs: 18,
  created_at: '2026-05-16T10:00:00Z',
}

const MOCK_PREVIEWS = {
  job_id: 'lora_abc123',
  character_id: 'char_xyz789',
  previews: [
    { filename: 'preview_front_idle.png', path: '/path/to/preview_front_idle.png', size: 51200 },
    { filename: 'preview_side_idle.png', path: '/path/to/preview_side_idle.png', size: 48384 },
  ],
  total: 2,
}

const MOCK_WORKFLOW = {
  character_id: 'char_xyz789',
  job_id: 'lora_abc123',
  metadata: MOCK_METADATA,
  workflow: {
    '1': { class_type: 'CheckpointLoaderSimple', inputs: { ckpt_name: 'sdxl.safetensors' } },
    '2': { class_type: 'LoraLoader', inputs: { lora_name: 'lora.safetensors' } },
  },
}

const mockToast = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
  fetchLoRAMetadata.mockResolvedValue({ job_id: 'lora_abc123', metadata: MOCK_METADATA })
  fetchPreviewImages.mockResolvedValue(MOCK_PREVIEWS)
  exportLoRA.mockResolvedValue({ job_id: 'lora_abc123', export_path: '/path/to/lora.safetensors', exported: true })
  fetchWorkflowTemplate.mockResolvedValue(MOCK_WORKFLOW)
})

describe('LoraDetail', () => {
  it('shows loading state initially', () => {
    fetchLoRAMetadata.mockReturnValue(new Promise(() => {}))
    render(<LoraDetail jobId="lora_abc123" characterId="char_xyz789" showToast={mockToast} />)
    // Loading state shows skeleton with animate-pulse class
    const skeleton = document.querySelector('.animate-pulse')
    expect(skeleton).toBeInTheDocument()
  })

  it('displays metadata fields', async () => {
    render(<LoraDetail jobId="lora_abc123" characterId="char_xyz789" showToast={mockToast} />)

    // Wait for metadata section to appear
    await waitFor(() => {
      expect(screen.getByText('LoRA Metadata')).toBeInTheDocument()
    })

    expect(screen.getByText('hero_v1')).toBeInTheDocument()
    expect(screen.getByText('DungeonRPG_Hero_Pixel32_v1')).toBeInTheDocument()
    expect(screen.getByText('0.0002')).toBeInTheDocument()
    // "18" appears multiple times (epochs and dataset_count), so use getAllByText
    expect(screen.getAllByText('18').length).toBeGreaterThanOrEqual(1)
  })

  it('displays recommended prompt prefix', async () => {
    render(<LoraDetail jobId="lora_abc123" characterId="char_xyz789" showToast={mockToast} />)

    await waitFor(() => {
      expect(screen.getByText(/recommended prompt prefix/i)).toBeInTheDocument()
      expect(screen.getByText(/hero_v1, warrior full body pixel art sprite/i)).toBeInTheDocument()
    })
  })

  it('displays preview images', async () => {
    render(<LoraDetail jobId="lora_abc123" characterId="char_xyz789" showToast={mockToast} />)

    await waitFor(() => {
      expect(screen.getByText(/preview_front_idle\.png/)).toBeInTheDocument()
      expect(screen.getByText(/preview_side_idle\.png/)).toBeInTheDocument()
    })
  })

  it('shows export section', async () => {
    render(<LoraDetail jobId="lora_abc123" characterId="char_xyz789" showToast={mockToast} />)

    await waitFor(() => {
      expect(screen.getByText(/export to comfyui/i)).toBeInTheDocument()
      expect(screen.getByPlaceholderText(/path\/to\/comfyui/i)).toBeInTheDocument()
    })
  })

  it('exports LoRA when button clicked', async () => {
    render(<LoraDetail jobId="lora_abc123" characterId="char_xyz789" showToast={mockToast} />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /📤 export/i })).toBeInTheDocument()
    })

    const user = userEvent.setup()
    const input = screen.getByPlaceholderText(/path\/to\/comfyui/i)
    await user.type(input, '/models/loras')
    await user.click(screen.getByRole('button', { name: /📤 export/i }))

    expect(exportLoRA).toHaveBeenCalledWith('lora_abc123', '/models/loras')
  })

  it('generates workflow template', async () => {
    render(<LoraDetail jobId="lora_abc123" characterId="char_xyz789" showToast={mockToast} />)

    await waitFor(() => {
      expect(screen.getByText(/generate workflow/i)).toBeInTheDocument()
    })

    const user = userEvent.setup()
    await user.click(screen.getByText(/generate workflow/i))

    expect(fetchWorkflowTemplate).toHaveBeenCalledWith('char_xyz789')
  })

  it('shows no previews message when empty', async () => {
    fetchPreviewImages.mockResolvedValue({ previews: [], total: 0 })
    render(<LoraDetail jobId="lora_abc123" characterId="char_xyz789" showToast={mockToast} />)

    await waitFor(() => {
      expect(screen.getByText(/no preview images yet/i)).toBeInTheDocument()
    })
  })

  it('displays base model filename', async () => {
    render(<LoraDetail jobId="lora_abc123" characterId="char_xyz789" showToast={mockToast} />)

    await waitFor(() => {
      expect(screen.getByText('stable-diffusion-xl-base-1.0.safetensors')).toBeInTheDocument()
    })
  })
})