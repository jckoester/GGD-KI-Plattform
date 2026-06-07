import { describe, it, expect } from 'vitest'
import { parseMaterial, serializeMaterial, extractNodeTargets } from './material.js'

const NODE_A = '44444444-4444-4444-4444-444444444444'
const NODE_B = '55555555-5555-5555-5555-555555555555'

const TEXT = `Siehe @[Arbeitsblatt](node:${NODE_A}) und @[Video](node:${NODE_B}) sowie https://x.de`

describe('parseMaterial', () => {
    it('leerer Text → []', () => {
        expect(parseMaterial('')).toEqual([])
    })

    it('zerlegt node-Tokens und Freitext', () => {
        const parts = parseMaterial(TEXT)
        expect(parts.map((p) => p.kind)).toEqual([
            'text', 'node', 'text', 'node', 'text',
        ])
        const nodes = parts.filter((p) => p.kind === 'node')
        expect(nodes[0]).toMatchObject({ label: 'Arbeitsblatt', node_id: NODE_A })
        expect(nodes[1]).toMatchObject({ label: 'Video', node_id: NODE_B })
        // URL bleibt im Freitext-Part (wird erst beim Rendern verlinkt)
        expect(parts.at(-1).label).toContain('https://x.de')
    })
})

describe('serializeMaterial (Round-Trip)', () => {
    it('parse → serialize ist verlustfrei', () => {
        expect(serializeMaterial(parseMaterial(TEXT))).toBe(TEXT)
    })
})

describe('extractNodeTargets', () => {
    it('liefert alle node-UUIDs', () => {
        expect(extractNodeTargets(TEXT)).toEqual([NODE_A, NODE_B])
    })
    it('leerer Text → []', () => {
        expect(extractNodeTargets('')).toEqual([])
    })
})
