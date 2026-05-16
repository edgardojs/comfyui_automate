/**
 * Unit tests for the PromptHistory component.
 *
 * Tests:
 * - Loading state
 * - Error state with retry
 * - Empty state
 * - History item rendering
 * - Expand/collapse entries
 * - Favorite toggle
 * - Copy buttons
 * - Load More pagination
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import PromptHistory from '../components/PromptHistory'

vi.mock('../api/client', () => ({
  fetchHistory: vi.fn(),
  favoriteHistoryItem: vi.fn(),
}))

import { fetchHistory, favoriteHistoryItem } from '../api/client'

const MOCK_HISTORY = {
  items: [
    {
      id: 1,
      generation_id: 'gen_abc',
      positive_prompt: 'front view sprite of a rogue elf with leather armor',
      negative_prompt: 'blurry, low quality, deformed',
      attributes: { classes: 'rogue', species: 'elf' },
      template_id: 'front_view_sprite',
      negative_profile_id: 'general_sprite_cleanup',
      is_favorite: false,
      created_at: '2026-05-15T10:30:00',
    },
    {
      id: 2,
      generation_id: 'gen_def',
      positive_prompt: 'side view sprite of a mage human with robes',
      negative_prompt: 'blurry, low quality',
      attributes: { classes: 'mage', species: 'human' },
      template_id: 'side_view_sprite',
      negative_profile_id: 'dark_fantasy',
      is_favorite: true,
      created_at: '2026-05-15T09:00:00',
    },
  ],
  total: 2,
}

const DEFAULT_PROPS = {
  onCopy: vi.fn(),
  showToast: vi.fn(),
}

describe('PromptHistory', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders loading skeleton while fetching', () => {
    fetchHistory.mockReturnValue(new Promise(() => {}))
    render(<PromptHistory {...DEFAULT_PROPS} />)

    expect(screen.getByText('Prompt History')).toBeInTheDocument()
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('renders error state with retry on fetch failure', async () => {
    fetchHistory.mockRejectedValue(new Error('Network error'))
    render(<PromptHistory {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText(/Failed to load history/)).toBeInTheDocument()
      expect(screen.getByText('Retry')).toBeInTheDocument()
    })
  })

  it('renders empty state when no history', async () => {
    fetchHistory.mockResolvedValue({ items: [], total: 0 })
    render(<PromptHistory {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('No history yet')).toBeInTheDocument()
    })
  })

  it('renders history items with prompt previews', async () => {
    fetchHistory.mockResolvedValue(MOCK_HISTORY)
    render(<PromptHistory {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText(/front view sprite of a rogue/)).toBeInTheDocument()
      expect(screen.getByText(/side view sprite of a mage/)).toBeInTheDocument()
    })
  })

  it('shows total entry count', async () => {
    fetchHistory.mockResolvedValue(MOCK_HISTORY)
    render(<PromptHistory {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('2 entries')).toBeInTheDocument()
    })
  })

  it('shows singular "1 entry" for single item', async () => {
    fetchHistory.mockResolvedValue({ items: [MOCK_HISTORY.items[0]], total: 1 })
    render(<PromptHistory {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('1 entry')).toBeInTheDocument()
    })
  })

  it('shows favorite star for favorited items', async () => {
    fetchHistory.mockResolvedValue(MOCK_HISTORY)
    render(<PromptHistory {...DEFAULT_PROPS} />)

    await waitFor(() => {
      // The favorited item (gen_def) should show ⭐
      expect(screen.getByTitle('Remove from favorites')).toBeInTheDocument()
      // The non-favorited item (gen_abc) should show ☆
      expect(screen.getByTitle('Add to favorites')).toBeInTheDocument()
    })
  })

  it('calls favoriteHistoryItem when star clicked', async () => {
    const user = userEvent.setup()
    fetchHistory.mockResolvedValue(MOCK_HISTORY)
    favoriteHistoryItem.mockResolvedValue({ generation_id: 'gen_abc', is_favorite: true })

    render(<PromptHistory {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByTitle('Add to favorites')).toBeInTheDocument()
    })

    await user.click(screen.getByTitle('Add to favorites'))

    expect(favoriteHistoryItem).toHaveBeenCalledWith('gen_abc')
  })

  it('shows toast on favorite toggle', async () => {
    const user = userEvent.setup()
    fetchHistory.mockResolvedValue(MOCK_HISTORY)
    favoriteHistoryItem.mockResolvedValue({ generation_id: 'gen_abc', is_favorite: true })

    render(<PromptHistory {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByTitle('Add to favorites')).toBeInTheDocument()
    })

    await user.click(screen.getByTitle('Add to favorites'))

    await waitFor(() => {
      expect(DEFAULT_PROPS.showToast).toHaveBeenCalledWith('⭐ Added to favorites')
    })
  })

  it('shows toast on favorite toggle failure', async () => {
    const user = userEvent.setup()
    fetchHistory.mockResolvedValue(MOCK_HISTORY)
    favoriteHistoryItem.mockRejectedValue(new Error('Server error'))

    render(<PromptHistory {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByTitle('Add to favorites')).toBeInTheDocument()
    })

    await user.click(screen.getByTitle('Add to favorites'))

    await waitFor(() => {
      expect(DEFAULT_PROPS.showToast).toHaveBeenCalledWith('Failed to toggle favorite: Server error')
    })
  })

  it('expands entry to show full prompts on click', async () => {
    const user = userEvent.setup()
    fetchHistory.mockResolvedValue(MOCK_HISTORY)
    render(<PromptHistory {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText(/front view sprite of a rogue/)).toBeInTheDocument()
    })

    // Click on the first history item summary row
    const previewText = screen.getByText(/front view sprite of a rogue/)
    await user.click(previewText)

    await waitFor(() => {
      // Expanded view should show full positive prompt
      expect(screen.getByText('Positive Prompt')).toBeInTheDocument()
      expect(screen.getByText('Negative Prompt')).toBeInTheDocument()
    })
  })

  it('shows copy buttons in expanded view', async () => {
    const user = userEvent.setup()
    fetchHistory.mockResolvedValue(MOCK_HISTORY)
    render(<PromptHistory {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText(/front view sprite of a rogue/)).toBeInTheDocument()
    })

    // Expand the first entry by clicking the summary row
    const summaryRows = document.querySelectorAll('[class*="cursor-pointer"]')
    // Find the div that contains the prompt preview text
    const previewEl = screen.getByText(/front view sprite of a rogue/)
    await user.click(previewEl.closest('[class*="cursor-pointer"]') || previewEl)

    await waitFor(() => {
      expect(screen.getByText('📋 Copy Positive')).toBeInTheDocument()
      expect(screen.getByText('📋 Copy Negative')).toBeInTheDocument()
      expect(screen.getByText('📋 Copy Both')).toBeInTheDocument()
    })
  })

  it('calls onCopy when copy button clicked in expanded view', async () => {
    const user = userEvent.setup()
    fetchHistory.mockResolvedValue(MOCK_HISTORY)
    render(<PromptHistory {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText(/front view sprite of a rogue/)).toBeInTheDocument()
    })

    // Expand the first entry
    const previewEl = screen.getByText(/front view sprite of a rogue/)
    await user.click(previewEl.closest('[class*="cursor-pointer"]') || previewEl)

    await waitFor(() => {
      expect(screen.getByText('📋 Copy Positive')).toBeInTheDocument()
    })

    await user.click(screen.getByText('📋 Copy Positive'))

    expect(DEFAULT_PROPS.onCopy).toHaveBeenCalledWith(
      MOCK_HISTORY.items[0].positive_prompt,
      'Positive'
    )
  })

  it('shows attribute badges in summary row', async () => {
    fetchHistory.mockResolvedValue(MOCK_HISTORY)
    render(<PromptHistory {...DEFAULT_PROPS} />)

    await waitFor(() => {
      // Attribute badges for classes
      expect(screen.getByText('rogue')).toBeInTheDocument()
      expect(screen.getByText('mage')).toBeInTheDocument()
    })
  })

  it('shows Load More button when more items exist', async () => {
    fetchHistory.mockResolvedValue({
      items: MOCK_HISTORY.items,
      total: 25, // More than the 2 items returned
    })
    render(<PromptHistory {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText(/Load More/)).toBeInTheDocument()
    })
  })

  it('does not show Load More when all items loaded', async () => {
    fetchHistory.mockResolvedValue(MOCK_HISTORY) // total=2, items.length=2
    render(<PromptHistory {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('2 entries')).toBeInTheDocument()
    })

    expect(screen.queryByText(/Load More/)).not.toBeInTheDocument()
  })

  it('loads more items when Load More clicked', async () => {
    const user = userEvent.setup()
    const moreItems = [
      {
        id: 3,
        generation_id: 'gen_ghi',
        positive_prompt: 'pixel art sprite of a warrior dwarf',
        negative_prompt: 'blurry',
        attributes: { classes: 'warrior', species: 'dwarf' },
        template_id: 'pixel_art_sprite',
        negative_profile_id: 'general_sprite_cleanup',
        is_favorite: false,
        created_at: '2026-05-15T08:00:00',
      },
    ]

    fetchHistory.mockResolvedValueOnce({
      items: MOCK_HISTORY.items,
      total: 3,
    })
    fetchHistory.mockResolvedValueOnce({
      items: moreItems,
      total: 3,
    })

    render(<PromptHistory {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText(/Load More/)).toBeInTheDocument()
    })

    await user.click(screen.getByText(/Load More/))

    await waitFor(() => {
      expect(screen.getByText(/pixel art sprite of a warrior/)).toBeInTheDocument()
    })

    // fetchHistory should have been called with offset
    expect(fetchHistory).toHaveBeenCalledWith({ limit: 20, offset: 2 })
  })

  it('retries fetch when retry button clicked', async () => {
    const user = userEvent.setup()
    fetchHistory.mockRejectedValueOnce(new Error('Network error'))
    fetchHistory.mockResolvedValueOnce(MOCK_HISTORY)

    render(<PromptHistory {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('Retry')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Retry'))

    await waitFor(() => {
      expect(screen.getByText(/front view sprite of a rogue/)).toBeInTheDocument()
    })
  })

  it('shows generation ID in expanded view', async () => {
    const user = userEvent.setup()
    fetchHistory.mockResolvedValue(MOCK_HISTORY)
    render(<PromptHistory {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText(/front view sprite of a rogue/)).toBeInTheDocument()
    })

    // Expand the first entry
    const previewText = screen.getByText(/front view sprite of a rogue/)
    await user.click(previewText)

    await waitFor(() => {
      expect(screen.getByText(/ID: gen_abc/)).toBeInTheDocument()
    })
  })
})