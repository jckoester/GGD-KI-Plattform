// @vitest-environment jsdom
// `fuelleAbbildungen` schreibt ins DOM und sanitisiert über DOMPurify — beides
// braucht ein Dokument.
import { describe, it, expect } from 'vitest'
import { renderMarkdown } from './markdown.js'
import {
  ANZEIGE_FAKTOR,
  dateiname,
  eingebettet,
  fuelleAbbildungen,
  intrinsischeBreite,
  ohneEinbettung,
} from './abbildungen.js'

const SVG = '<svg xmlns="http://www.w3.org/2000/svg"><circle cx="5" cy="5" r="4"/></svg>'

const WASSER = {
  datei: '_Abb/EN_H2O.svg',
  beschreibung: 'Wassermolekül mit Partialladungen',
  svg: SVG,
}

function wurzelMit(html) {
  const el = document.createElement('div')
  el.innerHTML = html
  return el
}

describe('renderMarkdown: {{abbildung:…}}', () => {
  it('erzeugt eine leere Hülle mit dem Dateinamen', () => {
    const html = renderMarkdown('Davor\n\n{{abbildung:EN_H2O.svg}}\n\nDanach')
    expect(html).toContain('class="abbildung-block"')
    expect(html).toContain('data-datei="EN_H2O.svg"')
  })

  it('nimmt nur den Dateinamen, nicht den Pfad', () => {
    // Dieselbe Regel wie im Backend: Im Vault steht im Text die bare Form, im
    // Frontmatter eine Pfadangabe. Beide müssen zusammenfinden.
    const html = renderMarkdown('{{abbildung:_Abb/EN_H2O.svg}}')
    expect(html).toContain('data-datei="EN_H2O.svg"')
  })

  it('setzt kein SVG ein — das kennt nur die Seite', () => {
    expect(renderMarkdown('{{abbildung:x.svg}}')).not.toContain('<svg')
  })

  it('lässt gewöhnliche geschweifte Klammern in Ruhe', () => {
    const html = renderMarkdown('Die Menge {1, 2} und {{nicht: eine Abbildung}}')
    expect(html).not.toContain('abbildung-block')
  })
})

describe('eingebettet / ohneEinbettung', () => {
  it('findet die Platzhalter im Text', () => {
    const namen = eingebettet('a {{abbildung:_Abb/x.svg}} b {{abbildung:y.svg}}')
    expect([...namen].sort()).toEqual(['x.svg', 'y.svg'])
  })

  it('liefert die Abbildungen, die im Text nicht vorkommen', () => {
    const rest = ohneEinbettung('Text mit {{abbildung:EN_H2O.svg}}', [
      WASSER,
      { datei: '_Abb/andere.svg', beschreibung: 'kommt im Text nicht vor', svg: SVG },
    ])
    expect(rest.map((a) => a.datei)).toEqual(['_Abb/andere.svg'])
  })

  it('zählt eine Abbildung als eingebettet, auch wenn der Pfad abweicht', () => {
    // Im Text steht die bare Form, im Frontmatter der Pfad — sonst stünde dieselbe
    // Abbildung zweimal auf der Seite: einmal im Fließtext, einmal am Ende.
    expect(ohneEinbettung('{{abbildung:EN_H2O.svg}}', [WASSER])).toEqual([])
  })

  it('kommt ohne Illustrationen aus', () => {
    expect(ohneEinbettung('Text', null)).toEqual([])
  })

  it('dateiname zieht den Pfad ab', () => {
    expect(dateiname('_Abb/EN_H2O.svg')).toBe('EN_H2O.svg')
    expect(dateiname('EN_H2O.svg')).toBe('EN_H2O.svg')
    expect(dateiname(undefined)).toBe('')
  })
})

describe('fuelleAbbildungen', () => {
  it('setzt das SVG in die Hülle', () => {
    const wurzel = wurzelMit(renderMarkdown('{{abbildung:EN_H2O.svg}}'))
    fuelleAbbildungen(wurzel, [WASSER])
    expect(wurzel.querySelector('.abbildung-bild svg')).not.toBeNull()
  })

  it('findet das SVG über den Dateinamen, nicht über den Pfad', () => {
    const wurzel = wurzelMit('<span class="abbildung-block" data-datei="EN_H2O.svg"></span>')
    fuelleAbbildungen(wurzel, [WASSER])
    expect(wurzel.querySelector('svg')).not.toBeNull()
  })

  it('zeigt die Beschreibung genau einmal — sichtbar und als Bildbeschreibung', () => {
    // ⚠️ Beides gleichzeitig vorzulesen wäre die naheliegende Lösung und die falsche:
    // Ein Screenreader läse denselben Satz zweimal.
    const wurzel = wurzelMit('<span class="abbildung-block" data-datei="EN_H2O.svg"></span>')
    fuelleAbbildungen(wurzel, [WASSER])
    const bild = wurzel.querySelector('.abbildung-bild')
    const text = wurzel.querySelector('.abbildung-text')
    expect(bild.getAttribute('aria-label')).toBe(WASSER.beschreibung)
    expect(text.textContent).toBe(WASSER.beschreibung)
    expect(text.getAttribute('aria-hidden')).toBe('true')
  })

  it('sanitisiert: <script> und Event-Handler fallen weg, die Zeichnung bleibt', () => {
    // ⚠️ Die Quelle ist der Vault einer Lehrkraft — vertrauenswürdig, aber ungeprüft.
    // Eine aus dem Netz übernommene Strukturformel kann beides tragen, und niemand
    // sieht es der Datei an.
    const boese = {
      datei: 'boese.svg',
      beschreibung: 'Test',
      svg:
        '<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)">' +
        '<scr' + 'ipt>alert(2)</scr' + 'ipt>' +
        '<circle cx="5" cy="5" r="4" onclick="alert(3)"/></svg>',
    }
    const wurzel = wurzelMit('<span class="abbildung-block" data-datei="boese.svg"></span>')
    fuelleAbbildungen(wurzel, [boese])
    const html = wurzel.innerHTML
    expect(html).not.toContain('<script')
    expect(html).not.toContain('onload')
    expect(html).not.toContain('onclick')
    expect(wurzel.querySelector('circle')).not.toBeNull()
  })

  it('meldet sichtbar, wenn zum Platzhalter nichts hinterlegt ist', () => {
    // Eine leere Stelle im Text sieht aus wie ein Ladefehler und wird nicht gemeldet.
    const wurzel = wurzelMit('<span class="abbildung-block" data-datei="fehlt.svg"></span>')
    fuelleAbbildungen(wurzel, [WASSER])
    expect(wurzel.querySelector('.abbildung-fehlt').textContent).toContain('fehlt.svg')
  })

  it('meldet auch, wenn der Eintrag da ist, aber ohne SVG', () => {
    // Genau der Fall, den das Seed-Skript beim Import als „SVG nicht gefunden" meldet.
    const wurzel = wurzelMit('<span class="abbildung-block" data-datei="ohne.svg"></span>')
    fuelleAbbildungen(wurzel, [{ datei: 'ohne.svg', beschreibung: 'Ohne Datei' }])
    expect(wurzel.querySelector('.abbildung-fehlt').textContent).toContain('Datei fehlt')
  })

  it('füllt beim zweiten Lauf nicht doppelt', () => {
    const wurzel = wurzelMit('<span class="abbildung-block" data-datei="EN_H2O.svg"></span>')
    fuelleAbbildungen(wurzel, [WASSER])
    fuelleAbbildungen(wurzel, [WASSER])
    expect(wurzel.querySelectorAll('svg')).toHaveLength(1)
  })

  it('kommt ohne Wurzel und ohne Abbildungen aus', () => {
    expect(() => fuelleAbbildungen(null, [WASSER])).not.toThrow()
    const wurzel = wurzelMit('<span class="abbildung-block" data-datei="x.svg"></span>')
    expect(() => fuelleAbbildungen(wurzel, undefined)).not.toThrow()
  })
})

describe('Anzeigegröße', () => {
  const mitBreite = (attr) =>
    `<svg xmlns="http://www.w3.org/2000/svg" ${attr}><circle cx="5" cy="5" r="4"/></svg>`

  function svgAus(attr) {
    const d = document.createElement('div')
    d.innerHTML = mitBreite(attr)
    return d.querySelector('svg')
  }

  it('rechnet Punkt in Pixel um', () => {
    // ⚠️ Der Regelfall: Die Zeichnungen kommen aus LaTeX und tragen ihre **Druck**maße.
    // 39,1 pt sind 52 px — ein Wassermolekül von der Größe eines Wortes.
    expect(Math.round(intrinsischeBreite(svgAus("width='39.115786pt'")))).toBe(52)
  })

  it('nimmt eine blanke Zahl als Pixel', () => {
    expect(intrinsischeBreite(svgAus('width="145.331"'))).toBeCloseTo(145.331)
  })

  it('fällt auf die viewBox zurück, wenn Maße fehlen', () => {
    // Zwei der neun Piktogramme im Pilot tragen gar keine — der Browser setzte sie
    // sonst auf 300 × 150 und stauchte die Zeichnung hinein.
    expect(intrinsischeBreite(svgAus('viewBox="0 0 579 579"'))).toBe(579)
  })

  it('gibt null bei unbrauchbarer Angabe', () => {
    expect(intrinsischeBreite(svgAus('width="100%"'))).toBeNull()
    expect(intrinsischeBreite(svgAus(''))).toBeNull()
    expect(intrinsischeBreite(null)).toBeNull()
  })

  it('setzt die Breite auf das Vielfache der Eigengröße', () => {
    const wurzel = wurzelMit('<span class="abbildung-block" data-datei="a.svg"></span>')
    fuelleAbbildungen(wurzel, [
      { datei: 'a.svg', beschreibung: 'x', svg: mitBreite("width='39.115786pt'") },
    ])
    const svg = wurzel.querySelector('svg')
    expect(svg.style.width).toBe(`${Math.round(52.15 * ANZEIGE_FAKTOR)}px`)
  })

  it('⚠️ skaliert alle Bilder gleich, statt sie auf eine Breite zu ziehen', () => {
    // Alle Zeichnungen kommen aus derselben LaTeX-Strecke und haben dieselbe
    // Schriftgröße. Auf eine gemeinsame Zielbreite gezogen hätte das kleine Bild
    // fünfmal so große Beschriftung wie das große — dieselbe Zeichnung, zwei
    // Schriftgrößen.
    const wurzel = wurzelMit(
      '<span class="abbildung-block" data-datei="klein.svg"></span>' +
        '<span class="abbildung-block" data-datei="gross.svg"></span>',
    )
    fuelleAbbildungen(wurzel, [
      { datei: 'klein.svg', beschreibung: 'k', svg: mitBreite('width="40"') },
      { datei: 'gross.svg', beschreibung: 'g', svg: mitBreite('width="200"') },
    ])
    const [klein, gross] = [...wurzel.querySelectorAll('svg')].map((s) =>
      parseFloat(s.style.width),
    )
    expect(gross / klein).toBeCloseTo(5)
  })

  it('lässt die Eigengröße stehen, wenn sie sich nicht bestimmen lässt', () => {
    const wurzel = wurzelMit('<span class="abbildung-block" data-datei="a.svg"></span>')
    fuelleAbbildungen(wurzel, [
      { datei: 'a.svg', beschreibung: 'x', svg: mitBreite('width="100%"') },
    ])
    expect(wurzel.querySelector('svg').style.width).toBe('')
  })
})
