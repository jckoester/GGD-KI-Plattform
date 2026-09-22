<script>
  /**
   * Planungsinhalt ohne Termin — und die beiden Wege zurück.
   *
   * Entsteht beim Umhängen der Jahresplanung auf ein neues Stundenraster: Gibt es
   * weniger Termine als Inhalte, bleibt der Rest hier liegen statt verloren zu gehen.
   *
   * **Zwei Wege zurück, verschieden in der Art.** *Umplanen*: auf eine freie Stunde
   * ziehen — mechanisch. *Kürzen*: Phasen in andere Stunden übernehmen oder streichen,
   * danach den Eintrag verwerfen — inhaltlich. Damit die zweite Wahl begründet möglich
   * ist, steht die Überhang-Bilanz dabei: welche Unterrichtseinheit über ihrem Soll liegt.
   *
   * ⚠️ **Nicht hinter einem Aufklapper.** Ein Parkplatz, den man wegklicken kann, ist am
   * nächsten Tag vergessen — und mit ihm die Stunden, die niemand mehr unterrichtet.
   * Ist er leer, verschwindet er ganz; ein leerer Kasten als Daueranzeige wäre Lärm.
   */
  import { CircleParking, Trash2 } from 'lucide-svelte'
  import { deleteParkplatzEintrag } from '$lib/api.js'
  import ErrorBanner from '$lib/components/ErrorBanner.svelte'

  let { eintraege = [], ueberhang = [], onGeaendert = () => {} } = $props()

  let fehler = $state(null)
  let verwirft = $state(null)

  const bilanz = $derived(new Map(ueberhang.map((u) => [u.ue_node_id, u])))

  async function verwerfen(eintrag) {
    verwirft = eintrag.id
    fehler = null
    try {
      await deleteParkplatzEintrag(eintrag.id)
      onGeaendert()
    } catch (e) {
      fehler = e.message
    } finally {
      verwirft = null
    }
  }

  function ziehen(ereignis, eintrag) {
    // Dasselbe Format, das `PlannerRow` beim Verschieben zwischen Stunden benutzt —
    // die Zielzeile muss nicht zwei Sorten Ladung unterscheiden.
    ereignis.dataTransfer.effectAllowed = 'move'
    ereignis.dataTransfer.setData('application/x-parkplatz', eintrag.id)
  }

  const datum = (wert) =>
    new Date(wert).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })
</script>

{#if eintraege.length}
  <div class="px-4 pt-2">
    <div
      class="rounded-lg border border-light-ui-3 dark:border-dark-ui-3
             bg-light-bg-2 dark:bg-dark-bg-2 p-3"
    >
      <div class="flex items-center gap-2 mb-2">
        <CircleParking class="w-4 h-4 text-light-tx-2 dark:text-dark-tx-2" />
        <h3 class="text-sm font-medium text-light-tx dark:text-dark-tx">
          Ohne Termin ({eintraege.length})
        </h3>
        <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
          auf eine freie Stunde ziehen — oder durch Kürzen eingliedern
        </span>
      </div>

      {#if fehler}<ErrorBanner message={fehler} />{/if}

      <ul class="flex flex-col gap-1.5">
        {#each eintraege as e (e.id)}
          <li
            draggable="true"
            ondragstart={(ev) => ziehen(ev, e)}
            class="flex items-start gap-2 rounded-md border border-dashed px-2.5 py-1.5
                   border-light-ui-3 dark:border-dark-ui-3
                   bg-light-bg dark:bg-dark-bg cursor-grab"
          >
            <span class="min-w-0 flex-1">
              <span class="block text-sm text-light-tx dark:text-dark-tx truncate">
                {e.thema || e.stunde_titel || 'Ohne Thema'}
              </span>
              <span class="block text-xs text-light-tx-2 dark:text-dark-tx-2">
                war für den {datum(e.herkunft_datum)} geplant{#if e.ue_titel} · {e.ue_titel}{/if}
                {#if bilanz.has(e.ue_node_id)}
                  · diese Einheit liegt {bilanz.get(e.ue_node_id).ueberhang} Stunden über Soll
                {/if}
              </span>
            </span>
            <button
              onclick={() => verwerfen(e)}
              disabled={verwirft === e.id}
              title="Verwerfen — der Stundenentwurf bleibt erhalten"
              aria-label="Eintrag verwerfen"
              class="flex-shrink-0 p-1 rounded text-light-tx-2 dark:text-dark-tx-2
                     hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 disabled:opacity-50"
            >
              <Trash2 class="w-4 h-4" />
            </button>
          </li>
        {/each}
      </ul>
    </div>
  </div>
{/if}
