import { describe, it, expect } from 'vitest'
import { isToolAssistant, MEDIA_TOOL_GROUPS } from './tools.js'

describe('isToolAssistant', () => {
  it('erkennt Assistenten mit image_generation als Werkzeug-Assistent', () => {
    expect(isToolAssistant({ tool_groups: ['image_generation'] })).toBe(true)
  })

  it('erkennt Assistenten mit gemischten Gruppen inkl. Bildgenerierung', () => {
    expect(isToolAssistant({ tool_groups: ['planning', 'image_generation'] })).toBe(true)
  })

  it('erkennt Planungs-/Wissens-Assistenten NICHT als Werkzeug-Assistent', () => {
    expect(isToolAssistant({ tool_groups: ['planning'] })).toBe(false)
    expect(isToolAssistant({ tool_groups: ['student_planning', 'context_search'] })).toBe(false)
  })

  it('ist robust bei fehlenden/leeren tool_groups', () => {
    expect(isToolAssistant({ tool_groups: [] })).toBe(false)
    expect(isToolAssistant({})).toBe(false)
    expect(isToolAssistant(null)).toBe(false)
    expect(isToolAssistant(undefined)).toBe(false)
  })

  it('MEDIA_TOOL_GROUPS enthält (aktuell) image_generation', () => {
    expect(MEDIA_TOOL_GROUPS).toContain('image_generation')
  })
})
