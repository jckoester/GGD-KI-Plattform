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
  import { getWeekPatternProposals, setWeekPattern, generateSlots } from "$lib/api.js"
  import { rasterJeGruppe } from "$lib/stundenplan_abgleich.js"
  import { calendarConfigured, ensureCalendarStatus } from "$lib/stores/calendarStatus.js"
  import ErrorBanner from "$lib/components/ErrorBanner.svelte"
  import InfoBanner from "$lib/components/InfoBanner.svelte"
  import WarningBanner from "$lib/components/WarningBanner.svelte"

  let laden = $state(false)
  let fehler = $state(null)
  let antwort = $state(null)
  let schreibt = $state(false)
  let ergebnisse = $state([])

  const gruppen = $derived(rasterJeGruppe(antwort))
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

  async function uebernehmen() {
    schreibt = true
    fehler = null
    const halbjahr = antwort?.halbjahr ?? 1
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
        await setWeekPattern(g.group_id, halbjahr, zeilen)
      } catch (e) {
        gesammelt.push({ gruppe: g.gruppe, text: `Muster nicht gespeichert: ${e.message}` })
        continue
      }
      try {
        const stats = await generateSlots(g.group_id, halbjahr)
        gesammelt.push({ gruppe: g.gruppe, text: `${stats.created} Stunden angelegt.` })
      } catch (e) {
        // 409 heißt: Das Halbjahr hat schon Stunden. Das Muster ist trotzdem gespeichert
        // — neu erzeugen würde bestehende Planung überschreiben und bleibt deshalb dem
        // Jahresplan vorbehalten, wo die Warnung dazu steht.
        gesammelt.push({
          gruppe: g.gruppe,
          text: e.status === 409
            ? "Muster gespeichert. Stunden bestehen bereits — Neuerzeugung im Jahresplan."
            : `Muster gespeichert, Stunden nicht erzeugt: ${e.message}`,
        })
      }
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
      message="Im Stundenplan wurde nichts gefunden, das zu einer Ihrer Unterrichtsgruppen passt."
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

    {#if antwort.fehlende_gruppen?.length}
      <InfoBanner
        message={`${antwort.fehlende_gruppen.length} Lerngruppen aus Ihrem Stundenplan haben auf der Plattform keine Unterrichtsgruppe und bleiben hier außen vor.`}
      />
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
{/if}
