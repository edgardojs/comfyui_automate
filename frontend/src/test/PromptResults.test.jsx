/**
 * Unit tests for the PromptResults component.
 *
 * Tests:
 * - Empty state
 * - Loading state
 * - Error state
 * - Result rendering with copy buttons
 * - Expandable resolved attributes
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import PromptResults from '../components/PromptResults'

const MOCK_RESULTS = {
  generation_id: 'gen_abc123',
  items: [
    {
      positive_prompt: 'front view sprite of a rogue elf, leather armor, forest background',
      negative_prompt: 'blurry, low quality, deformed',
      attributes: {
        classes: 'rogue',
        species: 'elf',
        weapons: 'dagger',
      },
    },
    {
      positive_prompt: 'front view sprite of a warrior human, plate armor, castle background',
      negative_prompt: 'blurry, low quality, deformed',
      attributes: {
        classes: 'warrior',
        species: 'human',
        weapons: 'sword',
      },
    },
  ],
}

const DEFAULT_PROPS = {
  results: null,
  error: null,
  isGenerating: false,
  onCopy: vi.fn(),
}

describe('PromptResults', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders empty state when no results', () => {
    render(<PromptResults {...DEFAULT_PROPS} />)

    expect(screen.getByText('No prompts yet')).toBeInTheDocument()
    expect(screen.getByText(/Select attributes and click Generate/)).toBeInTheDocument()
  })

  it('renders loading state when generating', () => {
    render(<PromptResults {...DEFAULT_PROPS} isGenerating={true} />)

    expect(screen.getByText('Generating prompts…')).toBeInTheDocument()
  })

  it('renders error state', () => {
    render(<PromptResults {...DEFAULT_PROPS} error="Something went wrong" />)

    expect(screen.getByText(/Something went wrong/)).toBeInTheDocument()
  })

  it('renders variation cards with prompts', () => {
    render(<PromptResults {...DEFAULT_PROPS} results={MOCK_RESULTS} />)

    // "2 variations" is split across elements inside a span
    expect(screen.getByText(/2 variations/)).toBeInTheDocument()
    expect(screen.getByText(/front view sprite of a rogue/)).toBeInTheDocument()
    expect(screen.getByText(/front view sprite of a warrior/)).toBeInTheDocument()
  })

  it('renders copy buttons for each variation', () => {
    render(<PromptResults {...DEFAULT_PROPS} results={MOCK_RESULTS} />)

    // Copy buttons use "📋 Positive" / "📋 Negative" / "📋 Both"
    const positiveButtons = screen.getAllByText(/📋 Positive/)
    expect(positiveButtons.length).toBe(2)
    const negativeButtons = screen.getAllByText(/📋 Negative/)
    expect(negativeButtons.length).toBe(2)
    const bothButtons = screen.getAllByText(/📋 Both/)
    expect(bothButtons.length).toBe(2)
  })

  it('calls onCopy when Copy Positive button clicked', async () => {
    const user = userEvent.setup()
    render(<PromptResults {...DEFAULT_PROPS} results={MOCK_RESULTS} />)

    const copyButtons = screen.getAllByText(/📋 Positive/)
    await user.click(copyButtons[0])

    expect(DEFAULT_PROPS.onCopy).toHaveBeenCalledWith(
      MOCK_RESULTS.items[0].positive_prompt,
      'Positive'
    )
  })

  it('calls onCopy when Copy Negative button clicked', async () => {
    const user = userEvent.setup()
    render(<PromptResults {...DEFAULT_PROPS} results={MOCK_RESULTS} />)

    const copyButtons = screen.getAllByText(/📋 Negative/)
    await user.click(copyButtons[0])

    expect(DEFAULT_PROPS.onCopy).toHaveBeenCalledWith(
      MOCK_RESULTS.items[0].negative_prompt,
      'Negative'
    )
  })

  it('calls onCopy when Copy Both button clicked', async () => {
    const user = userEvent.setup()
    render(<PromptResults {...DEFAULT_PROPS} results={MOCK_RESULTS} />)

    const copyBothButtons = screen.getAllByText(/📋 Both/)
    await user.click(copyBothButtons[0])

    const expectedText = `Positive: ${MOCK_RESULTS.items[0].positive_prompt}\n\nNegative: ${MOCK_RESULTS.items[0].negative_prompt}`
    expect(DEFAULT_PROPS.onCopy).toHaveBeenCalledWith(expectedText, 'Both')
  })

  it('shows resolved attributes when expanded', async () => {
    const user = userEvent.setup()
    render(<PromptResults {...DEFAULT_PROPS} results={MOCK_RESULTS} />)

    // Click the <summary> element to expand attributes
    const summary = screen.getAllByText('▶ Resolved Attributes')[0]
    await user.click(summary)

    await waitFor(() => {
      // Attribute values should now be visible in the expanded details
      const attrValues = screen.getAllByText('rogue')
      expect(attrValues.length).toBeGreaterThan(0)
      const elfValues = screen.getAllByText('elf')
      expect(elfValues.length).toBeGreaterThan(0)
    })
  })

  it('displays generation ID', () => {
    render(<PromptResults {...DEFAULT_PROPS} results={MOCK_RESULTS} />)

    expect(screen.getByText(/gen_abc123/)).toBeInTheDocument()
  })

  it('renders singular "1 variation" for single result', () => {
    const singleResult = {
      generation_id: 'gen_single',
      items: [MOCK_RESULTS.items[0]],
    }
    render(<PromptResults {...DEFAULT_PROPS} results={singleResult} />)

    expect(screen.getByText(/1 variation/)).toBeInTheDocument()
  })
})