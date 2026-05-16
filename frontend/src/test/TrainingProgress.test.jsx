/**
 * Unit tests for the TrainingProgress component.
 *
 * Tests:
 * - Loading state
 * - Job status display (pending, running, completed, failed)
 * - Start button for pending jobs
 * - Cancel button for running jobs
 * - Configuration summary display
 * - Log output display
 * - Auto-refresh behavior
 * - Backend selector
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import TrainingProgress from '../components/TrainingProgress'

vi.mock('../api/client', () => ({
  fetchLoRAJob: vi.fn(),
  fetchLoRAJobStatus: vi.fn(),
  fetchLoRAJobLogs: vi.fn(),
  startLoRAJob: vi.fn(),
  cancelLoRAJob: vi.fn(),
  fetchTrainingBackends: vi.fn(),
}))

import {
  fetchLoRAJob,
  fetchLoRAJobStatus,
  fetchLoRAJobLogs,
  startLoRAJob,
  cancelLoRAJob,
  fetchTrainingBackends,
} from '../api/client'

const MOCK_JOB_PENDING = {
  job_id: 'lora_abc123',
  character_id: 'char_xyz789',
  status: 'pending',
  config: {
    base_model: 'stabilityai/stable-diffusion-xl-base-1.0',
    learning_rate: 0.0002,
    epochs: 18,
    lora_strength: 1.0,
    output_format: 'safetensors',
    preset_id: 'pixel_art_character',
  },
  created_at: '2026-05-16T10:00:00Z',
  updated_at: '2026-05-16T10:00:00Z',
}

const MOCK_JOB_RUNNING = {
  ...MOCK_JOB_PENDING,
  status: 'running',
  log_output: 'Epoch 1/18: loss=0.5234\nEpoch 2/18: loss=0.4123\n',
  updated_at: '2026-05-16T10:05:00Z',
}

const MOCK_JOB_COMPLETED = {
  ...MOCK_JOB_PENDING,
  status: 'completed',
  output_lora_path: '/path/to/lora.safetensors',
  updated_at: '2026-05-16T11:00:00Z',
}

const MOCK_JOB_FAILED = {
  ...MOCK_JOB_PENDING,
  status: 'failed',
  log_output: 'Error: Training failed\n',
  updated_at: '2026-05-16T10:30:00Z',
}

const MOCK_BACKENDS = [
  { id: 'kohya_ss', label: 'Kohya_ss', description: 'Popular LoRA training tool' },
  { id: 'ai_toolkit', label: 'AI Toolkit', description: 'All-in-one training toolkit' },
]

const mockToast = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
  fetchLoRAJob.mockResolvedValue(MOCK_JOB_PENDING)
  fetchLoRAJobStatus.mockResolvedValue({ job_id: 'lora_abc123', is_running: false, pid: null })
  fetchLoRAJobLogs.mockResolvedValue({ job_id: 'lora_abc123', logs: '', tail: 100 })
  fetchTrainingBackends.mockResolvedValue(MOCK_BACKENDS)
  startLoRAJob.mockResolvedValue(MOCK_JOB_RUNNING)
  cancelLoRAJob.mockResolvedValue(MOCK_JOB_FAILED)
})

describe('TrainingProgress', () => {
  it('shows loading state initially', () => {
    fetchLoRAJob.mockReturnValue(new Promise(() => {})) // never resolves
    render(<TrainingProgress jobId="lora_abc123" showToast={mockToast} />)
    // Loading state shows skeleton with animate-pulse class
    const skeleton = document.querySelector('.animate-pulse')
    expect(skeleton).toBeInTheDocument()
  })

  it('displays pending job status', async () => {
    fetchLoRAJob.mockResolvedValue(MOCK_JOB_PENDING)
    render(<TrainingProgress jobId="lora_abc123" showToast={mockToast} />)

    await waitFor(() => {
      expect(screen.getByText('PENDING')).toBeInTheDocument()
    })
  })

  it('displays running job status', async () => {
    fetchLoRAJob.mockResolvedValue(MOCK_JOB_RUNNING)
    render(<TrainingProgress jobId="lora_abc123" showToast={mockToast} />)

    await waitFor(() => {
      expect(screen.getByText('RUNNING')).toBeInTheDocument()
    })
  })

  it('displays completed job status', async () => {
    fetchLoRAJob.mockResolvedValue(MOCK_JOB_COMPLETED)
    render(<TrainingProgress jobId="lora_abc123" showToast={mockToast} />)

    await waitFor(() => {
      expect(screen.getByText('COMPLETED')).toBeInTheDocument()
    })
  })

  it('displays failed job status', async () => {
    fetchLoRAJob.mockResolvedValue(MOCK_JOB_FAILED)
    render(<TrainingProgress jobId="lora_abc123" showToast={mockToast} />)

    await waitFor(() => {
      expect(screen.getByText('FAILED')).toBeInTheDocument()
    })
  })

  it('shows start button for pending jobs', async () => {
    fetchLoRAJob.mockResolvedValue(MOCK_JOB_PENDING)
    render(<TrainingProgress jobId="lora_abc123" showToast={mockToast} />)

    await waitFor(() => {
      expect(screen.getByText(/start training/i)).toBeInTheDocument()
    })
  })

  it('shows cancel button for running jobs', async () => {
    fetchLoRAJob.mockResolvedValue(MOCK_JOB_RUNNING)
    render(<TrainingProgress jobId="lora_abc123" showToast={mockToast} />)

    await waitFor(() => {
      expect(screen.getByText(/cancel training/i)).toBeInTheDocument()
    })
  })

  it('shows configuration summary', async () => {
    fetchLoRAJob.mockResolvedValue(MOCK_JOB_PENDING)
    render(<TrainingProgress jobId="lora_abc123" showToast={mockToast} />)

    await waitFor(() => {
      expect(screen.getByText('lora_abc123')).toBeInTheDocument()
      expect(screen.getByText('0.0002')).toBeInTheDocument()
      expect(screen.getByText('18')).toBeInTheDocument()
    })
  })

  it('shows backend selector for pending jobs', async () => {
    fetchLoRAJob.mockResolvedValue(MOCK_JOB_PENDING)
    render(<TrainingProgress jobId="lora_abc123" showToast={mockToast} />)

    await waitFor(() => {
      expect(screen.getByText(/kohya_ss/i)).toBeInTheDocument()
    })
  })

  it('starts training when start button clicked', async () => {
    fetchLoRAJob.mockResolvedValue(MOCK_JOB_PENDING)
    render(<TrainingProgress jobId="lora_abc123" showToast={mockToast} />)

    await waitFor(() => {
      expect(screen.getByText(/start training/i)).toBeInTheDocument()
    })

    const user = userEvent.setup()
    await user.click(screen.getByText(/start training/i))

    expect(startLoRAJob).toHaveBeenCalledWith('lora_abc123', 'kohya_ss')
  })

  it('cancels training when cancel button clicked with confirmation', async () => {
    fetchLoRAJob.mockResolvedValue(MOCK_JOB_RUNNING)
    // Mock window.confirm to return true
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<TrainingProgress jobId="lora_abc123" showToast={mockToast} />)

    await waitFor(() => {
      expect(screen.getByText(/cancel training/i)).toBeInTheDocument()
    })

    const user = userEvent.setup()
    await user.click(screen.getByText(/cancel training/i))

    expect(cancelLoRAJob).toHaveBeenCalledWith('lora_abc123')
  })

  it('does not cancel when confirmation is denied', async () => {
    fetchLoRAJob.mockResolvedValue(MOCK_JOB_RUNNING)
    vi.spyOn(window, 'confirm').mockReturnValue(false)

    render(<TrainingProgress jobId="lora_abc123" showToast={mockToast} />)

    await waitFor(() => {
      expect(screen.getByText(/cancel training/i)).toBeInTheDocument()
    })

    const user = userEvent.setup()
    await user.click(screen.getByText(/cancel training/i))

    expect(cancelLoRAJob).not.toHaveBeenCalled()
  })

  it('shows log output for running jobs', async () => {
    fetchLoRAJob.mockResolvedValue(MOCK_JOB_RUNNING)
    render(<TrainingProgress jobId="lora_abc123" showToast={mockToast} />)

    await waitFor(() => {
      expect(screen.getByText(/training log/i)).toBeInTheDocument()
    })
  })

  it('shows timestamps', async () => {
    fetchLoRAJob.mockResolvedValue(MOCK_JOB_PENDING)
    render(<TrainingProgress jobId="lora_abc123" showToast={mockToast} />)

    await waitFor(() => {
      expect(screen.getByText(/created:/i)).toBeInTheDocument()
    })
  })
})