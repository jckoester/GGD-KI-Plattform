<script>
  /**
   * Vorgeschlagene Begriffe der Stunde (0.18, Plan „Begriffe aus den Phasentexten", F6).
   *
   * Ein eigener kleiner Modellaufruf bestimmt die Begriffe aus den Phasentexten — automatisch,
   * nachdem der Stundenassistent geschrieben hat, oder über den Knopf hier. Die Lehrkraft
   * hakt an: ✓ trägt ein, ✕ verwirft (`refs_dismissed`, kommt nicht wieder).
   *
   * Begriffe früherer Stunden stehen getrennt und lassen sich trotzdem eintragen. Sie sind
   * eine Planungshilfe, kein Lernstand (F1) — der Hinweis dazu steht sichtbar dabei.
   *
   * Props:
   * - vorschlag: `begriffe_vorschlag` aus `GET /planning/lessons/{id}` (oder null)
   * - refs, verworfen: Stand der Seite — was eingetragen oder verworfen ist, fällt weg
   * - veraltet: Der Entwurf hat sich seit dem Vorschlag geändert
   * - laedt, fehler: Zustand des Knopfs
   * - onUebernehmen(ref), onVerwerfen(nodeId), onVorschlagen(erzwingen)
   */
  import NodeTypeIcon from '$lib/components/NodeTypeIcon.svelte'
  import { kurzdatum, offeneVorschlaege, refAusVorschlag, vorschlagFehlerText } from '$lib/begriffe_der_stunde.js'

  const {
    vorschlag = null,
    refs = [],
    verworfen = [],
    veraltet = false,
    laedt = false,
    fehler = null,
    onUebernehmen = () => {},
    onVerwerfen = () => {},
    onVorschlagen = () => {},
  } = $props()

  const offen = $derived(offeneVorschlaege(vorschlag, refs, verworfen))
  const fehlerText = $derived(vorschlagFehlerText(fehler))
  const nichtsGefunden = $derived(
    vorschlag && !veraltet && !offen.eintraege.length && !offen.frueher.length && !offen.ohne.length,
  )

  const chip = 'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border border-dashed'
  const vorgeschlagen = 'border-light-pu dark:border-dark-pu text-light-pu dark:text-dark-pu'
  const knopf = 'opacity-70 hover:opacity-100'
</script>

<div class="space-y-1.5 text-xs">
  <div class="flex flex-wrap gap-1.5 items-center">
    <span class="text-light-tx-2 dark:text-dark-tx-2">Vorgeschlagen:</span>

    {#each offen.eintraege as e (e.node_id)}
      <span class="{chip} {vorgeschlagen}" title={[e.art, e.phase].filter(Boolean).join(' · ')}>
        <NodeTypeIcon category="concept" contentType={e.content_type ?? 'begriff'} size={12} />
        {e.titel}
        {#if e.aliase?.length}<span class="font-normal opacity-80">· {e.aliase.join(', ')}</span>{/if}
        <button onclick={() => onUebernehmen(refAusVorschlag(e))} class={knopf}
                aria-label={`„${e.titel}“ eintragen`} title="Eintragen">✓</button>
        <button onclick={() => onVerwerfen(e.node_id)} class={knopf}
                aria-label={`„${e.titel}“ verwerfen`} title="Verwerfen — kommt nicht wieder">✕</button>
      </span>
    {/each}

    {#if laedt}
      <span class="text-light-tx-2 dark:text-dark-tx-2 italic">Begriffe werden vorgeschlagen … (einige Sekunden)</span>
    {:else if !vorschlag}
      <button onclick={() => onVorschlagen(false)}
              class="border border-light-ui-3 dark:border-dark-ui-3 rounded px-2 py-0.5 text-light-tx-2 dark:text-dark-tx-2
                     hover:text-light-bl dark:hover:text-dark-bl">
        Begriffe vorschlagen
      </button>
    {:else if veraltet}
      <button onclick={() => onVorschlagen(false)}
              class="border border-light-ui-3 dark:border-dark-ui-3 rounded px-2 py-0.5 text-light-tx-2 dark:text-dark-tx-2
                     hover:text-light-bl dark:hover:text-dark-bl">
        Entwurf geändert — neu vorschlagen
      </button>
    {:else}
      {#if nichtsGefunden}
        <span class="text-light-tx-2 dark:text-dark-tx-2 italic">keine neuen Begriffe gefunden</span>
      {/if}
      <button onclick={() => onVorschlagen(true)}
              class="text-light-tx-2 dark:text-dark-tx-2 hover:text-light-bl dark:hover:text-dark-bl underline decoration-dotted">
        neu vorschlagen
      </button>
    {/if}
  </div>

  {#if offen.frueher.length}
    <div class="flex flex-wrap gap-1.5 items-center">
      <span class="text-light-tx-2 dark:text-dark-tx-2">In früheren Stunden eingetragen:</span>
      {#each offen.frueher as f (f.node_id)}
        <span class="{chip} border-light-ui-3 dark:border-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2">
          {f.titel}{#if kurzdatum(f.datum)}<span class="font-normal opacity-80">({kurzdatum(f.datum)})</span>{/if}
          <button onclick={() => onUebernehmen(refAusVorschlag(f))} class={knopf}
                  aria-label={`„${f.titel}“ auch hier eintragen`} title="Auch hier eintragen (etwa als Wiederholung)">✓</button>
        </span>
      {/each}
    </div>
    <p class="text-light-tx-2 dark:text-dark-tx-2 italic">{vorschlag?.hinweis_frueher}</p>
  {/if}

  {#if offen.ohne.length}
    <details class="text-light-tx-2 dark:text-dark-tx-2">
      <summary class="cursor-pointer">
        {offen.ohne.length} {offen.ohne.length === 1 ? 'Name' : 'Namen'} ohne Eintrag im Wissensspeicher
      </summary>
      <p class="mt-1">{offen.ohne.map((o) => o.name).join(', ')} — die Fachschaft kann fehlende Begriffe anlegen.</p>
    </details>
  {/if}

  {#if fehlerText}
    <p class="text-light-re dark:text-dark-re">{fehlerText}</p>
  {/if}
</div>
