import { describe, expect, it } from 'vitest'
import {
    budgetText, eintragText, einrichtungsRolle, fachFehltText, faecherLeerText, gutZuWissenSchueler, hinweisText,
    hinweisZeigen, kiHilft, rasterAnbieten, fertigZeilen, fortschritt, gutZuWissen, planungsStufe,
    seitenNummer, sichtbareSeiten, sollAufgehen, startIndex, SEITEN, SEITEN_JE_ROLLE, wegeWeiter,
    wegeWeiterSchueler,
} from './einrichtung.js'

const mitPlan = { stundenplan: { configured: true } }
const ohnePlan = { stundenplan: { configured: false } }

describe('Rolle (F10)', () => {
    it('Lehrkraft, auch mit Admin; Schüler:in (0.47); reiner Admin nicht', () => {
        expect(einrichtungsRolle(['teacher'])).toBe('teacher')
        expect(einrichtungsRolle(['teacher', 'admin'])).toBe('teacher')
        expect(einrichtungsRolle(['admin'])).toBeNull()
        expect(einrichtungsRolle(['student'])).toBe('student')
        expect(einrichtungsRolle(undefined)).toBeNull()
    })

    it('Doppelrolle: die Lehrkraft gewinnt (F9), unabhängig von der Reihenfolge', () => {
        expect(einrichtungsRolle(['student', 'teacher'])).toBe('teacher')
        expect(einrichtungsRolle(['teacher', 'student'])).toBe('teacher')
    })

    it('jede Seite einer Rolle hat einen Titel', () => {
        for (const seiten of Object.values(SEITEN_JE_ROLLE)) {
            for (const s of seiten) expect(SEITEN[s]?.titel, s).toBeTruthy()
        }
    })
})

describe('Seiten', () => {
    it('sechs mit Stundenplanquelle, fünf ohne', () => {
        expect(sichtbareSeiten('teacher', mitPlan)).toHaveLength(6)
        expect(sichtbareSeiten('teacher', ohnePlan)).not.toContain('stundenplan')
        expect(sichtbareSeiten('teacher', ohnePlan)).toHaveLength(5)
        expect(sichtbareSeiten(null, mitPlan)).toEqual([])
    })

    it('Nummer in der vollen Liste, Anzeige in der gezeigten', () => {
        expect(seitenNummer('teacher', 'gruppen')).toBe(5)
        const seiten = sichtbareSeiten('teacher', ohnePlan)
        expect(fortschritt(seiten.indexOf('gruppen'), seiten)).toBe('4 von 5')
    })
})

describe('Wiedereinstieg', () => {
    const seiten = sichtbareSeiten('teacher', mitPlan)

    it('nach „später“ dort, wo der Durchgang stand', () => {
        expect(seiten[startIndex('teacher', seiten, { stand: 'spaeter', seite: 3 })]).toBe('stufe')
    })

    it('entfallene Seite: die nächste gezeigte', () => {
        const ohne = sichtbareSeiten('teacher', ohnePlan)
        expect(ohne[startIndex('teacher', ohne, { stand: 'spaeter', seite: 4 })]).toBe('gruppen')
    })

    it('neu, erledigt oder abgewählt: von vorn', () => {
        expect(startIndex('teacher', seiten, { stand: null, seite: null })).toBe(0)
        expect(startIndex('teacher', seiten, { stand: 'erledigt', seite: 6 })).toBe(0)
        expect(startIndex('teacher', seiten, { stand: 'abgewaehlt', seite: 2 })).toBe(0)
    })
})

describe('Von selbst aufgehen (F3)', () => {
    it('auf jeder Seite, nur nicht in der Hilfe', () => {
        expect(sollAufgehen({ faellig: true }, '/chat')).toBe(true)
        expect(sollAufgehen({ faellig: true }, '/subjects/chemie/groups/3')).toBe(true)
        expect(sollAufgehen({ faellig: true }, '/help/chat')).toBe(false)
        expect(sollAufgehen({ faellig: false }, '/chat')).toBe(false)
        expect(sollAufgehen(null, '/chat')).toBe(false)
    })
})

describe('Verdrahtung', () => {
    it('einmal im Layout, über den Store geschaltet', async () => {
        const { readFileSync } = await import('node:fs')
        const { join } = await import('node:path')
        const layout = readFileSync(join(__dirname, '..', 'routes/(app)/+layout.svelte'), 'utf8')
        expect(layout).toContain('<EinrichtungDialog')
        expect(layout).toContain('sollAufgehen($einrichtung.daten, $page.url.pathname)')
        expect(layout).toMatch(/if \(einrichtungsRolle_\) ladeEinrichtung\(\)/)
    })

    it('Später speichert die Seite, die letzte Seite „erledigt“', async () => {
        const { readFileSync } = await import('node:fs')
        const { join } = await import('node:path')
        const dialog = readFileSync(join(__dirname, 'components/EinrichtungDialog.svelte'), 'utf8')
        expect(dialog).toContain("putEinrichtung('spaeter', seitenNummer(rolle, seite))")
        expect(dialog).toContain("putEinrichtung('erledigt', seitenNummer(rolle, seite))")
        expect(dialog).toContain('<Dialog open onClose={schliessen}')
    })
})

describe('Gut zu wissen', () => {
    const daten = { fristen: { chat_tage: 93, konto_tage: 90 } }
    const budget = { remaining_eur: 1.5, wochenbetrag_eur: 0.5, naechste_aufstockung: '2026-11-16', vorsprung_wochen: 4 }

    it('vier Absätze, Fristen aus der Antwort, Namen zuerst', () => {
        const absaetze = gutZuWissen(daten, budget)
        expect(absaetze).toHaveLength(4)
        expect(absaetze[0].titel).toMatch(/Namen/)
        expect(absaetze[0].links.map((l) => l.href)).toEqual(['/help/datenschutz', '/info/regeln'])
        expect(absaetze[1].text).toContain('93 Tagen')
        expect(absaetze[2].text).toContain('90 Tagen')
    })

    it('keine Bildkosten, kein Satz zu Assistenten (Prüfung 3, Schritt 0)', () => {
        const alles = gutZuWissen(daten, budget).map((a) => a.text).join(' ')
        expect(alles).not.toMatch(/Bild/)
        expect(alles).not.toMatch(/Assistent/)
    })

    it('Budget mit eigenen Zahlen, ohne Antwort allgemein', () => {
        const t = budgetText(budget)
        expect(t).toMatch(/^Gerade hast du .+Einheiten\./)
        expect(t).toContain('Jede Unterrichtswoche kommen')
        expect(t).toContain('4 Wochen')
        expect(t).toContain('Seitenleiste')
        expect(budgetText(null)).toBe('Dein Guthaben wächst jede Unterrichtswoche. Den Stand siehst du unten in der Seitenleiste.')
    })
})

describe('Fertig', () => {
    const stufen = [{ stufe: 1, name: 'Chatten', eintraege: ['chat'] }, { stufe: 3, name: 'Unterricht planen', eintraege: ['planner'] }]

    it('tatsächlicher Stand mit Ort zum Nachholen', () => {
        const z = fertigZeilen({ theme: 'dark', stufe: 3, stufen, kuerzelGesetzt: false, stundenplan: true, gruppen: 2 })
        expect(z.map((x) => x.text)).toEqual([
            'Erscheinungsbild: Dunkel', 'Umfang: Stufe 3 – Unterricht planen',
            'Kein Stundenplan-Kürzel gewählt', '2 Unterrichtsgruppen',
        ])
        expect(z[2]).toMatchObject({ ok: false, nachholen: 'Unterricht' })
    })

    it('ohne Stundenplanquelle keine Kürzel-Zeile', () => {
        const z = fertigZeilen({ theme: 'system', stufe: 1, stufen, kuerzelGesetzt: false, stundenplan: false, gruppen: 0 })
        expect(z.map((x) => x.text)).toEqual(['Erscheinungsbild: System', 'Umfang: Stufe 1 – Chatten', 'Noch keine Unterrichtsgruppe'])
    })

    it('ab der Planungsstufe „Zur Planung“ statt Assistent', () => {
        expect(planungsStufe({ stufen })).toBe(3)
        expect(planungsStufe(null)).toBeNull()
        expect(wegeWeiter(3, 3)[0].href).toBe('/planning')
        expect(wegeWeiter(2, 3)[0].href).toBe('/assistants')
        expect(wegeWeiter(3, null)[0].href).toBe('/assistants')
        expect(wegeWeiter(1, 3).map((w) => w.text)).toEqual(['Einen Assistenten ausprobieren', 'Die ersten 30 Minuten', 'Feedback geben'])
    })
})

describe('Seite 5 (F6)', () => {
    it('Stundenraster nur ab der Planungsstufe', () => {
        expect(rasterAnbieten(3, 3)).toBe(true)
        expect(rasterAnbieten(4, 3)).toBe(true)
        expect(rasterAnbieten(2, 3)).toBe(false)
        expect(rasterAnbieten(3, null)).toBe(false)
    })

    it('bettet die Bausteine von „Unterricht“ ein, Raster nach Stufe', async () => {
        const { readFileSync } = await import('node:fs')
        const { join } = await import('node:path')
        const dialog = readFileSync(join(__dirname, 'components/EinrichtungDialog.svelte'), 'utf8')
        expect(dialog).toContain('<GruppenAngebote />')
        expect(dialog).toContain('<GruppenVorschlaege />')
        expect(dialog).toContain('<StundenrasterUebernahme raster={mitRaster} />')
    })

    it('⚠️ Stundenraster: `wahl` im Effekt nur ungetrackt gelesen (sonst Endlosschleife)', async () => {
        const { readFileSync } = await import('node:fs')
        const { join } = await import('node:path')
        const quelle = readFileSync(join(__dirname, 'components/StundenrasterUebernahme.svelte'), 'utf8')
        expect(quelle).toContain('untrack(() => wahl)')
    })
})

describe('„Später“ (F4 a)', () => {
    it('Hinweis nur nach „später“', () => {
        expect(hinweisZeigen({ stand: 'spaeter', seite: 3 })).toBe(true)
        for (const stand of [null, 'erledigt', 'abgewaehlt']) expect(hinweisZeigen({ stand })).toBe(false)
        expect(hinweisZeigen(null)).toBe(false)
    })

    it('zählt die Seiten vor dem Wiedereinstieg', () => {
        expect(hinweisText('teacher', { ...mitPlan, stand: 'spaeter', seite: 3 })).toBe('2 von 6 Schritten erledigt.')
        expect(hinweisText('teacher', { ...ohnePlan, stand: 'spaeter', seite: 5 })).toBe('3 von 5 Schritten erledigt.')
    })

    it('Startseite, „Unterricht“ und Profil sind verdrahtet', async () => {
        const { readFileSync } = await import('node:fs')
        const { join } = await import('node:path')
        const lies = (p) => readFileSync(join(__dirname, '..', p), 'utf8')
        const start = lies('routes/(app)/welcome/+page.svelte')
        expect(start).toContain('hinweisZeigen($einrichtung.daten)')
        expect(start).toContain('onaction={oeffneEinrichtung}')
        expect(start).toContain('onclose={einrichtungAbwaehlen}')
        expect(lies('routes/(app)/teaching/+page.svelte')).toContain('<EinrichtungEintrag')
        expect(lies('routes/(app)/profile/+page.svelte')).toContain('<EinrichtungEintrag')
    })
})

describe('Schüler:innen (0.47)', () => {
    const daten = { fristen: { chat_tage: 93, konto_tage: 90 }, stundenplan: { configured: true } }

    it('fünf Seiten, keine entfällt — auch nicht ohne Stundenplanquelle', () => {
        expect(SEITEN_JE_ROLLE.student).toEqual(['willkommen', 'gut_zu_wissen', 'ki_hilft', 'faecher', 'fertig'])
        expect(sichtbareSeiten('student', ohnePlan)).toHaveLength(5)
        expect(fortschritt(3, sichtbareSeiten('student', daten))).toBe('4 von 5')
    })

    it('Gut zu wissen: Namen, wer mitliest (mit Ausnahme, F5), Fristen samt Konto (F2), Budget', () => {
        const absaetze = gutZuWissenSchueler(daten, null)
        expect(absaetze).toHaveLength(4)
        expect(absaetze[0].titel).toMatch(/Namen/)
        expect(absaetze[0].links.map((l) => l.href)).toEqual(['/help/datenschutz', '/info/regeln'])
        expect(absaetze[1].titel).toMatch(/niemand/)
        expect(absaetze[1].text).toMatch(/Notlage/)
        expect(absaetze[1].text).toMatch(/zwei Personen/)
        expect(absaetze[2].text).toContain('93 Tage')
        expect(absaetze[2].text).toContain('90 Tage')
        expect(absaetze[2].text).toMatch(/Werkstatt/)
        expect(absaetze[3].titel).toBe('Budget.')
    })

    it('ohne Budget (Vorschau) keine Zahlen, nur der allgemeine Satz', () => {
        const budget = gutZuWissenSchueler(daten, null)[3].text
        expect(budget).toMatch(/wächst jede Unterrichtswoche/)
        expect(budget).not.toMatch(/\d/)
    })

    it('mit Budget die eigenen Zahlen wie bei Lehrkräften', () => {
        const b = { remaining_eur: 1.5, einheiten_je_euro: 100 }
        expect(gutZuWissenSchueler(daten, b)[3].text).toBe(budgetText(b))
    })

    it('Texte ohne „Sie“ und ohne Fachwörter der Plattform', () => {
        const alle = [...gutZuWissenSchueler(daten, null), ...kiHilft()]
            .map((a) => `${a.titel} ${a.text}`).join(' ')
        expect(alle).not.toMatch(/\bSie\b/)
        expect(alle).not.toMatch(/Pseudonym|Baustein|Knoten|Token|LiteLLM|Modell/)
    })

    it('So hilft dir die KI: vier Absätze, Angabe mit Link aufs Zitieren', () => {
        const absaetze = kiHilft()
        expect(absaetze).toHaveLength(4)
        expect(absaetze[0].text).toMatch(/Absicht/)
        expect(absaetze[3].links).toEqual([{ text: 'KI-Ergebnisse zitieren', href: '/help/zitieren' }])
    })

    it('Deine Fächer: leer wie auf /subjects, Erprobung eigens', () => {
        expect(faecherLeerText(false)).toBe('Dir sind noch keine Fächer zugeordnet.')
        expect(faecherLeerText(true)).toMatch(/Erprobung/)
    })

    it('Fach fehlt: die Regel „Chat oder Assistent“ nur außerhalb der Erprobung', () => {
        expect(fachFehltText(false)).toMatch(/Assistenten für dich gibt/)
        expect(fachFehltText(true)).not.toMatch(/Assistenten für dich gibt/)
        for (const e of [true, false]) {
            expect(fachFehltText(e)).toMatch(/Schulkonto/)
            expect(fachFehltText(e)).toMatch(/Code/)
        }
    })

    it('Fertig: Chat, Assistenten, Hilfe für Schüler:innen', () => {
        expect(wegeWeiterSchueler().map((w) => w.href)).toEqual(['/chat', '/assistants', '/help/schueler'])
    })

    it('Hinweis auf der Startseite zählt in der Schüler-Liste', () => {
        const d = { ...daten, stand: 'spaeter', seite: seitenNummer('student', 'faecher') }
        expect(hinweisText('student', d)).toBe('3 von 5 Schritten erledigt.')
    })
})

describe('Dialog der Schüler:innen (0.47, Schritt 5)', () => {
    const lies = async (p) => {
        const { readFileSync } = await import('node:fs')
        const { join } = await import('node:path')
        return readFileSync(join(__dirname, p), 'utf8')
    }

    it('jede Seite der Schüler-Liste hat einen Inhalt im Dialog', async () => {
        const dialog = await lies('components/EinrichtungDialog.svelte')
        for (const s of SEITEN_JE_ROLLE.student) expect(dialog, s).toContain(`seite === '${s}'`)
    })

    it('Fächer: dieselbe Liste wie die Seitenleiste, Beitritt eingebettet', async () => {
        const dialog = await lies('components/EinrichtungDialog.svelte')
        expect(dialog).toContain('$sidebarSubjectSections')
        expect(dialog).toContain('<GruppeBeitreten gesperrt={vorschau} nachBeitritt={refreshMyGroups} />')
    })

    it('Vorschau (F6 a): kein Stand, kein Erscheinungsbild, kein Budget der Lehrkraft', async () => {
        const dialog = await lies('components/EinrichtungDialog.svelte')
        expect(dialog).toContain('if (erledigt || vorschau) return onClose(neu)')
        expect(dialog).toMatch(/erledigt = true\s+if \(vorschau\) return/)
        expect(dialog).toContain('disabled={vorschau}')
        expect(dialog).toContain('gutZuWissenSchueler(daten, vorschau ? null : $budget)')
    })

    it('Beitreten lässt sich sperren und meldet den Beitritt', async () => {
        const quelle = await lies('components/GruppeBeitreten.svelte')
        expect(quelle).toContain('const { gesperrt = false, nachBeitritt = null } = $props()')
        expect(quelle).toContain('nachBeitritt?.()')
        expect(quelle).toContain('disabled={gesperrt || arbeitet || !eingabe.trim()}')
    })
})

describe('Kasten „Einrichtung“ (0.47)', () => {
    it('nennt je Rolle, was der Durchgang enthält', () => {
        expect(eintragText('teacher')).toMatch(/Stundenplan und Gruppen/)
        expect(eintragText('student')).toMatch(/deine Fächer/)
        expect(eintragText('student')).not.toMatch(/Stundenplan|Gruppen|Oberfläche/)
    })
})
