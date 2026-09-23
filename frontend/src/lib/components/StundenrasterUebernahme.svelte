<script>
  /**
   * Stundenraster für **alle** eigenen Gruppen auf einmal aus dem Stundenplan übernehmen.
   *
   * Der Vorschlags-Endpunkt liest ohnehin den ganzen Stundenplan der Lehrkraft und
   * ordnet ihn den Gruppen zu — die Übernahme je Gruppe einzeln durchzugehen hieße, für
   * jede Gruppe denselben Abruf zu wiederholen und dafür durch jeden Jahresplan zu
   * navigieren. Hier steht das Ergebnis einmal, und ein Knopf schreibt es.
   *
   * Geschrieben wird über dieselben Endpunkte wie im Jahresplan
   * (`PUT …/pattern`, `POST …/slots/generate`) — kein zweiter Schreibpfad.
   */
  import { onMount } from "svelte"
  import { CalendarClock } from "lucide-svelte"
  import {
    createTeachingGroupFromTimetable,
    getWeekPatternProposals,
    setWeekPattern,
    generateSlots,
  } from "$lib/api.js"
  import { anlegbareGruppen, rasterJeGruppe } from "$lib/stundenplan_abgleich.js"
  import {
    halbjahrFuerMuster,
    halbjahreFuerUebernahme,
    restjahrMoeglich,
    slotMeldung,
    vierzehntaegigWarnung,
  } from "$lib/jahresraster.js"
  import { calendarConfigured, ensureCalendarStatus } from "$lib/stores/calendarStatus.js"
  import ErrorBanner from "$lib/components/ErrorBanner.svelte"
  import InfoBanner from "$lib/components/InfoBanner.svelte"
  import WarningBanner from "$lib/components/WarningBanner.svelte"

  let laden = $state(false)
  let fehler = $state(null)
  let antwort = $state(null)
  let schreibt = $state(false)
  let ergebnisse = $state([])
  let bisSchuljahresende = $state(true)
  let warnung = $state(null)

  let legtAn = $state(null)
  let anlegeFehler = $state(null)

  const gruppen = $derived(rasterJeGruppe(antwort))
  const anlegbar = $derived(anlegbareGruppen(antwort))
  const aktuellesHalbjahr = $derived(antwort?.halbjahr ?? 1)
  const restjahr = $derived(restjahrMoeglich(aktuellesHalbjahr))
  const unsicherGesamt = $derived(gruppen.reduce((n, g) => n + g.unsicher, 0))

  onMount(ensureCalendarStatus)

  async function lesen() {
    laden = true
    fehler = null
    ergebnisse = []
    try {
      antwort = await getWeekPatternProposals(4)
    } catch (e) {
      fehler = e.message
    } finally {
      laden = false
    }
  }

  async function anlegen(g) {
    legtAn = g.gruppe
    anlegeFehler = null
    try {
      await createTeachingGroupFromTimetable(g.gruppe, g.subjectId)
      // Neu lesen statt lokal streichen: Die angelegte Gruppe taucht danach als
      // **vorhanden** auf und ihr Wochenmuster lässt sich in einem Zug übernehmen.
      // Ein lokales Entfernen ließe die Liste und den Server auseinanderlaufen.
      await lesen()
    } catch (e) {
      anlegeFehler = e.message
    } finally {
      legtAn = null
    }
  }

  async function uebernehmen() {
    schreibt = true
    fehler = null
    warnung = null
    // Das Muster gilt für das Halbjahr, das der Stundenplan beschreibt — für das zweite
    // wird bewusst keins hinterlegt (`halbjahrFuerMuster`).
    const musterHalbjahr = halbjahrFuerMuster(aktuellesHalbjahr)
    const laeufe = halbjahreFuerUebernahme(aktuellesHalbjahr, bisSchuljahresende)
    const gesammelt = []
    for (const g of gruppen) {
      try {
        // Ausdrücklich aufgezählt statt „alles außer `sicher`": `sicher` ist eine
        // Einschätzung des Vorschlags, kein Feld des Wochenmusters.
        const zeilen = g.zeilen.map((z) => ({
          weekday: z.weekday,
          start_period: z.start_period,
          periods: z.periods,
          rhythmus: z.rhythmus,
        }))
        await setWeekPattern(g.group_id, musterHalbjahr, zeilen)
      } catch (e) {
        gesammelt.push({ gruppe: g.gruppe, text: `Muster nicht gespeichert: ${e.message}` })
        continue
      }
      const saetze = []
      for (const lauf of laeufe) {
        try {
          const stats = await generateSlots(g.group_id, lauf.halbjahr, false, lauf.vorlaeufig)
          saetze.push(slotMeldung(stats))
          warnung ??= vierzehntaegigWarnung(stats)
        } catch (e) {
          // 409 heißt: Das Halbjahr hat schon Stunden. Das Muster ist trotzdem
          // gespeichert — neu erzeugen würde bestehende Planung überschreiben und
          // bleibt deshalb dem Jahresplan vorbehalten, wo die Warnung dazu steht.
          saetze.push(
            e.status === 409
              ? `${lauf.halbjahr}. Halbjahr: Stunden bestehen bereits — Neuerzeugung im Jahresplan.`
              : `${lauf.halbjahr}. Halbjahr: nicht erzeugt (${e.message}).`,
          )
        }
      }
      gesammelt.push({ gruppe: g.gruppe, text: saetze.join(" ") })
    }
    ergebnisse = gesammelt
    schreibt = false
  }
</script>

{#if $calendarConfigured}
  <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx mb-1">
    Stundenraster aus dem Stundenplan
  </h2>
  <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-4">
    Liest vier Wochen Ihres Stundenplans und legt für jede Gruppe das Wochenmuster samt
    Stunden an. Dasselbe geht einzeln im Jahresplan jeder Gruppe.
  </p>

  {#if fehler}<ErrorBanner message={fehler} />{/if}

  {#if antwort === null}
    <button
      class="px-3 py-1.5 text-sm rounded-lg border border-light-ui-3 dark:border-dark-ui-3
             text-light-tx dark:text-dark-tx hover:bg-light-bg-2 dark:hover:bg-dark-bg-2
             disabled:opacity-50 flex items-center gap-1.5"
      disabled={laden}
      onclick={lesen}
    >
      <CalendarClock size={16} />
      {laden ? "Stundenplan wird gelesen …" : "Stundenplan lesen"}
    </button>
  {:else if gruppen.length === 0}
    <InfoBanner
      message={anlegbar.length
        ? "Im Stundenplan stehen Lerngruppen, für die es hier noch keine Unterrichtsgruppe gibt — unten anlegen."
        : "Im Stundenplan wurde nichts gefunden, das zu einer Ihrer Unterrichtsgruppen passt."}
    />
  {:else}
    <ul class="mb-4 flex flex-col gap-2">
      {#each gruppen as g (g.group_id)}
        <li class="rounded-lg border border-light-ui-3 dark:border-dark-ui-3 p-3">
          <p class="text-sm font-medium text-light-tx dark:text-dark-tx">{g.gruppe}</p>
          <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
            {g.zeilen.length}
            {g.zeilen.length === 1 ? "Termin" : "Termine"} erkannt{#if g.unsicher}
              · {g.unsicher} unsicher{/if}
          </p>
        </li>
      {/each}
    </ul>

    {#if unsicherGesamt}
      <WarningBanner
        message={`${unsicherGesamt} Termine sind unsicher — etwa, weil sie in den gelesenen Wochen nicht regelmäßig vorkamen. Nach der Übernahme im Jahresplan prüfen.`}
      />
    {/if}


    {#if restjahr && !ergebnisse.length}
      <label class="mt-3 flex items-start gap-2">
        <input type="checkbox" bind:checked={bisSchuljahresende} class="mt-0.5 accent-primary" />
        <span class="text-sm text-light-tx dark:text-dark-tx">
          Stunden bis zum Schuljahresende anlegen
          <span class="block text-xs text-light-tx-2 dark:text-dark-tx-2">
            Das 2. Halbjahr entsteht <strong>vorläufig</strong> aus dem jetzigen Raster —
            damit die Jahresplanung Termine hat. Kommt der Stundenplan für das 2. Halbjahr,
            wird es neu aufgebaut und die Planung umgehängt.
          </span>
        </span>
      </label>
    {/if}

    {#if warnung}
      <div class="mt-3"><WarningBanner message={warnung} /></div>
    {/if}

    {#if ergebnisse.length}
      <ul class="mt-3 flex flex-col gap-1">
        {#each ergebnisse as e (e.gruppe)}
          <li class="text-sm text-light-tx-2 dark:text-dark-tx-2">
            <span class="text-light-tx dark:text-dark-tx">{e.gruppe}:</span> {e.text}
          </li>
        {/each}
      </ul>
    {:else}
      <div class="mt-3 flex gap-2">
        <button
          class="px-3 py-1.5 text-sm rounded-lg bg-primary dark:bg-primary-dark text-white
                 disabled:opacity-50"
          disabled={schreibt}
          onclick={uebernehmen}
        >
          {schreibt ? "Wird übernommen …" : `Für ${gruppen.length} Gruppen übernehmen`}
        </button>
        <button
          class="px-3 py-1.5 text-sm rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                 text-light-tx dark:text-dark-tx"
          onclick={() => { antwort = null }}
        >
          Abbrechen
        </button>
      </div>
    {/if}
  {/if}

  {#if anlegbar.length}
    <div class="mt-3 rounded-lg border border-light-ui-3 dark:border-dark-ui-3 p-3">
      <h4 class="text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
        Noch ohne Unterrichtsgruppe ({anlegbar.length})
      </h4>
      <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mb-2">
        Diese Lerngruppen stehen in Ihrem Stundenplan, aber nicht auf der Plattform.
        Angelegt werden Sie darin zur Lehrkraft.
      </p>

      {#if anlegeFehler}<ErrorBanner message={anlegeFehler} />{/if}

      <ul class="flex flex-col gap-1.5">
        {#each anlegbar as g (g.gruppe)}
          <li
            class="flex items-start gap-3 rounded-md border border-light-ui-3
                   dark:border-dark-ui-3 px-2.5 py-2"
          >
            <span class="min-w-0 flex-1">
              <span class="block text-sm text-light-tx dark:text-dark-tx">
                {g.name}
              </span>
              <span class="block text-xs text-light-tx-2 dark:text-dark-tx-2">
                {g.herkunft}
              </span>
            </span>
            <button
              onclick={() => anlegen(g)}
              disabled={legtAn === g.gruppe || schreibt}
              class="flex-shrink-0 px-2.5 py-1 rounded-md text-xs font-medium
                     bg-primary dark:bg-primary-dark text-white disabled:opacity-50"
            >
              {legtAn === g.gruppe ? "Legt an …" : "Anlegen"}
            </button>
          </li>
        {/each}
      </ul>
    </div>
  {/if}
{/if}
