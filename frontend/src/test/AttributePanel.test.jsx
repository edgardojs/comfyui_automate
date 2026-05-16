/**
 * Unit tests for the AttributePanel component.
 *
 * Tests:
 * - Loading state renders skeleton
 * - Error state renders retry button
 * - Successful load renders category dropdowns
 * - Dropdown selection triggers onAttributeChange
 * - Lock toggle triggers onLockToggle
 * - Randomize/Clear buttons work
 * - Retry button re-fetches data
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AttributePanel from '../components/AttributePanel'

// Mock the API client
vi.mock('../api/client', () => ({
  fetchAttributes: vi.fn(),
}))

import { fetchAttributes } from '../api/client'

const MOCK_CATEGORIES = [
  {
    id: 'classes',
    label: 'Character Class',
    attributes: [
      { id: 'rogue', label: 'Rogue' },
      { id: 'mage', label: 'Mage' },
    ],
  },
  {
    id: 'species',
    label: 'Species',
    attributes: [
      { id: 'elf', label: 'Elf' },
      { id: 'human', label: 'Human' },
    ],
  },
]

const DEFAULT_PROPS = {
  attributes: {},
  lockedFields: [],
  onAttributeChange: vi.fn(),
  onLockToggle: vi.fn(),
  onRandomizeAll: vi.fn(),
  onClearAll: vi.fn(),
}

describe('AttributePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders loading skeleton while fetching', () => {
    fetchAttributes.mockReturnValue(new Promise(() => {})) // never resolves
    render(<AttributePanel {...DEFAULT_PROPS} />)

    expect(screen.getByText('Character Attributes')).toBeInTheDocument()
    // Skeleton elements (animate-pulse)
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('renders error state with retry button on fetch failure', async () => {
    fetchAttributes.mockRejectedValue(new Error('Network error'))
    render(<AttributePanel {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText(/Failed to load attributes/)).toBeInTheDocument()
    })
    expect(screen.getByText('Retry')).toBeInTheDocument()
  })

  it('retries fetch when retry button is clicked', async () => {
    const user = userEvent.setup()
    fetchAttributes.mockRejectedValueOnce(new Error('Network error'))
    fetchAttributes.mockResolvedValueOnce({ categories: MOCK_CATEGORIES })

    render(<AttributePanel {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('Retry')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Retry'))

    await waitFor(() => {
      const selects = document.querySelectorAll('select')
      expect(selects.length).toBe(2)
    })
  })

  it('renders category dropdowns after successful fetch', async () => {
    fetchAttributes.mockResolvedValue({ categories: MOCK_CATEGORIES })
    render(<AttributePanel {...DEFAULT_PROPS} />)

    await waitFor(() => {
      // Verify dropdowns exist by checking for select elements
      const selects = document.querySelectorAll('select')
      expect(selects.length).toBe(2)
    })
  })

  it('renders "Random" default option in each dropdown', async () => {
    fetchAttributes.mockResolvedValue({ categories: MOCK_CATEGORIES })
    render(<AttributePanel {...DEFAULT_PROPS} />)

    await waitFor(() => {
      const randomOptions = screen.getAllByText('— Random —')
      expect(randomOptions.length).toBe(2)
    })
  })

  it('renders attribute options in dropdowns', async () => {
    fetchAttributes.mockResolvedValue({ categories: MOCK_CATEGORIES })
    render(<AttributePanel {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByText('Rogue')).toBeInTheDocument()
      expect(screen.getByText('Mage')).toBeInTheDocument()
      expect(screen.getByText('Elf')).toBeInTheDocument()
      expect(screen.getByText('Human')).toBeInTheDocument()
    })
  })

  it('calls onAttributeChange when dropdown value changes', async () => {
    const user = userEvent.setup()
    fetchAttributes.mockResolvedValue({ categories: MOCK_CATEGORIES })
    render(<AttributePanel {...DEFAULT_PROPS} />)

    await waitFor(() => {
      const selects = document.querySelectorAll('select')
      expect(selects.length).toBeGreaterThan(0)
    })

    const firstSelect = document.querySelectorAll('select')[0]
    await user.selectOptions(firstSelect, 'rogue')

    expect(DEFAULT_PROPS.onAttributeChange).toHaveBeenCalledWith('classes', 'rogue')
  })

  it('calls onLockToggle when lock button is clicked', async () => {
    const user = userEvent.setup()
    fetchAttributes.mockResolvedValue({ categories: MOCK_CATEGORIES })
    render(<AttributePanel {...DEFAULT_PROPS} />)

    await waitFor(() => {
      // Find lock buttons by their emoji content
      const unlockButtons = screen.getAllByText('🔓')
      expect(unlockButtons.length).toBeGreaterThan(0)
    })

    // Click the first lock button (🔓)
    const unlockButtons = screen.getAllByText('🔓')
    await user.click(unlockButtons[0])

    expect(DEFAULT_PROPS.onLockToggle).toHaveBeenCalledWith('classes')
  })

  it('shows locked state for locked fields', async () => {
    fetchAttributes.mockResolvedValue({ categories: MOCK_CATEGORIES })
    render(<AttributePanel {...DEFAULT_PROPS} lockedFields={['classes']} />)

    await waitFor(() => {
      expect(screen.getByTitle('Unlock this attribute')).toBeInTheDocument()
    })
  })

  it('calls onRandomizeAll when Randomize button is clicked', async () => {
    const user = userEvent.setup()
    fetchAttributes.mockResolvedValue({ categories: MOCK_CATEGORIES })
    render(<AttributePanel {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByTitle('Randomize all attributes')).toBeInTheDocument()
    })

    await user.click(screen.getByTitle('Randomize all attributes'))

    expect(DEFAULT_PROPS.onRandomizeAll).toHaveBeenCalledTimes(1)
  })

  it('calls onClearAll when Clear button is clicked', async () => {
    const user = userEvent.setup()
    fetchAttributes.mockResolvedValue({ categories: MOCK_CATEGORIES })
    render(<AttributePanel {...DEFAULT_PROPS} />)

    await waitFor(() => {
      expect(screen.getByTitle('Clear all selections')).toBeInTheDocument()
    })

    await user.click(screen.getByTitle('Clear all selections'))

    expect(DEFAULT_PROPS.onClearAll).toHaveBeenCalledTimes(1)
  })

  it('renders empty state when no categories returned', async () => {
    fetchAttributes.mockResolvedValue({ categories: [] })
    render(<AttributePanel {...DEFAULT_PROPS} />)

    await waitFor(() => {
      // No dropdowns should be rendered
      expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    })
  })
})