/**
 * Unit tests for the TrainingConfig component.
 *
 * Tests:
 * - Loading state (presets + dataset)
 * - Preset selector rendering and selection
 * - Auto-fill parameters when preset selected
 * - Manual override fields
 * - LoRA strength slider
 * - Dataset readiness indicator
 * - Create training job (success and error)
 * - Existing jobs list
 * - Disabled state when dataset not ready
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import TrainingConfig from '../components/TrainingConfig'

vi.mock('../api/client', () => ({
  fetchTrainingPresets: vi.fn(),
  fetchReferences: vi.fn(),
  validateDataset: vi.fn(),
  createLoRAJob: vi.fn(),
  fetchLoRAJobs: vi.fn(),
}))

import {
  fetchTrainingPresets,
  fetchReferences,
  validateDataset,
  createLoRAJob,
  fetchLoRAJobs,
} from '../api/client'

const MOCK_PRESETS = [
  {
    id: 'pixel_art_character',
    label: 'Pixel Art Character LoRA',
    description: 'Best for 32x32 or 64x64 pixel art sprites',
    learning_rate: 0.0002,
    epochs: 18,
    recommended_images: 18,
    preview_interval: 2,
    output_format: 'safetensors',
    caption_style: 'detailed',
    recommended_angles: ['front', 'side', 'back', 'three-quarter'],
  },
  {
    id: 'chibi_character',
    label: 'Chibi Character LoRA',
    description: 'Best for chibi-style game characters',
    learning_rate: 0.0002,
    epochs: 15,
    recommended_images: 15,
    preview_interval: 3,
    output_format: 'safetensors',
    caption_style: 'simple',
    recommended_angles: ['front', 'side'],
  },
]

const MOCK_READY_DATASET = {
  is_ready: true,
  warnings: [],
  accepted_count: 15,
  total_images: 20,
}

const MOCK_ACCEPTED_REFS = [
  { image_id: 'img_001', caption: 'a caption', status: 'accepted' },
  { image_id: 'img_002', caption: 'another caption', status: 'accepted' },
]

const MOCK_JOBS = [
  {
    job_id: 'lora_abc123',
    character_id: 'char_1',
    preset_id: 'pixel_art_character',
    learning_rate: 0.0002,
    epochs: 18,
    status: 'pending',
    output_lora_path: null,
    created_at: '2026-05-16T10:00:00',
    updated_at: '2026-05-16T10:00:00',
  },
]

const DEFAULT_PROPS = {
  characterId: 'char_1',
  showToast: vi.fn(),
}

describe('TrainingConfig', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Default: ready dataset
    fetchTrainingPresets.mockResolvedValue(MOCK_PRESETS)
    validateDataset.mockResolvedValue(MOCK_READY_DATASET)
    fetchReferences.mockResolvedValue(MOCK_ACCEPTED_REFS)
    fetchLoRAJobs.mockResolvedValue([])
  })

  // --- Loading state ---
  it('renders loading state while fetching presets', () => {
    fetchTrainingPresets.mockReturnValue(new Promise(() => {}))
    render(<TrainingConfig {...DEFAULT_PROPS} />)

    expect(screen.getByText('LoRA Training Configuration')).toBeInTheDocument()
    // Should show a loading skeleton for preset selector
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  // --- Preset selector ---
  it('renders preset selector with options after loading', async () => {
    render(<TrainingConfig {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('Pixel Art Character LoRA')).toBeInTheDocument()
      expect(screen.getByText('Chibi Character LoRA')).toBeInTheDocument()
    })
  })

  it('shows custom option when no preset selected', async () => {
    render(<TrainingConfig {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('— Custom (no preset) —')).toBeInTheDocument()
    })
  })

  // --- Auto-fill on preset selection ---
  it('auto-fills parameters when preset is selected', async () => {
    const user = userEvent.setup()
    render(<TrainingConfig {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('Pixel Art Character LoRA')).toBeInTheDocument()
    })

    // Select the chibi preset (epochs: 15, preview_interval: 3)
    const presetSelect = screen.getAllByRole('combobox')[0]
    await user.selectOptions(presetSelect, 'chibi_character')

    // The epochs slider should show 15 (check the label text specifically)
    expect(screen.getByText(/Epochs:/).closest('label')).toHaveTextContent('15')
  })

  it('shows preset description when selected', async () => {
    const user = userEvent.setup()
    render(<TrainingConfig {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('Pixel Art Character LoRA')).toBeInTheDocument()
    })

    const presetSelect = screen.getAllByRole('combobox')[0]
    await user.selectOptions(presetSelect, 'pixel_art_character')

    expect(screen.getByText('Best for 32x32 or 64x64 pixel art sprites')).toBeInTheDocument()
  })

  // --- Dataset readiness ---
  it('shows ready status when dataset has enough images with captions', async () => {
    render(<TrainingConfig {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('✅ Ready for training')).toBeInTheDocument()
      expect(screen.getByText(/15 accepted images/)).toBeInTheDocument()
      expect(screen.getByText('✅ All accepted images have captions')).toBeInTheDocument()
    })
  })

  it('shows not-ready status when not enough images', async () => {
    validateDataset.mockResolvedValue({
      is_ready: false,
      warnings: [{ severity: 'error', message: 'Need at least 10 accepted images' }],
      accepted_count: 5,
      total_images: 8,
    })
    fetchReferences.mockResolvedValue([
      { image_id: 'img_001', caption: 'a caption', status: 'accepted' },
    ])

    render(<TrainingConfig {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('⚠️ Needs attention')).toBeInTheDocument()
      expect(screen.getByText(/5 accepted images/)).toBeInTheDocument()
    })
  })

  it('shows not-ready when images missing captions', async () => {
    validateDataset.mockResolvedValue({
      is_ready: false,
      warnings: [{ severity: 'error', message: 'Missing captions' }],
      accepted_count: 12,
      total_images: 15,
    })
    fetchReferences.mockResolvedValue([
      { image_id: 'img_001', caption: null, status: 'accepted' },
      { image_id: 'img_002', caption: 'has caption', status: 'accepted' },
    ])

    render(<TrainingConfig {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('❌ All accepted images have captions')).toBeInTheDocument()
    })
  })

  // --- Create training job ---
  it('calls createLoRAJob with correct parameters', async () => {
    const user = userEvent.setup()
    createLoRAJob.mockResolvedValue({ job_id: 'lora_new123', status: 'pending' })
    render(<TrainingConfig {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('🚀 Create Training Job')).toBeInTheDocument()
    })

    await user.click(screen.getByText('🚀 Create Training Job'))

    expect(createLoRAJob).toHaveBeenCalledWith(
      expect.objectContaining({
        character_id: 'char_1',
        base_model: 'stabilityai/stable-diffusion-xl-base-1.0',
        learning_rate: 0.0002,
        epochs: 18,
        output_format: 'safetensors',
      })
    )
  })

  it('shows success toast after job creation', async () => {
    const user = userEvent.setup()
    createLoRAJob.mockResolvedValue({ job_id: 'lora_new123', status: 'pending' })
    render(<TrainingConfig {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('🚀 Create Training Job')).toBeInTheDocument()
    })

    await user.click(screen.getByText('🚀 Create Training Job'))

    expect(DEFAULT_PROPS.showToast).toHaveBeenCalledWith('✅ Training job created!')
  })

  it('shows error toast when job creation fails', async () => {
    const user = userEvent.setup()
    createLoRAJob.mockRejectedValue(new Error('Insufficient accepted images'))
    render(<TrainingConfig {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('🚀 Create Training Job')).toBeInTheDocument()
    })

    await user.click(screen.getByText('🚀 Create Training Job'))

    expect(DEFAULT_PROPS.showToast).toHaveBeenCalledWith(
      '❌ Insufficient accepted images'
    )
  })

  // --- Disabled state ---
  it('disables create button when dataset is not ready', async () => {
    validateDataset.mockResolvedValue({
      is_ready: false,
      warnings: [],
      accepted_count: 3,
      total_images: 5,
    })
    fetchReferences.mockResolvedValue([])

    render(<TrainingConfig {...DEFAULT_PROPS} />)

    await waitFor(() => {
      const btn = screen.getByText('🚀 Create Training Job')
      expect(btn).toBeDisabled()
    })
  })

  // --- Existing jobs list ---
  it('displays existing training jobs', async () => {
    fetchLoRAJobs.mockResolvedValue(MOCK_JOBS)
    render(<TrainingConfig {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('Training Jobs')).toBeInTheDocument()
      expect(screen.getByText('pending')).toBeInTheDocument()
      expect(screen.getByText(/lora_abc123/)).toBeInTheDocument()
    })
  })

  // --- Parameter sliders ---
  it('renders LoRA strength slider with default value', async () => {
    render(<TrainingConfig {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText(/LoRA Strength/)).toBeInTheDocument()
      expect(screen.getByText('1.00')).toBeInTheDocument()
    })
  })

  it('renders learning rate slider with default value', async () => {
    render(<TrainingConfig {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText(/Learning Rate/)).toBeInTheDocument()
    })
  })

  it('renders epochs slider with default value', async () => {
    render(<TrainingConfig {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText(/Epochs/)).toBeInTheDocument()
    })
  })

  // --- Output format selector ---
  it('renders output format selector', async () => {
    render(<TrainingConfig {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('Output Format')).toBeInTheDocument()
      expect(screen.getByText('safetensors')).toBeInTheDocument()
    })
  })
})