// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest'
import { einstellen, feldEinrichten, tottasteAbfangen } from './formel_editor.js'

describe('einstellen — MathLive ohne Netz', () => {
    it('lädt keine Schriften und Klänge nach, setzt das deutsche Komma', () => {
        const M = { fontsDirectory: './fonts/', soundsDirectory: './sounds', keypressSound: 'x', plonkSound: 'y' }
        einstellen(M)
        expect(M).toMatchObject({
            fontsDirectory: null, soundsDirectory: null, keypressSound: null, plonkSound: null,
            decimalSeparator: ',', locale: 'de',
        })
    })
})

/** Ein Element mit Shadow-Root wie `<math-field>`, darin die Tastatur-Senke; das Feld ist eine Attrappe. */
function aufbau() {
    const wirt = document.createElement('div')
    const wurzel = wirt.attachShadow({ mode: 'open' })
    const senke = document.createElement('span')
    wurzel.append(senke)
    document.body.append(wirt)
    const mathlive = vi.fn() // was MathLive selbst an der Senke sieht
    for (const t of ['keydown', 'compositionend']) senke.addEventListener(t, (e) => mathlive(t, e.key ?? e.data), true)
    const feld = { executeCommand: vi.fn(), shadowRoot: wurzel }
    return { wurzel, senke, mathlive, feld }
}

describe('tottasteAbfangen — ^ auf deutscher Tastatur in Chrome', () => {
    it('lässt keydown key="Dead" nicht zu MathLive durch, andere Tasten schon', () => {
        const { wurzel, senke, mathlive, feld } = aufbau()
        tottasteAbfangen(wurzel, feld)
        senke.dispatchEvent(new KeyboardEvent('keydown', { key: 'Dead', code: 'IntlBackslash', bubbles: true, composed: true }))
        senke.dispatchEvent(new KeyboardEvent('keydown', { key: '2', code: 'Digit2', bubbles: true, composed: true }))
        expect(mathlive.mock.calls).toEqual([['keydown', '2']])
    })

    it('zerlegt "^2" aus compositionend in einzelne Zeichen', () => {
        const { wurzel, senke, mathlive, feld } = aufbau()
        tottasteAbfangen(wurzel, feld)
        senke.dispatchEvent(new CompositionEvent('compositionend', { data: '^(', bubbles: true, composed: true }))
        // MathLive bekommt nur das leere Rücksetz-Ereignis …
        expect(mathlive.mock.calls).toEqual([['compositionend', '']])
        // … und die Zeichen einzeln
        expect(feld.executeCommand.mock.calls).toEqual([
            [['typedText', '^', { simulateKeystroke: true }]],
            [['typedText', '(', { simulateKeystroke: true }]],
        ])
    })

    it('lässt ein einzelnes Zeichen (Safari, ^ mit Leertaste) unverändert durch', () => {
        const { wurzel, senke, mathlive, feld } = aufbau()
        tottasteAbfangen(wurzel, feld)
        senke.dispatchEvent(new CompositionEvent('compositionend', { data: '^', bubbles: true, composed: true }))
        expect(mathlive.mock.calls).toEqual([['compositionend', '^']])
        expect(feld.executeCommand).not.toHaveBeenCalled()
    })
})

describe('feldEinrichten', () => {
    it('nimmt Escape aus den Tasten und kürzt das Menü', () => {
        const { feld } = aufbau()
        feld.keybindings = [{ key: '[Escape]', command: 'x' }, { key: '/', command: 'y' }]
        feld.menuItems = [{ id: 'copy' }, { id: 'color' }, { type: 'divider' }, { id: 'paste' }]
        feldEinrichten(feld)
        expect(feld.keybindings).toEqual([{ key: '/', command: 'y' }])
        expect(feld.menuItems.map((m) => m.id)).toEqual(['copy', 'paste'])
    })
})
