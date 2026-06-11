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
  getLoRADownloadUrl: vi.fn(),
  fetchLoRAVersions: vi.fn(),
  deleteLoRAJob: vi.fn(),
}))

import {
  fetchLoRAMetadata,
  fetchPreviewImages,
  exportLoRA,
  fetchWorkflowTemplate,
  getLoRADownloadUrl,
  fetchLoRAVersions,
  deleteLoRAJob,
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
  getLoRADownloadUrl.mockReturnValue('/api/lora/jobs/lora_abc123/download')
  fetchLoRAVersions.mockResolvedValue({ job_id: 'lora_abc123', character_id: 'char_xyz789', versions: [], total: 0 })
  deleteLoRAJob.mockResolvedValue({ job_id: 'lora_abc123', character_id: 'char_xyz789', deleted_files: [] })
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

  it('shows download LoRA section', async () => {
    render(<LoraDetail jobId="lora_abc123" characterId="char_xyz789" showToast={mockToast} />)

    await waitFor(() => {
      expect(screen.getByText(/download lora/i)).toBeInTheDocument()
    })

    // The download link should have the correct href
    const downloadLink = screen.getByText(/download \.safetensors/i).closest('a')
    expect(downloadLink).toHaveAttribute('href', '/api/lora/jobs/lora_abc123/download')
    expect(downloadLink).toHaveAttribute('download')
  })

  it('shows version history section', async () => {
    render(<LoraDetail jobId="lora_abc123" characterId="char_xyz789" showToast={mockToast} />)

    await waitFor(() => {
      expect(screen.getByText(/version history/i)).toBeInTheDocument()
    })

    // Initially shows "no versioned files" message
    expect(screen.getByText(/no versioned lora files found/i)).toBeInTheDocument()
  })

  it('shows version history with versions', async () => {
    fetchLoRAVersions.mockResolvedValue({
      job_id: 'lora_abc123',
      character_id: 'char_xyz789',
      versions: [
        { version: 1, filename: 'DungeonRPG_Hero_Pixel32_v1.safetensors', size: 144179200, created_at: '2026-05-16T10:00:00Z', metadata: null },
        { version: 2, filename: 'DungeonRPG_Hero_Pixel32_v2.safetensors', size: 144179200, created_at: '2026-05-17T10:00:00Z', metadata: null },
      ],
      total: 2,
    })

    render(<LoraDetail jobId="lora_abc123" characterId="char_xyz789" showToast={mockToast} />)

    const user = userEvent.setup()
    await waitFor(() => {
      expect(screen.getByText(/version history/i)).toBeInTheDocument()
    })

    // Click Refresh to load versions
    await user.click(screen.getByText('Refresh'))

    await waitFor(() => {
      expect(screen.getByText(/DungeonRPG_Hero_Pixel32_v1\.safetensors/)).toBeInTheDocument()
      expect(screen.getByText(/DungeonRPG_Hero_Pixel32_v2\.safetensors/)).toBeInTheDocument()
    })
  })

  it('shows delete section with danger zone', async () => {
    render(<LoraDetail jobId="lora_abc123" characterId="char_xyz789" showToast={mockToast} />)

    await waitFor(() => {
      expect(screen.getByText(/danger zone/i)).toBeInTheDocument()
    })

    expect(screen.getByText(/delete lora job/i)).toBeInTheDocument()
  })

  it('shows delete confirmation when delete button clicked', async () => {
    render(<LoraDetail jobId="lora_abc123" characterId="char_xyz789" showToast={mockToast} />)

    await waitFor(() => {
      expect(screen.getByText(/danger zone/i)).toBeInTheDocument()
    })

    const user = userEvent.setup()
    await user.click(screen.getByText(/delete lora job/i))

    expect(screen.getByText(/this will permanently delete/i)).toBeInTheDocument()
    expect(screen.getByText(/confirm delete/i)).toBeInTheDocument()
    expect(screen.getByText('Cancel')).toBeInTheDocument()
  })

  it('calls onDelete callback after successful deletion', async () => {
    const mockOnDelete = vi.fn()
    render(<LoraDetail jobId="lora_abc123" characterId="char_xyz789" showToast={mockToast} onDelete={mockOnDelete} />)

    await waitFor(() => {
      expect(screen.getByText(/danger zone/i)).toBeInTheDocument()
    })

    const user = userEvent.setup()
    await user.click(screen.getByText(/delete lora job/i))
    await user.click(screen.getByText(/confirm delete/i))

    expect(deleteLoRAJob).toHaveBeenCalledWith('lora_abc123')
    expect(mockOnDelete).toHaveBeenCalledWith('lora_abc123')
  })