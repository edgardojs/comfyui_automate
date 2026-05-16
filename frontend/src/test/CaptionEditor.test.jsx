/**
 * Unit tests for the CaptionEditor component.
 *
 * Tests:
 * - Loading state
 * - Error state
 * - Empty state (no accepted images)
 * - Image grid rendering with captions
 * - Missing caption indicator
 * - Auto-generate captions button
 * - Inline caption editing (click to edit, save, cancel)
 * - Caption style selector
 * - Stats display
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import CaptionEditor from '../components/CaptionEditor'

vi.mock('../api/client', () => ({
  fetchReferences: vi.fn(),
  generateCaptions: vi.fn(),
  updateCaption: vi.fn(),
  getReferenceFileUrl: vi.fn((characterId, imageId) =>
    `/api/characters/${characterId}/references/${imageId}/file`
  ),
}))

import { fetchReferences, generateCaptions, updateCaption } from '../api/client'

const MOCK_REFERENCES = [
  {
    image_id: 'img_001',
    character_id: 'char_1',
    original_filename: 'front_view.png',
    status: 'accepted',
    angle: 'front',
    caption: 'dwarf_rogue_v1, dwarf rogue, shortbow, front view, full body, pixel art sprite style',
    file_path: '/sprite_projects/Project/Character/references/front_view.png',
    created_at: '2026-05-16T10:00:00',
  },
  {
    image_id: 'img_002',
    character_id: 'char_1',
    original_filename: 'side_view.png',
    status: 'accepted',
    angle: 'side',
    caption: null,
    file_path: '/sprite_projects/Project/Character/references/side_view.png',
    created_at: '2026-05-16T10:01:00',
  },
  {
    image_id: 'img_003',
    character_id: 'char_1',
    original_filename: 'back_view.png',
    status: 'accepted',
    angle: 'back',
    caption: '',
    file_path: '/sprite_projects/Project/Character/references/back_view.png',
    created_at: '2026-05-16T10:02:00',
  },
]

const DEFAULT_PROPS = {
  characterId: 'char_1',
  showToast: vi.fn(),
}

describe('CaptionEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // --- Loading state ---
  it('renders loading state while fetching references', () => {
    fetchReferences.mockReturnValue(new Promise(() => {}))
    render(<CaptionEditor {...DEFAULT_PROPS} />)

    expect(screen.getByText('Loading images...')).toBeInTheDocument()
  })

  // --- Error state ---
  it('renders error message on fetch failure', async () => {
    fetchReferences.mockRejectedValue(new Error('Server error'))
    render(<CaptionEditor {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText(/Error: Server error/)).toBeInTheDocument()
    })
  })

  // --- Empty state ---
  it('renders empty state when no accepted images', async () => {
    fetchReferences.mockResolvedValue([])
    render(<CaptionEditor {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText(/No accepted reference images/)).toBeInTheDocument()
    })
  })

  // --- Image grid rendering ---
  it('renders image grid with accepted references', async () => {
    fetchReferences.mockResolvedValue(MOCK_REFERENCES)
    render(<CaptionEditor {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('front_view.png')).toBeInTheDocument()
      expect(screen.getByText('side_view.png')).toBeInTheDocument()
      expect(screen.getByText('back_view.png')).toBeInTheDocument()
    })
  })

  // --- Angle tags ---
  it('displays angle tags for images with angles', async () => {
    fetchReferences.mockResolvedValue(MOCK_REFERENCES)
    render(<CaptionEditor {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('front')).toBeInTheDocument()
      expect(screen.getByText('side')).toBeInTheDocument()
      expect(screen.getByText('back')).toBeInTheDocument()
    })
  })

  // --- Caption display ---
  it('displays existing captions for images', async () => {
    fetchReferences.mockResolvedValue(MOCK_REFERENCES)
    render(<CaptionEditor {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText(/dwarf_rogue_v1, dwarf rogue/)).toBeInTheDocument()
    })
  })

  // --- Missing caption indicator ---
  it('shows "No caption" badge for images without captions', async () => {
    fetchReferences.mockResolvedValue(MOCK_REFERENCES)
    render(<CaptionEditor {...DEFAULT_PROPS} />)

    await waitFor(() => {
      const noCaptionBadges = screen.getAllByText('No caption')
      // img_002 has null caption, img_003 has empty string caption
      expect(noCaptionBadges.length).toBe(2)
    })
  })

  // --- Stats display ---
  it('shows caption stats', async () => {
    fetchReferences.mockResolvedValue(MOCK_REFERENCES)
    render(<CaptionEditor {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText(/1 with caption/)).toBeInTheDocument()
      expect(screen.getByText(/2 missing caption/)).toBeInTheDocument()
    })
  })

  // --- Caption style selector ---
  it('renders caption style selector with detailed and simple options', async () => {
    fetchReferences.mockResolvedValue(MOCK_REFERENCES)
    render(<CaptionEditor {...DEFAULT_PROPS} />)

    await waitFor(() => {
      const select = screen.getByDisplayValue('Detailed')
      expect(select).toBeInTheDocument()
    })
  })

  // --- Auto-generate captions ---
  it('calls generateCaptions with selected style on button click', async () => {
    const user = userEvent.setup()
    const mockResult = {
      character_id: 'char_1',
      captions: [
        { image_id: 'img_001', caption: 'new caption 1' },
        { image_id: 'img_002', caption: 'new caption 2' },
        { image_id: 'img_003', caption: 'new caption 3' },
      ],
      count: 3,
    }
    fetchReferences.mockResolvedValue(MOCK_REFERENCES)
    generateCaptions.mockResolvedValue(mockResult)
    render(<CaptionEditor {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('✨ Generate All Captions')).toBeInTheDocument()
    })

    await user.click(screen.getByText('✨ Generate All Captions'))

    expect(generateCaptions).toHaveBeenCalledWith('char_1', 'detailed')
    expect(DEFAULT_PROPS.showToast).toHaveBeenCalledWith('✨ Generated 3 caption(s)')
  })

  it('shows error toast when generateCaptions fails', async () => {
    const user = userEvent.setup()
    fetchReferences.mockResolvedValue(MOCK_REFERENCES)
    generateCaptions.mockRejectedValue(new Error('No accepted images'))
    render(<CaptionEditor {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('✨ Generate All Captions')).toBeInTheDocument()
    })

    await user.click(screen.getByText('✨ Generate All Captions'))

    expect(DEFAULT_PROPS.showToast).toHaveBeenCalledWith(
      '❌ Caption generation failed: No accepted images'
    )
  })

  // --- Inline caption editing ---
  it('enters edit mode when clicking on a caption', async () => {
    const user = userEvent.setup()
    fetchReferences.mockResolvedValue(MOCK_REFERENCES)
    render(<CaptionEditor {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText(/dwarf_rogue_v1/)).toBeInTheDocument()
    })

    // Click on the caption text to enter edit mode
    await user.click(screen.getByText(/dwarf_rogue_v1/))

    // Should show textarea and save/cancel buttons
    expect(screen.getByRole('textbox')).toBeInTheDocument()
    expect(screen.getByText('Save')).toBeInTheDocument()
    expect(screen.getByText('Cancel')).toBeInTheDocument()
  })

  it('saves edited caption on Save button click', async () => {
    const user = userEvent.setup()
    const updatedRef = { ...MOCK_REFERENCES[0], caption: 'updated caption text' }
    fetchReferences.mockResolvedValue(MOCK_REFERENCES)
    updateCaption.mockResolvedValue(updatedRef)
    render(<CaptionEditor {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText(/dwarf_rogue_v1/)).toBeInTheDocument()
    })

    // Click on the caption to enter edit mode
    await user.click(screen.getByText(/dwarf_rogue_v1/))

    // Clear and type new caption
    const textarea = screen.getByRole('textbox')
    await user.clear(textarea)
    await user.type(textarea, 'updated caption text')

    // Click Save
    await user.click(screen.getByText('Save'))

    expect(updateCaption).toHaveBeenCalledWith('char_1', 'img_001', 'updated caption text')
    expect(DEFAULT_PROPS.showToast).toHaveBeenCalledWith('Caption updated')
  })

  it('cancels editing on Cancel button click', async () => {
    const user = userEvent.setup()
    fetchReferences.mockResolvedValue(MOCK_REFERENCES)
    render(<CaptionEditor {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText(/dwarf_rogue_v1/)).toBeInTheDocument()
    })

    // Click on the caption to enter edit mode
    await user.click(screen.getByText(/dwarf_rogue_v1/))

    // Should show textarea
    expect(screen.getByRole('textbox')).toBeInTheDocument()

    // Click Cancel
    await user.click(screen.getByText('Cancel'))

    // Textarea should be gone
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  // --- "Click to add a caption" for empty captions ---
  it('shows "Click to add a caption" for images without captions', async () => {
    fetchReferences.mockResolvedValue(MOCK_REFERENCES)
    render(<CaptionEditor {...DEFAULT_PROPS} />)

    await waitFor(() => {
      const addCaptionLinks = screen.getAllByText('Click to add a caption...')
      expect(addCaptionLinks.length).toBe(2) // img_002 and img_003
    })
  })

  // --- Generate button disabled when no images ---
  it('disables generate button when no references', async () => {
    fetchReferences.mockResolvedValue([])
    render(<CaptionEditor {...DEFAULT_PROPS} />)

    await waitFor(() => {
      const btn = screen.getByText('✨ Generate All Captions')
      expect(btn).toBeDisabled()
    })
  })
})