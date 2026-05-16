/**
 * Unit tests for the PresetManager component.
 *
 * Tests:
 * - Loading state
 * - Error state with retry
 * - Save dialog flow
 * - Preset list rendering
 * - Load button
 * - Delete confirmation flow
 * - Empty state
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import PresetManager from '../components/PresetManager'

vi.mock('../api/client', () => ({
  fetchPresets: vi.fn(),
  savePreset: vi.fn(),
  deletePreset: vi.fn(),
}))

import { fetchPresets, savePreset, deletePreset } from '../api/client'

const MOCK_PRESETS = [
  {
    preset_id: 'preset_1',
    name: 'Rogue Elf',
    attributes: { classes: 'rogue', species: 'elf' },
    locked_fields: ['classes'],
    positive_template_id: 'front_view_sprite',
    negative_profile_id: 'general_sprite_cleanup',
  },
  {
    preset_id: 'preset_2',
    name: 'Mage Human',
    attributes: { classes: 'mage', species: 'human' },
    locked_fields: [],
    positive_template_id: 'side_view_sprite',
    negative_profile_id: 'dark_fantasy',
  },
]

const DEFAULT_PROPS = {
  currentAttributes: { classes: 'rogue' },
  currentLockedFields: ['classes'],
  currentTemplateId: 'front_view_sprite',
  currentNegativeProfileId: 'general_sprite_cleanup',
  onLoadPreset: vi.fn(),
  showToast: vi.fn(),
}

describe('PresetManager', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders loading skeleton while fetching', () => {
    fetchPresets.mockReturnValue(new Promise(() => {}))
    render(<PresetManager {...DEFAULT_PROPS} />)

    expect(screen.getByText('Presets')).toBeInTheDocument()
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('renders error state with retry on fetch failure', async () => {
    fetchPresets.mockRejectedValue(new Error('Network error'))
    render(<PresetManager {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText(/Failed to load presets/)).toBeInTheDocument()
      expect(screen.getByText('Retry')).toBeInTheDocument()
    })
  })

  it('renders empty state when no presets', async () => {
    fetchPresets.mockResolvedValue([])
    render(<PresetManager {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('No presets saved yet.')).toBeInTheDocument()
    })
  })

  it('renders preset list with names', async () => {
    fetchPresets.mockResolvedValue(MOCK_PRESETS)
    render(<PresetManager {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('Rogue Elf')).toBeInTheDocument()
      expect(screen.getByText('Mage Human')).toBeInTheDocument()
    })
  })

  it('renders attribute tags for presets', async () => {
    fetchPresets.mockResolvedValue(MOCK_PRESETS)
    render(<PresetManager {...DEFAULT_PROPS} />)

    await waitFor(() => {
      // Attribute values shown as tags
      expect(screen.getByText('rogue')).toBeInTheDocument()
      expect(screen.getByText('elf')).toBeInTheDocument()
    })
  })

  it('opens save dialog when Save Current clicked', async () => {
    const user = userEvent.setup()
    fetchPresets.mockResolvedValue([])
    render(<PresetManager {...DEFAULT_PROPS} />)

    await waitFor(() => {
      // Use exact text match for the header button (includes emoji)
      expect(screen.getByText('💾 Save Current')).toBeInTheDocument()
    })

    await user.click(screen.getByText('💾 Save Current'))

    await waitFor(() => {
      expect(screen.getByPlaceholderText('My favorite combo...')).toBeInTheDocument()
    })
  })

  it('saves preset with entered name', async () => {
    const user = userEvent.setup()
    fetchPresets.mockResolvedValue([])
    savePreset.mockResolvedValue({ preset_id: 'preset_new', name: 'My Preset' })
    fetchPresets.mockResolvedValue([{ preset_id: 'preset_new', name: 'My Preset', attributes: {} }])

    render(<PresetManager {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('💾 Save Current')).toBeInTheDocument()
    })

    await user.click(screen.getByText('💾 Save Current'))

    const input = await screen.findByPlaceholderText('My favorite combo...')
    await user.type(input, 'My Preset')
    // Find the Save button in the dialog (small button, not the header button)
    const dialogSaveBtn = screen.getByRole('button', { name: 'Save' })
    await user.click(dialogSaveBtn)

    expect(savePreset).toHaveBeenCalledWith({
      name: 'My Preset',
      attributes: DEFAULT_PROPS.currentAttributes,
      locked_fields: DEFAULT_PROPS.currentLockedFields,
      positive_template_id: DEFAULT_PROPS.currentTemplateId,
      negative_profile_id: DEFAULT_PROPS.currentNegativeProfileId,
    })
  })

  it('shows toast on save success', async () => {
    const user = userEvent.setup()
    fetchPresets.mockResolvedValue([])
    savePreset.mockResolvedValue({ preset_id: 'preset_new', name: 'Test' })
    fetchPresets.mockResolvedValue([])

    render(<PresetManager {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('💾 Save Current')).toBeInTheDocument()
    })

    await user.click(screen.getByText('💾 Save Current'))

    const input = await screen.findByPlaceholderText('My favorite combo...')
    await user.type(input, 'Test')
    const dialogSaveBtn = screen.getByRole('button', { name: 'Save' })
    await user.click(dialogSaveBtn)

    await waitFor(() => {
      expect(DEFAULT_PROPS.showToast).toHaveBeenCalledWith('Preset "Test" saved!')
    })
  })

  it('shows toast on save failure', async () => {
    const user = userEvent.setup()
    fetchPresets.mockResolvedValue([])
    savePreset.mockRejectedValue(new Error('Server error'))

    render(<PresetManager {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('💾 Save Current')).toBeInTheDocument()
    })

    await user.click(screen.getByText('💾 Save Current'))

    const input = await screen.findByPlaceholderText('My favorite combo...')
    await user.type(input, 'Test')
    const dialogSaveBtn = screen.getByRole('button', { name: 'Save' })
    await user.click(dialogSaveBtn)

    await waitFor(() => {
      expect(DEFAULT_PROPS.showToast).toHaveBeenCalledWith('Failed to save preset: Server error')
    })
  })

  it('calls onLoadPreset when Load button clicked', async () => {
    const user = userEvent.setup()
    fetchPresets.mockResolvedValue(MOCK_PRESETS)
    render(<PresetManager {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('Rogue Elf')).toBeInTheDocument()
    })

    const loadButtons = screen.getAllByText('Load')
    await user.click(loadButtons[0])

    expect(DEFAULT_PROPS.onLoadPreset).toHaveBeenCalledWith({
      attributes: { classes: 'rogue', species: 'elf' },
      lockedFields: ['classes'],
      templateId: 'front_view_sprite',
      negativeProfileId: 'general_sprite_cleanup',
    })
  })

  it('shows delete confirmation when delete button clicked', async () => {
    const user = userEvent.setup()
    fetchPresets.mockResolvedValue(MOCK_PRESETS)
    render(<PresetManager {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('Rogue Elf')).toBeInTheDocument()
    })

    // Find delete buttons (🗑️)
    const deleteButtons = screen.getAllByTitle('Delete this preset')
    await user.click(deleteButtons[0])

    await waitFor(() => {
      expect(screen.getByText('Delete Preset')).toBeInTheDocument()
      expect(screen.getByText(/Are you sure/)).toBeInTheDocument()
    })
  })

  it('deletes preset when confirmed', async () => {
    const user = userEvent.setup()
    // Initial load returns both presets
    fetchPresets.mockResolvedValue(MOCK_PRESETS)
    deletePreset.mockResolvedValue(undefined)

    render(<PresetManager {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('Rogue Elf')).toBeInTheDocument()
    })

    const deleteButtons = screen.getAllByTitle('Delete this preset')
    await user.click(deleteButtons[0])

    await waitFor(() => {
      expect(screen.getByText('Delete Preset')).toBeInTheDocument()
    })

    // After delete, refresh returns only the remaining preset
    fetchPresets.mockResolvedValue([MOCK_PRESETS[1]])

    // Click the red Delete button in the confirmation dialog
    const confirmButtons = screen.getAllByRole('button', { name: 'Delete' })
    // The last one is the red confirmation button
    await user.click(confirmButtons[confirmButtons.length - 1])

    await waitFor(() => {
      expect(deletePreset).toHaveBeenCalledWith('preset_1')
      expect(DEFAULT_PROPS.showToast).toHaveBeenCalledWith('Preset deleted')
    })
  })

  it('cancels delete when Cancel clicked in confirmation', async () => {
    const user = userEvent.setup()
    fetchPresets.mockResolvedValue(MOCK_PRESETS)
    render(<PresetManager {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('Rogue Elf')).toBeInTheDocument()
    })

    const deleteButtons = screen.getAllByTitle('Delete this preset')
    await user.click(deleteButtons[0])

    await waitFor(() => {
      expect(screen.getByText('Delete Preset')).toBeInTheDocument()
    })

    // Click Cancel in the confirmation dialog
    await user.click(screen.getByText('Cancel'))

    // Confirmation dialog should be gone
    await waitFor(() => {
      expect(screen.queryByText('Delete Preset')).not.toBeInTheDocument()
    })

    expect(deletePreset).not.toHaveBeenCalled()
  })

  it('submits save on Enter key in name input', async () => {
    const user = userEvent.setup()
    fetchPresets.mockResolvedValue([])
    savePreset.mockResolvedValue({ preset_id: 'preset_new', name: 'Quick' })
    fetchPresets.mockResolvedValue([])

    render(<PresetManager {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('💾 Save Current')).toBeInTheDocument()
    })

    await user.click(screen.getByText('💾 Save Current'))

    const input = await screen.findByPlaceholderText('My favorite combo...')
    await user.type(input, 'Quick{Enter}')

    await waitFor(() => {
      expect(savePreset).toHaveBeenCalledWith(
        expect.objectContaining({ name: 'Quick' })
      )
    })
  })

  it('shows toast on refresh failure after save', async () => {
    const user = userEvent.setup()
    fetchPresets.mockResolvedValueOnce([]) // initial load
    savePreset.mockResolvedValue({ preset_id: 'preset_new', name: 'Test' })
    fetchPresets.mockRejectedValueOnce(new Error('Refresh failed')) // refresh after save

    render(<PresetManager {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('💾 Save Current')).toBeInTheDocument()
    })

    await user.click(screen.getByText('💾 Save Current'))

    const input = await screen.findByPlaceholderText('My favorite combo...')
    await user.type(input, 'Test')
    const dialogSaveBtn = screen.getByRole('button', { name: 'Save' })
    await user.click(dialogSaveBtn)

    await waitFor(() => {
      expect(DEFAULT_PROPS.showToast).toHaveBeenCalledWith('Failed to refresh preset list')
    })
  })
})