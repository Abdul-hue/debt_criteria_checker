import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import SummaryStats from '../../components/assess/SummaryStats'
import { vi } from 'vitest'

describe('SummaryStats', () => {
  const mockResult = {
    hard_blocks: [{ id: 1 }],
    flags: [{ id: 1 }, { id: 2 }],
    info: [{ id: 1 }, { id: 2 }, { id: 3 }],
    passed: Array(10).fill({ id: 1 })
  }

  const mockRefs = {
    hardBlocks: { current: { scrollIntoView: vi.fn() } },
    flags: { current: { scrollIntoView: vi.fn() } },
    info: { current: { scrollIntoView: vi.fn() } },
    passed: { current: { scrollIntoView: vi.fn() } }
  }

  it('renders four stat cards with correct counts', () => {
    render(<SummaryStats result={mockResult} sectionRefs={mockRefs} />)
    expect(screen.getByText('1')).toBeInTheDocument() // Hard Blocks
    expect(screen.getByText('2')).toBeInTheDocument() // Flags
    expect(screen.getByText('3')).toBeInTheDocument() // Info
    expect(screen.getByText('10')).toBeInTheDocument() // Passed
    
    expect(screen.getByText(/hard blocks/i)).toBeInTheDocument()
    expect(screen.getByText(/flags/i)).toBeInTheDocument()
    expect(screen.getByText(/info/i)).toBeInTheDocument()
    expect(screen.getByText(/passed/i)).toBeInTheDocument()
  })

  it('clicking a card calls the scroll handler', () => {
    render(<SummaryStats result={mockResult} sectionRefs={mockRefs} />)
    
    const hardBlocksCard = screen.getByRole('button', { name: /1 hard blocks/i })
    fireEvent.click(hardBlocksCard)
    
    expect(mockRefs.hardBlocks.current.scrollIntoView).toHaveBeenCalledWith({
      behavior: 'smooth',
      block: 'start'
    })
  })
})
