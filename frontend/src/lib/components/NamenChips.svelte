<script>
  import { bausteinPfad } from '$lib/rueckweg.js'
  import { page } from '$app/stores'
  /**
   * Begriffe oder Fachmethoden am Eintrag eines Curriculums (0.44, Päckchen AQ) — Chips mit
   * Eingabe. Logik in `$lib/curriculum_begriffe.js`.
   *
   * **Begriffe** (`art="begriffe"`): Tippen sucht wie `BegriffSelector` im Fach und seinen
   * Bezugsfächern; Enter übernimmt auch einen Namen, den es (noch) nicht gibt. Die Chips
   * zeigen den Zustand aus `aufloesung` farbig (E5): verknüpft, Platzhalter, mehrdeutig.
   * Ein Platzhalter verlinkt aufs Anlegen, wenn die Person es darf (E6); im Editor in einem
   * neuen Tab, damit nichts Ungespeichertes verloren geht.
   *
   * **Fachmethoden** (`art="fachmethoden"`): nur Namen (E2); vorgeschlagen werden die, die in
   * den Curricula des Fachs schon stehen (gegen auseinanderlaufende Schreibweisen).
   *
   * Props: `namen` (Liste), `aufloesung` (Map), `editMode`, `subjectId`, `curriculumId`,
   * `darfAnlegen`, `back` (Rückweg nach dem Anlegen), `lokal` (Fachmethoden des offenen Editors,
   * auch ungespeicherte), `onchange(neueListe)`.
   */
  import { getContextNodes, getCurriculumFachmethoden } from '$lib/api.js'
  import { subjectMap } from '$lib/stores/subjects.js'
  import { bezugsfach, ordneTreffer, suchparameter } from '$lib/begriffe_der_stunde.js'
  import {
    CHIP_KLASSEN, anlegenPfad, ausTreffer, aufloesungVon, chipHinweis, chipText, chipZustand,
    enterWahl, fachmethodenVorschlaege, mitFassung, mitName, namensEintrag, ohneName,
  } from '$lib/curriculum_begriffe.js'

  let {
    art = 'begriffe',
    namen = [],
    aufloesung = new Map(),
    editMode = false,
    subjectId = null,
    curriculumId = null,
    darfAnlegen = false,
    back = null,
    lokal = [],
    onchange = () => {},
  } = $props()

  const begriffe = $derived(art === 'begriffe')
  const label = $derived(begriffe ? 'Begriffe' : 'Fachmethoden')

  let draft = $state('')
  let offen = $state(false)
  let treffer = $state([])
  let laedt = $state(false)
  let aktiv = $state(0)
  let navigiert = $state(false)
  let fassungWahl = $state(null) // Index des Chips, dessen Fassung gewählt wird
  let debounce = null

  const titelVon = (t) => (begriffe ? t.title : t.name)
  const angeboten = $derived(
    treffer.filter((t) => !namen.some((n) => n.name.toLocaleLowerCase('de') === String(titelVon(t)).toLocaleLowerCase('de'))),
  )

  function schliessen() {
    offen = false
    treffer = []
    aktiv = 0
    navigiert = false
  }

  function onInput() {
    const q = draft.trim()
    clearTimeout(debounce)
    navigiert = false
    if (!q) {
      schliessen()
      return
    }
    debounce = setTimeout(() => suche(q), 250)
  }

  async function suche(q) {
    laedt = true
    offen = true
    try {
      if (begriffe) {
        const res = await getContextNodes(suchparameter(q, subjectId))
        treffer = ordneTreffer(Array.isArray(res) ? res : (res.items ?? []), q)
      } else {
        const server = curriculumId ? await getCurriculumFachmethoden(curriculumId, q) : []
        treffer = fachmethodenVorschlaege(server, lokal, q)
      }
      aktiv = 0
    } catch {
      treffer = []
    } finally {
      laedt = false
    }
  }

  function uebernehmen(eintrag) {
    if (eintrag) onchange(mitName(namen, eintrag))
    draft = ''
    schliessen()
  }

  function waehleTreffer(t) {
    uebernehmen(begriffe ? ausTreffer(t) : namensEintrag(t.name))
  }

  function onKeydown(e) {
    if (e.key === 'ArrowDown' && angeboten.length) {
      e.preventDefault()
      aktiv = navigiert ? Math.min(aktiv + 1, angeboten.length - 1) : 0
      navigiert = true
    } else if (e.key === 'ArrowUp' && angeboten.length) {
      e.preventDefault()
      aktiv = Math.max(aktiv - 1, 0)
      navigiert = true
    } else if (e.key === 'Enter') {
      e.preventDefault()
      const wahl = enterWahl(draft, angeboten, aktiv, navigiert, titelVon)
      if (wahl?.treffer) waehleTreffer(wahl.treffer)
      else if (wahl?.text) uebernehmen(namensEintrag(wahl.text))
    } else if (e.key === 'Escape') {
      schliessen()
    }
  }
</script>

{#snippet chip(n, i)}
  {@const a = begriffe ? aufloesungVon(aufloesung, n) : null}
  {@const zustand = begriffe ? chipZustand(a) : 'fachmethode'}
  <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium {CHIP_KLASSEN[zustand]}"
        title={begriffe ? chipHinweis(a, { kannAnlegen: darfAnlegen }) : null}
        data-zustand={zustand}>
    {#if zustand === 'gefunden'}
      <a href={bausteinPfad(a.node_id, $page.url)} class="hover:underline">{chipText(n, a)}</a>
    {:else if zustand === 'mehrdeutig' && editMode}
      <button type="button" class="hover:underline" onclick={() => (fassungWahl = fassungWahl === i ? null : i)}
              aria-expanded={fassungWahl === i}>{chipText(n, a)} ▾</button>
    {:else}
      <span>{chipText(n, a)}</span>
    {/if}
    {#if zustand === 'fehlt' && darfAnlegen}
      <a href={anlegenPfad(subjectId, n.name, back)}
         target={editMode ? '_blank' : null} rel={editMode ? 'noopener' : null}
         class="font-normal underline opacity-80 hover:opacity-100"
         aria-label={`Begriff „${n.name}“ anlegen`}>anlegen</a>
    {/if}
    {#if editMode}
      <button type="button" onclick={() => { fassungWahl = null; onchange(ohneName(namen, i)) }}
              class="opacity-70 hover:opacity-100 ml-0.5" aria-label={`„${n.name}“ entfernen`}>✕</button>
    {/if}
  </span>
  {#if fassungWahl === i && a?.kandidaten}
    <span class="inline-flex flex-wrap gap-1 items-center text-xs">
      <span class="text-light-tx-2 dark:text-dark-tx-2">Fassung:</span>
      {#each a.kandidaten as k (k.node_id)}
        <button type="button"
                class="px-1.5 py-0.5 rounded border border-light-ui-3 dark:border-dark-ui-3 text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
                onclick={() => { fassungWahl = null; onchange(mitFassung(namen, i, k.fassung)) }}>
          {k.fassung || 'ohne Fassung'}{k.fach && k.subject_id !== subjectId ? ` · ${k.fach}` : ''}
        </button>
      {/each}
    </span>
  {/if}
{/snippet}

{#if editMode || namen.length}
  <div class="mt-2" data-feld={art}>
    <p class="text-xs font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1">{label}</p>
    {#if namen.length}
      <div class="flex flex-wrap gap-1.5 mb-1">
        {#each namen as n, i (`${n.name}\u0000${n.fassung ?? ''}`)}
          {@render chip(n, i)}
        {/each}
      </div>
    {/if}
    {#if editMode}
      <div class="relative">
        <input
          type="text"
          bind:value={draft}
          oninput={onInput}
          onkeydown={onKeydown}
          onblur={() => setTimeout(schliessen, 200)}
          placeholder={begriffe ? 'Begriff eintragen …' : 'Fachmethode eintragen …'}
          aria-label={begriffe ? 'Begriff eintragen' : 'Fachmethode eintragen'}
          class="w-full bg-transparent text-xs text-light-tx dark:text-dark-tx
                 border-b border-light-ui-3 dark:border-dark-ui-3 focus:border-primary dark:focus:border-primary-dark outline-none
                 placeholder:text-light-tx-2 dark:placeholder:text-dark-tx-2"
        />
        {#if offen}
          <div class="absolute top-full left-0 right-0 mt-1 z-50 min-w-[220px]
                      bg-light-bg dark:bg-dark-bg-2 border border-light-ui-3 dark:border-dark-ui-3
                      rounded-md shadow-xl max-h-64 overflow-y-auto">
            {#if laedt}
              <div class="px-3 py-2 text-xs text-light-tx-2 dark:text-dark-tx-2">Suche…</div>
            {:else}
              {#each angeboten as t, i (begriffe ? t.id : t.name)}
                {@const fach = begriffe ? bezugsfach(t, subjectId, $subjectMap) : null}
                <button
                  type="button"
                  onmousedown={(e) => { e.preventDefault(); waehleTreffer(t) }}
                  class="w-full px-3 py-1.5 text-left text-xs flex items-center gap-2 transition-colors
                         {navigiert && i === aktiv ? 'bg-light-ui-2 dark:bg-dark-ui-2' : 'hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
                >
                  <span class="truncate text-light-tx dark:text-dark-tx">{titelVon(t)}</span>
                  {#if begriffe && t.metadata?.fassung}
                    <span class="shrink-0 text-light-tx-2 dark:text-dark-tx-2">({t.metadata.fassung})</span>
                  {/if}
                  {#if fach}
                    <span class="ml-auto shrink-0 text-light-tx-2 dark:text-dark-tx-2">{fach}</span>
                  {:else if !begriffe}
                    <span class="ml-auto shrink-0 text-light-tx-2 dark:text-dark-tx-2">{t.anzahl}×</span>
                  {/if}
                </button>
              {/each}
              <div class="px-3 py-1.5 text-xs text-light-tx-2 dark:text-dark-tx-2 border-t border-light-ui-2 dark:border-dark-ui-2">
                Enter übernimmt „{draft.trim()}“{angeboten.length ? ' oder den gewählten Vorschlag' : ''}.
              </div>
            {/if}
          </div>
        {/if}
      </div>
    {/if}
  </div>
{/if}
