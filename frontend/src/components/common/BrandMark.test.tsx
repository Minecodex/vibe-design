import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import { BrandMark } from './BrandMark'

const currentDir = dirname(fileURLToPath(import.meta.url))

describe('BrandMark', () => {
  test('renders a square rounded brand mark', () => {
    render(<BrandMark isDark={false} />)

    const mark = screen.getByLabelText('brand-mark')
    expect(mark).toHaveClass('rounded-lg')
    expect(mark).toHaveClass('bg-black')
    expect(mark).toHaveClass('text-white')
  })

  test('is reused by main layout and canvas top bar', () => {
    const mainLayoutSource = readFileSync(resolve(currentDir, 'MainLayout/index.tsx'), 'utf8')
    const canvasTopBarSource = readFileSync(
      resolve(currentDir, '../../pages/dashboard/CanvasPage/components/CanvasTopBar.tsx'),
      'utf8',
    )

    expect(mainLayoutSource).toContain('<BrandMark')
    expect(canvasTopBarSource).toContain('<BrandMark')
  })
})
