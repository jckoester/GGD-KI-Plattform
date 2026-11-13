<script>
  /**
   * Stunde oder Einheit als Vorlage kopieren (0.42, Päckchen AO, Schritt 5).
   *
   * Ziel: eine eigene aktuelle Gruppe desselben Fachs (F5); bei einer Stunde dazu eine Einheit
   * der Gruppe oder eine neue (F6). Nach dem Kopieren zeigt der Dialog einen Link zur Kopie und,
   * was nicht oder umgestellt übernommen wurde. Die Regeln dahinter: `app/planning/kopieren.py`.
   *
   * Props: `art` ('stunde' | 'einheit'), `quelle` ({id, titel, einheitTitel?}), `fachId` (Fach der Quelle),
   * `onKopiert(ergebnis, gruppe)` — etwa, damit der Planer neu lädt, wenn in dieselbe Gruppe
   * kopiert wurde.
   */
  import { untrack } from 'svelte'
  import Dialog from '$lib/components/Dialog.svelte'
  import ErrorBanner from '$lib/components/ErrorBanner.svelte'
  import InfoBanner from '$lib/components/InfoBanner.svelte'
  import LoadingBanner from '$lib/components/LoadingBanner.svelte'
  import SuccessBanner from '$lib/components/SuccessBanner.svelte'
  import { copyLesson, copyUnit, getPlanungsgruppen, listUnits } from '$lib/api.js'
  import {
    ergebnisPfad, kopierAnfrage, meldungenZusammenfassung, meldungText, NEUE_EINHEIT, zielGruppen,
  } from '$lib/planung_kopieren.js'

  const { open = false, art = 'stunde', quelle = null, fachId = null, onClose, onKopiert = null } = $props()

  let gruppen = $state([])
  let laedt = $state(false)
  let fehler = $state(null)
  let gruppeId = $state(null)
  let einheiten = $state([])
  let einheitenLaden = $state(false)
  let einheitWahl = $state('')
  let neuerTitel = $state('')
  let laeuft = $state(false)
  let ergebnis = $state(null)

  const istStunde = $derived(art === 'stunde')
  const gruppe = $derived(gruppen.find((g) => g.id === gruppeId) ?? null)
  const anfrage = $derived(kopierAnfrage(art, { gruppeId, einheitWahl, neuerTitel }))
  const link = $derived(ergebnisPfad(art, ergebnis, gruppe))

  // Beim Öffnen frisch: Zielgruppen laden, alte Auswahl und altes Ergebnis vergessen.
  $effect(() => {
    if (!open) return
    fehler = null
    ergebnis = null
    einheitWahl = ''
    neuerTitel = ''
    laedt = true
    getPlanungsgruppen()
      .then((alle) => {
        gruppen = zielGruppen(alle, fachId)
        gruppeId = gruppen.length === 1 ? gruppen[0].id : null
      })
      .catch((e) => (fehler = e.message))
      .finally(() => (laedt = false))
  })

  // Einheiten der gewählten Zielgruppe — nur bei einer Stunde. Ohne Einheiten gleich „neu“.
  $effect(() => {
    const id = gruppeId
    if (!open || !istStunde || !id) {
      einheiten = []
      return
    }
    einheitenLaden = true
    listUnits(id)
      .then((liste) => {
        if (gruppeId !== id) return
        einheiten = liste
        einheitWahl = liste.length ? '' : NEUE_EINHEIT
        // Vorbelegt mit dem Titel der Einheit der Quelle — ohne den Effekt an die Eingabe zu binden.
        untrack(() => {
          if (!liste.length && !neuerTitel) neuerTitel = quelle?.einheitTitel ?? ''
        })
      })
      .catch((e) => (fehler = e.message))
      .finally(() => (einheitenLaden = false))
  })

  async function kopieren() {
    if (!anfrage || laeuft) return
    laeuft = true
    fehler = null
    try {
      ergebnis = istStunde ? await copyLesson(quelle.id, anfrage) : await copyUnit(quelle.id, anfrage)
      onKopiert?.(ergebnis, gruppe)
    } catch (e) {
      fehler = e.message
    } finally {
      laeuft = false
    }
  }

  const feld = 'w-full px-3 py-2 text-sm bg-light-bg-2 dark:bg-dark-bg-2 border border-light-ui-3 ' +
    'dark:border-dark-ui-3 rounded-lg text-light-tx dark:text-dark-tx outline-none ' +
    'focus:border-primary dark:focus:border-primary-dark transition-colors'
  const label = 'block text-xs font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1'
</script>

{#if open}
  <Dialog open {onClose} titelId="kopieren-titel" breite="max-w-md">
    <h2 id="kopieren-titel" class="text-base font-semibold text-light-tx dark:text-dark-tx mb-1">
      {istStunde ? 'Stunde kopieren' : 'Einheit kopieren'}
    </h2>
    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-4 truncate">„{quelle?.titel}“</p>

    {#if ergebnis}
      <SuccessBanner message={istStunde
        ? `Die Stunde liegt jetzt in ${gruppe?.beschriftung ?? 'der Gruppe'}.`
        : `Die Einheit liegt mit ${ergebnis.stunden} ${ergebnis.stunden === 1 ? 'Stunde' : 'Stunden'} in ${gruppe?.beschriftung ?? 'der Gruppe'}, noch ohne Termine.`} />
      {#if ergebnis.meldungen?.length}
        <div class="mt-3">
          <p class="text-sm font-medium text-light-tx dark:text-dark-tx">{meldungenZusammenfassung(ergebnis.meldungen)}</p>
          <ul class="mt-1 space-y-1 text-xs text-light-tx-2 dark:text-dark-tx-2 list-disc pl-4 max-h-48 overflow-y-auto">
            {#each ergebnis.meldungen as m, i (i)}
              <li>{meldungText(m)}</li>
            {/each}
          </ul>
        </div>
      {/if}
      <div class="mt-5 flex justify-end gap-2">
        <button type="button" onclick={onClose}
                class="px-3 py-1.5 text-sm rounded-md text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-bg-2 dark:hover:bg-dark-bg-2">
          Schließen
        </button>
        {#if link}
          <a href={link} onclick={onClose} data-autofocus
             class="px-3 py-1.5 text-sm rounded-md bg-primary dark:bg-primary-dark text-white hover:opacity-90">
            {istStunde ? 'Kopie öffnen' : 'Zum Planer'}
          </a>
        {/if}
      </div>
    {:else if laedt}
      <LoadingBanner message="Gruppen werden geladen …" />
    {:else}
      {#if !gruppen.length}
        <InfoBanner message="Du hast in diesem Schuljahr keine Gruppe desselben Fachs. Kopieren geht nur dorthin." />
      {:else}
        <div class="mb-4">
          <label for="kopieren-gruppe" class={label}>In die Gruppe</label>
          <select id="kopieren-gruppe" bind:value={gruppeId} class={feld}>
            {#if gruppen.length > 1}<option value={null}>— Gruppe wählen —</option>{/if}
            {#each gruppen as g (g.id)}
              <option value={g.id}>{g.beschriftung}</option>
            {/each}
          </select>
        </div>

        {#if istStunde && gruppeId}
          <div class="mb-4">
            <label for="kopieren-einheit" class={label}>In die Einheit</label>
            {#if einheitenLaden}
              <LoadingBanner message="Einheiten werden geladen …" />
            {:else}
              <select id="kopieren-einheit" bind:value={einheitWahl} class={feld}>
                {#if einheiten.length}<option value="">— Einheit wählen —</option>{/if}
                {#each einheiten as e (e.id)}
                  <option value={e.id}>{e.title}</option>
                {/each}
                <option value={NEUE_EINHEIT}>Neue Einheit …</option>
              </select>
              {#if einheitWahl === NEUE_EINHEIT}
                <input type="text" bind:value={neuerTitel} placeholder="Titel der neuen Einheit"
                       aria-label="Titel der neuen Einheit" class="{feld} mt-2" />
              {/if}
              <p class="mt-1 text-xs text-light-tx-2 dark:text-dark-tx-2">
                Die Stunde kommt ans Ende der Einheit, ohne Termin.
              </p>
            {/if}
          </div>
        {:else if !istStunde}
          <p class="mb-4 text-xs text-light-tx-2 dark:text-dark-tx-2">
            Die Einheit kommt mit allen Stunden, die du sehen kannst, in ihrer Reihenfolge — ohne Termine.
            Die Zuordnung machst du danach im Planer.
          </p>
        {/if}
      {/if}

      {#if fehler}
        <div class="mb-3"><ErrorBanner message={fehler} /></div>
      {/if}

      <div class="flex justify-end gap-2">
        <button type="button" onclick={onClose}
                class="px-3 py-1.5 text-sm rounded-md text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-bg-2 dark:hover:bg-dark-bg-2">
          Abbrechen
        </button>
        <button type="button" onclick={kopieren} disabled={!anfrage || laeuft}
                class="px-3 py-1.5 text-sm rounded-md bg-primary dark:bg-primary-dark text-white hover:opacity-90
                       disabled:opacity-50 disabled:cursor-not-allowed">
          {laeuft ? 'Wird kopiert …' : 'Kopieren'}
        </button>
      </div>
    {/if}
  </Dialog>
{/if}
