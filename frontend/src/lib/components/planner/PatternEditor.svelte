<script>
  import { setWeekPattern, generateSlots, getWeekPatternProposals, getAbWochen } from '$lib/api.js'
  import { terminzeile } from '$lib/ab_wochen.js'
  import {
    diagnose,
    diagnoseHatInhalt,
    OHNE_GRUPPE,
    ZUR_GRUPPE,
  } from '$lib/stundenplan_abgleich.js'
  import {
    restjahrMoeglich,
    slotMeldung,
    vierzehntaegigWarnung,
  } from '$lib/jahresraster.js'
  import { calendarConfigured, ensureCalendarStatus } from '$lib/stores/calendarStatus.js'
  import ErrorBanner from '$lib/components/ErrorBanner.svelte'
  import SuccessBanner from '$lib/components/SuccessBanner.svelte'
  import WarningBanner from '$lib/components/WarningBanner.svelte'

  const { open = false, groupId, patterns = [], onSaved, onGenerated, onClose } = $props()

  const WEEKDAYS = ['Mo', 'Di', 'Mi', 'Do', 'Fr']
  // Stundenraster der Schule — schulspezifisch, via Umgebungsvariable konfigurierbar.
  // Ausgelassene Stunden (z.B. keine 7. Stunde) werden einfach in der Liste weggelassen.
  const PERIODS = JSON.parse(import.meta.env.PUBLIC_PERIODS || '[1,2,3,4,5,6,7,8]')

  let halbjahr = $state(1)
  let rows = $state([])
  let saving = $state(false)
  let generating = $state(false)
  let error = $state(null)
  let genSuccess = $state(null)
  let genWarnung = $state(null)
  // Schultage des Halbjahres nach A-/B-Woche getrennt — damit unter jedem 14-tägigen
  // Muster die konkreten Termine stehen können. Scheitert der Abruf, bleibt es beim
  // bloßen Buchstaben; das ist kein Grund, den Dialog zu stören.
  let abWochen = $state(null)
  // Nur im 1. Halbjahr: Das 2. vorläufig mit anlegen, damit die Jahresplanung Termine hat.
  let bisSchuljahresende = $state(true)
  const heute = new Date().toISOString().slice(0, 10)

  // Lokalen State mit aktuellen Mustern für gewähltes Halbjahr befüllen
  $effect(() => {
    if (open) {
      syncRows()
      error = null
      genSuccess = null
      genWarnung = null
      // Ob eine Stundenplanquelle eingerichtet ist, entscheidet über den
      // Übernahme-Knopf. Den Status holt sonst niemand auf dieser Route — er wurde bis
      // 14.09.2026 nur in der Admin-Seitenleiste geladen, und der Knopf fehlte deshalb
      // immer. `ensureCalendarStatus` fragt höchstens einmal je Sitzung.
      ensureCalendarStatus()
    }
  })

  // Eigener Effekt, denn die Termine hängen am Halbjahr: Der obige läuft nur beim Öffnen,
  // das Auswahlfeld für das Halbjahr steht aber im Dialog.
  $effect(() => {
    if (!open) return
    const hj = halbjahr
    abWochen = null
    getAbWochen(hj)
      .then((k) => {
        if (halbjahr === hj) abWochen = k
      })
      .catch(() => {})
  })

  $effect(() => {
    syncRows()
  })

  function syncRows() {
    rows = patterns
      .filter(p => p.halbjahr === halbjahr)
      .map(p => ({
        weekday: p.weekday,
        start_period: p.start_period,
        periods: p.periods,
        rhythmus: p.rhythmus ?? 'woechentlich',
      }))
  }

  // ── Übernahme aus dem Stundenplan (UP-8, Schritt 10b) ────────────────────
  // Der Vorschlag füllt den Editor, statt direkt zu speichern: Die Lehrkraft sieht, was
  // übernommen würde, kann korrigieren und speichert mit demselben Knopf wie sonst.
  // Ein eigener Schreibpfad daneben wäre eine zweite Wahrheit.
  let holeVorschlag = $state(false)
  let vorschlagHinweis = $state(null)
  // Was der Abruf sonst noch hergab. Der Endpunkt meldet die erkannten Lerngruppen, die
  // fehlenden Gruppen, unbekannte Fachkürzel und Hinweise — ohne das bliebe im Fehlschlag
  // nur „nichts gefunden" mit geratenen Ursachen.
  let befund = $state(null)
  let befundOffen = $state(false)

  async function ausStundenplan() {
    holeVorschlag = true
    error = null
    vorschlagHinweis = null
    befund = null
    try {
      const data = await getWeekPatternProposals(4)
      const eigene = (data.patterns ?? []).filter(p => p.group_id === groupId)
      befund = diagnose(data, groupId)
      if (eigene.length === 0) {
        vorschlagHinweis = 'Für diese Gruppe wurde im Stundenplan nichts gefunden.'
        // Aufgeklappt, denn genau jetzt ist die Frage „warum nicht?" — und die Antwort
        // steht darunter. Bei einem Treffer bleibt der Befund zu, er stört dann nur.
        befundOffen = true
        return
      }
      befundOffen = false
      halbjahr = data.halbjahr ?? halbjahr
      rows = eigene.map(p => ({
        weekday: p.weekday,
        start_period: p.start_period,
        periods: p.periods,
        rhythmus: p.rhythmus,
      }))
      const unsicher = eigene.filter(p => !p.sicher).length
      vorschlagHinweis =
        `${eigene.length} Einträge aus ${data.wochen?.length ?? 0} Wochen übernommen`
        + (unsicher ? ` — ${unsicher} davon unsicher, bitte prüfen.` : '. Bitte prüfen und speichern.')
    } catch (e) {
      error = e.message
    } finally {
      holeVorschlag = false
    }
  }

  function addRow() {
    rows = [...rows, { weekday: 0, start_period: 1, periods: 1, rhythmus: 'woechentlich' }]
  }

  function removeRow(i) {
    rows = rows.filter((_, idx) => idx !== i)
  }

  function updateRow(i, key, value) {
    // `rhythmus` ist als einziges Feld Text — `Number()` machte daraus NaN.
    const wert = key === 'rhythmus' ? value : Number(value)
    rows = rows.map((r, idx) => idx === i ? { ...r, [key]: wert } : r)
  }

  // Der Ablauf hat **eine** erwartete Reihenfolge: speichern, dann erzeugen. Bis
  // 15.09.2026 waren das vier Knöpfe, und „Generieren" las das Muster aus der
  // **Datenbank** — wer nach „Aus Stundenplan übernehmen" direkt darauf drückte, erzeugte
  // Stunden aus dem alten Muster. Bei einer neuen Gruppe keine, bei einer bestehenden
  // lautlos die falschen. Deshalb gibt es den Schritt einzeln nicht mehr.
  const VORHANDEN = 'vorhanden'

  const ERSETZEN_FRAGE =
    'Für dieses Halbjahr gibt es bereits Stunden. Neu erzeugen ersetzt sie — Thema, ' +
    'verknüpfte Unterrichtseinheit und Nachbereitungsstand gehen dabei verloren. ' +
    'Ein Wiederherstellungspunkt wird angelegt. Fortfahren?'

  /** Schreibt das Muster. Gibt zurück, ob es geklappt hat. */
  async function speichern() {
    saving = true
    error = null
    try {
      const updated = await setWeekPattern(groupId, halbjahr, rows)
      onSaved(halbjahr, updated)
      return true
    } catch (e) {
      error = e.message
      return false
    } finally {
      saving = false
    }
  }

  const restjahr = $derived(restjahrMoeglich(halbjahr))

  async function nurSpeichern() {
    genSuccess = null
    genWarnung = null
    if (await speichern()) {
      genSuccess = `Wochenmuster für HJ ${halbjahr} gespeichert. Vorhandene Stunden wurden nicht angetastet.`
    }
  }

  async function speichernUndErzeugen() {
    genSuccess = null
    genWarnung = null
    if (!(await speichern())) return

    let ergebnis = await generate(false)
    if (ergebnis === VORHANDEN) {
      // Die Frage darf nicht wegfallen: Neu erzeugen löscht die Stunden des Halbjahres.
      // Der Wiederherstellungspunkt ist eine Rückfahrkarte, keine Erlaubnis.
      if (!confirm(ERSETZEN_FRAGE)) {
        genSuccess =
          `Wochenmuster für HJ ${halbjahr} gespeichert. Die vorhandenen Stunden blieben unverändert.`
        return
      }
      ergebnis = await generate(true)
    }
    if (ergebnis !== true) return

    // Das 2. Halbjahr vorläufig mitnehmen, damit die Jahresplanung über den
    // Halbjahreswechsel hinweg Termine hat. Ein 409 heißt hier: Dort stehen schon
    // Stunden — die bleiben unangetastet, das ist kein Fehlschlag dieses Dialogs.
    if (bisSchuljahresende && restjahrMoeglich(halbjahr)) {
      try {
        const stats = await generateSlots(groupId, 2, false, true)
        genSuccess += ` ${slotMeldung(stats)}`
        genWarnung = vierzehntaegigWarnung(stats) ?? genWarnung
        onGenerated(stats, { regenerate: false, halbjahr: 2 })
      } catch (e) {
        if (e.status !== 409) error = e.message
      }
    }
    onClose()
  }

  /** `true` | `false` | `VORHANDEN` — Letzteres heißt: Es gibt schon Stunden (409). */
  async function generate(regenerate = false) {
    generating = true
    error = null
    try {
      const stats = await generateSlots(groupId, halbjahr, regenerate)
      genSuccess = slotMeldung(stats)
      if (stats.used_hj1_fallback) genSuccess += ' (HJ-1-Muster als Fallback verwendet)'
      // Als Warnung, nicht als Anhängsel: Über den Halbjahreswechsel hinweg ist die
      // A-/B-Phase die einzige Angabe, die um eine Woche danebenliegen kann. Der Satz
      // steht in `jahresraster.js`, weil die Sammelübernahme ihn ebenfalls braucht.
      genWarnung = vierzehntaegigWarnung(stats) ?? genWarnung
      onGenerated(stats, { regenerate, halbjahr })
      return true
    } catch (e) {
      if (e.status === 409 && !regenerate) return VORHANDEN
      error = e.message
      return false
    } finally {
      generating = false
    }
  }
</script>

{#if open}
  <div
    class="fixed inset-0 z-50 bg-black/40 flex items-center justify-center"
    onclick={(e) => { if (e.target === e.currentTarget) onClose() }}
  >
    <div class="bg-light-bg dark:bg-dark-bg border border-light-ui-3 dark:border-dark-ui-3 rounded-xl shadow-2xl w-full max-w-lg p-6">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-base font-semibold text-light-tx dark:text-dark-tx">Wochenmuster bearbeiten</h2>
        <button
          onclick={onClose}
          class="p-1.5 rounded hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 text-light-tx-2 dark:text-dark-tx-2 transition-colors"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"
               fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      <!-- Halbjahr-Auswahl -->
      <div class="flex gap-1 mb-4">
        {#each [1, 2] as hj}
          <button
            onclick={() => { halbjahr = hj }}
            class="px-4 py-1.5 rounded-md text-sm font-medium transition-colors
                   {halbjahr === hj
                     ? 'bg-primary dark:bg-primary-dark text-white'
                     : 'bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
          >
            {hj}. Halbjahr
          </button>
        {/each}
      </div>

      {#if $calendarConfigured}
        <div class="mb-4">
          <button
            onclick={ausStundenplan}
            disabled={holeVorschlag}
            class="w-full px-3 py-2 text-sm rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                   text-light-tx dark:text-dark-tx hover:bg-light-bg-2 dark:hover:bg-dark-bg-2
                   transition-colors disabled:opacity-50"
          >
            {holeVorschlag ? 'Stundenplan wird gelesen …' : 'Aus Stundenplan übernehmen'}
          </button>
          {#if vorschlagHinweis}
            <p class="mt-2 text-sm text-light-tx-2 dark:text-dark-tx-2">{vorschlagHinweis}</p>
          {/if}
          {#if diagnoseHatInhalt(befund)}
            <details
              open={befundOffen}
              class="mt-2 text-sm text-light-tx-2 dark:text-dark-tx-2"
            >
              <summary class="cursor-pointer text-light-bl dark:text-dark-bl">
                Was der Stundenplan hergab
              </summary>
              <div class="mt-2 space-y-2 border-l-2 border-light-ui-3 dark:border-dark-ui-3 pl-3">
                {#if befund.kuerzel}
                  <p>Kürzel <strong>{befund.kuerzel}</strong>, {befund.wochen} Wochen gelesen.</p>
                {/if}

                {#if befund.lerngruppen.length}
                  <div>
                    <p class="font-medium text-light-tx dark:text-dark-tx">Erkannte Lerngruppen</p>
                    <ul class="mt-1 space-y-0.5">
                      {#each befund.lerngruppen as l}
                        <li>
                          <span class="text-light-tx dark:text-dark-tx">{l.label}</span>
                          {#if l.klassen.length}({l.klassen.join(', ')}){/if}
                          —
                          {#if l.status === ZUR_GRUPPE}
                            dieser Gruppe zugeordnet
                          {:else if l.status === OHNE_GRUPPE}
                            keiner Ihrer Gruppen zugeordnet
                          {:else}
                            einer anderen Ihrer Gruppen zugeordnet
                          {/if}
                        </li>
                      {/each}
                    </ul>
                  </div>
                {/if}

                {#if befund.fehlend.length}
                  <div>
                    <p class="font-medium text-light-tx dark:text-dark-tx">
                      Dafür gibt es noch keine Unterrichtsgruppe
                    </p>
                    <ul class="mt-1 space-y-0.5">
                      {#each befund.fehlend as g}
                        <li>{g.name}</li>
                      {/each}
                    </ul>
                  </div>
                {/if}

                {#if befund.unbekannt.length}
                  <div>
                    <p class="font-medium text-light-tx dark:text-dark-tx">
                      Unbekannte Fachkürzel
                    </p>
                    <ul class="mt-1 space-y-0.5">
                      {#each befund.unbekannt as f}
                        <li>{f.code} ({f.stunden} Stunden) — bitte der Administration melden</li>
                      {/each}
                    </ul>
                  </div>
                {/if}

                {#if befund.hinweise.length}
                  <ul class="space-y-0.5">
                    {#each befund.hinweise as h}
                      <li>{h}</li>
                    {/each}
                  </ul>
                {/if}
              </div>
            </details>
          {/if}
        </div>
      {/if}

      <!-- Muster-Zeilen -->
      <div class="mb-3">
        {#if rows.length === 0}
          <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 italic py-2">
            Keine Einträge — bitte "+ Zeile" klicken.
          </p>
        {:else}
          <div class="space-y-2">
            {#each rows as row, i}
              <div>
              <div class="flex items-center gap-2">
                <select
                  value={row.weekday}
                  onchange={(e) => updateRow(i, 'weekday', e.currentTarget.value)}
                  class="px-2 py-1 text-sm bg-light-bg-2 dark:bg-dark-bg-2 border border-light-ui-3 dark:border-dark-ui-3 rounded-md
                         text-light-tx dark:text-dark-tx outline-none focus:border-primary dark:focus:border-primary-dark"
                >
                  {#each WEEKDAYS as d, j}
                    <option value={j}>{d}</option>
                  {/each}
                </select>

                <select
                  value={row.start_period}
                  onchange={(e) => updateRow(i, 'start_period', e.currentTarget.value)}
                  class="px-2 py-1 text-sm bg-light-bg-2 dark:bg-dark-bg-2 border border-light-ui-3 dark:border-dark-ui-3 rounded-md
                         text-light-tx dark:text-dark-tx outline-none focus:border-primary dark:focus:border-primary-dark"
                >
                  {#each PERIODS as p}
                    <option value={p}>{p}. Stunde</option>
                  {/each}
                </select>

                <select
                  value={row.periods}
                  onchange={(e) => updateRow(i, 'periods', e.currentTarget.value)}
                  class="px-2 py-1 text-sm bg-light-bg-2 dark:bg-dark-bg-2 border border-light-ui-3 dark:border-dark-ui-3 rounded-md
                         text-light-tx dark:text-dark-tx outline-none focus:border-primary dark:focus:border-primary-dark"
                >
                  <option value={1}>Einzelstunde</option>
                  <option value={2}>Doppelstunde</option>
                </select>

                <select
                  value={row.rhythmus ?? 'woechentlich'}
                  onchange={(e) => updateRow(i, 'rhythmus', e.currentTarget.value)}
                  class="px-2 py-1 text-sm bg-light-bg-2 dark:bg-dark-bg-2 border border-light-ui-3 dark:border-dark-ui-3 rounded-md
                         text-light-tx dark:text-dark-tx outline-none focus:border-primary dark:focus:border-primary-dark"
                >
                  <option value="woechentlich">wöchentlich</option>
                  <option value="a_woche">A-Woche</option>
                  <option value="b_woche">B-Woche</option>
                </select>

                <button
                  onclick={() => removeRow(i)}
                  class="p-1 rounded hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 text-light-tx-2 dark:text-dark-tx-2 hover:text-light-re dark:hover:text-dark-re transition-colors"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
                       fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                  </svg>
                </button>
              </div>
              <!-- Die konkreten Termine machen den Buchstaben entbehrlich: Heißt die
                   Woche im Stundenplan anders, zählt hier das Datum. -->
              {#if terminzeile(abWochen, row.weekday, row.rhythmus, { ab: heute })}
                <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mt-1 ml-1">
                  findet statt am {terminzeile(abWochen, row.weekday, row.rhythmus, { ab: heute })}
                </p>
              {/if}
              </div>
            {/each}
          </div>
        {/if}
        <button
          onclick={addRow}
          class="mt-2 text-sm text-light-bl dark:text-dark-bl hover:opacity-80 transition-opacity"
        >+ Zeile</button>
      </div>

      {#if error}
        <ErrorBanner message={error} />
      {/if}
      {#if genSuccess}
        <SuccessBanner message={genSuccess} />
      {/if}
      {#if genWarnung}
        <WarningBanner message={genWarnung} />
      {/if}

      <!-- Aktionen -->
      <!--
        Zwei Knöpfe, nicht vier. Der Primärknopf ist der **Abschluss** des Ablaufs, nicht
        sein mittlerer Schritt: speichern, erzeugen, schließen. „Generieren HJx" und „Neu
        generieren" gab es bis 15.09.2026 einzeln — sie lasen das Muster aus der Datenbank
        und erzeugten nach dem Übernehmen aus dem Stundenplan lautlos die falschen Stunden.
      -->
      {#if restjahr}
        <label class="flex items-start gap-2 pt-4">
          <input type="checkbox" bind:checked={bisSchuljahresende} class="mt-0.5 accent-primary" />
          <span class="text-sm text-light-tx dark:text-dark-tx">
            Stunden bis zum Schuljahresende anlegen
            <span class="block text-xs text-light-tx-2 dark:text-dark-tx-2">
              Das 2. Halbjahr entsteht <strong>vorläufig</strong> aus diesem Raster — damit
              die Jahresplanung Termine hat. Kommt der Stundenplan für das 2. Halbjahr,
              wird es neu aufgebaut und die Planung umgehängt.
            </span>
          </span>
        </label>
      {/if}

      <div class="flex items-center justify-between pt-4 border-t border-light-ui-3 dark:border-dark-ui-3">
        <button
          onclick={onClose}
          class="px-4 py-2 text-sm rounded-lg text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 transition-colors"
        >Schließen</button>
        <div class="flex gap-2">
          <button
            onclick={nurSpeichern}
            disabled={saving || generating}
            class="px-4 py-2 text-sm rounded-lg font-medium border border-light-ui-3 dark:border-dark-ui-3
                   text-light-tx dark:text-dark-tx hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 transition-colors
                   disabled:opacity-50 disabled:cursor-not-allowed"
          >Nur speichern</button>
          <!-- Ohne Zeilen gibt es nichts zu erzeugen: Der Lauf schriebe ein leeres Muster
               und böte danach an, die vorhandenen Stunden durch **keine** zu ersetzen —
               eine zerstörerische Kette hinter einem einzigen Klick. Ein Muster bewusst
               leeren geht weiterhin über „Nur speichern". -->
          <button
            onclick={speichernUndErzeugen}
            disabled={saving || generating || rows.length === 0}
            class="px-4 py-2 text-sm rounded-lg font-medium bg-primary dark:bg-primary-dark text-white
                   hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving
              ? 'Speichern…'
              : generating
                ? 'Stunden werden erzeugt…'
                : 'Speichern und Stunden erzeugen'}
          </button>
        </div>
      </div>
    </div>
  </div>
{/if}
