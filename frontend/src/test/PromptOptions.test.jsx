/**
 * Unit tests for the PromptOptions component.
 *
 * Tests:
 * - Loading state
 * - Error state with retry
 * - Variation count selector
 * - Template and profile dropdowns
 * - Generate button
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import PromptOptions from '../components/PromptOptions'

vi.mock('../api/client', () => ({
  fetchTemplates: vi.fn(),
  fetchNegativeProfiles: vi.fn(),
}))

import { fetchTemplates, fetchNegativeProfiles } from '../api/client'

const MOCK_TEMPLATES = [
  { id: 'front_view_sprite', label: 'Front View Sprite' },
  { id: 'side_view_sprite', label: 'Side View Sprite' },
]

const MOCK_PROFILES = [
  { id: 'general_sprite_cleanup', label: 'General Sprite Cleanup' },
  { id: 'dark_fantasy', label: 'Dark Fantasy' },
]

const DEFAULT_PROPS = {
  variationCount: 1,
  templateId: 'front_view_sprite',
  negativeProfileId: 'general_sprite_cleanup',
  onVariationCountChange: vi.fn(),
  onTemplateIdChange: vi.fn(),
  onNegativeProfileIdChange: vi.fn(),
  onGenerate: vi.fn(),
  isGenerating: false,
}

describe('PromptOptions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders loading state initially', () => {
    fetchTemplates.mockReturnValue(new Promise(() => {}))
    fetchNegativeProfiles.mockReturnValue(new Promise(() => {}))
    render(<PromptOptions {...DEFAULT_PROPS} />)

    expect(screen.getByText('Prompt Options')).toBeInTheDocument()
  })

  it('renders variation count buttons', async () => {
    fetchTemplates.mockResolvedValue({ templates: MOCK_TEMPLATES })
    fetchNegativeProfiles.mockResolvedValue({ profiles: MOCK_PROFILES })
    render(<PromptOptions {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('1')).toBeInTheDocument()
      expect(screen.getByText('5')).toBeInTheDocument()
      expect(screen.getByText('10')).toBeInTheDocument()
      expect(screen.getByText('25')).toBeInTheDocument()
    })
  })

  it('highlights selected variation count', async () => {
    fetchTemplates.mockResolvedValue({ templates: MOCK_TEMPLATES })
    fetchNegativeProfiles.mockResolvedValue({ profiles: MOCK_PROFILES })
    render(<PromptOptions {...DEFAULT_PROPS} variationCount={5} />)

    await waitFor(() => {
      const btn5 = screen.getByText('5')
      expect(btn5.className).toContain('bg-indigo-600')
    })
  })

  it('calls onVariationCountChange when variation button clicked', async () => {
    const user = userEvent.setup()
    fetchTemplates.mockResolvedValue({ templates: MOCK_TEMPLATES })
    fetchNegativeProfiles.mockResolvedValue({ profiles: MOCK_PROFILES })
    render(<PromptOptions {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('10')).toBeInTheDocument()
    })

    await user.click(screen.getByText('10'))

    expect(DEFAULT_PROPS.onVariationCountChange).toHaveBeenCalledWith(10)
  })

  it('renders template dropdown with options', async () => {
    fetchTemplates.mockResolvedValue({ templates: MOCK_TEMPLATES })
    fetchNegativeProfiles.mockResolvedValue({ profiles: MOCK_PROFILES })
    render(<PromptOptions {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('Front View Sprite')).toBeInTheDocument()
      expect(screen.getByText('Side View Sprite')).toBeInTheDocument()
    })
  })

  it('renders negative profile dropdown with options', async () => {
    fetchTemplates.mockResolvedValue({ templates: MOCK_TEMPLATES })
    fetchNegativeProfiles.mockResolvedValue({ profiles: MOCK_PROFILES })
    render(<PromptOptions {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('General Sprite Cleanup')).toBeInTheDocument()
      expect(screen.getByText('Dark Fantasy')).toBeInTheDocument()
    })
  })

  it('renders Generate button', async () => {
    fetchTemplates.mockResolvedValue({ templates: MOCK_TEMPLATES })
    fetchNegativeProfiles.mockResolvedValue({ profiles: MOCK_PROFILES })
    render(<PromptOptions {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText(/Generate Prompts/)).toBeInTheDocument()
    })
  })

  it('calls onGenerate when Generate button clicked', async () => {
    const user = userEvent.setup()
    fetchTemplates.mockResolvedValue({ templates: MOCK_TEMPLATES })
    fetchNegativeProfiles.mockResolvedValue({ profiles: MOCK_PROFILES })
    render(<PromptOptions {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText(/Generate Prompts/)).toBeInTheDocument()
    })

    await user.click(screen.getByText(/Generate Prompts/))

    expect(DEFAULT_PROPS.onGenerate).toHaveBeenCalledTimes(1)
  })

  it('shows spinner when generating', async () => {
    fetchTemplates.mockResolvedValue({ templates: MOCK_TEMPLATES })
    fetchNegativeProfiles.mockResolvedValue({ profiles: MOCK_PROFILES })
    render(<PromptOptions {...DEFAULT_PROPS} isGenerating={true} />)

    await waitFor(() => {
      expect(screen.getByText('Generating…')).toBeInTheDocument()
    })
  })

  it('disables Generate button when generating', async () => {
    fetchTemplates.mockResolvedValue({ templates: MOCK_TEMPLATES })
    fetchNegativeProfiles.mockResolvedValue({ profiles: MOCK_PROFILES })
    render(<PromptOptions {...DEFAULT_PROPS} isGenerating={true} />)

    await waitFor(() => {
      const btn = screen.getByRole('button', { name: /generating/i })
      expect(btn).toBeDisabled()
    })
  })

  it('renders error state with retry when fetch fails', async () => {
    fetchTemplates.mockRejectedValue(new Error('Server error'))
    fetchNegativeProfiles.mockResolvedValue({ profiles: MOCK_PROFILES })
    render(<PromptOptions {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText(/Failed to load options/)).toBeInTheDocument()
      expect(screen.getByText('Retry')).toBeInTheDocument()
    })
  })

  it('retries fetch when retry button clicked', async () => {
    const user = userEvent.setup()
    fetchTemplates.mockRejectedValueOnce(new Error('Server error'))
    fetchTemplates.mockResolvedValue({ templates: MOCK_TEMPLATES })
    fetchNegativeProfiles.mockResolvedValue({ profiles: MOCK_PROFILES })

    render(<PromptOptions {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('Retry')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Retry'))

    await waitFor(() => {
      expect(screen.getByText('Front View Sprite')).toBeInTheDocument()
    })
  })
})