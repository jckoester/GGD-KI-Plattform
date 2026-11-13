<script>
  /**
   * Eine Stunde ohne Termin einplanen (0.42.3, Schritt 3; Plan F1).
   *
   * Zur Wahl stehen Unterrichtstermine ohne Entwurf ab heute — zuerst die der eigenen Einheit,
   * dann leere. Regeln und Anfrage: `lib/einplanen.js`.
   *
   * Props: `groupId`, `stunde` ({id, titel}), `einheitId` (oder null), `onEingeplant(slot)`.
   */
  import Dialog from '$lib/components/Dialog.svelte'
  import ErrorBanner from '$lib/components/ErrorBanner.svelte'
  import InfoBanner from '$lib/components/InfoBanner.svelte'
  import LoadingBanner from '$lib/components/LoadingBanner.svelte'
  import { getPlanningOverview, updateSlot } from '$lib/api.js'
  import { einplanAnfrage, einplanbareTermine, heuteIso, terminText } from '$lib/einplanen.js'

  const { open = false, groupId, stunde = null, einheitId = null, onClose, onEingeplant = null } = $props()

  let slots = $state([])
  let laedt = $state(false)
  let fehler = $state(null)
  let wahl = $state(null)
  let laeuft = $state(false)

  const termine = $derived(einplanbareTermine(slots, einheitId, heuteIso()))
  const alle = $derived([...termine.eigene, ...termine.freie])

  function ladeTermine() {
    wahl = null
    laedt = true
    return getPlanningOverview(groupId)
      .then((d) => (slots = d.slots ?? []))
      .catch((e) => (fehler = e.message))
      .finally(() => (laedt = false))
  }

  // Beim Öffnen frisch laden — der Plan kann sich seit dem Öffnen der Seite geändert haben.
  $effect(() => {
    if (!open) return
    fehler = null
    ladeTermine()
  })

  async function einplanen() {
    const slot = alle.find((s) => s.id === wahl)
    if (!slot || laeuft) return
    laeuft = true
    fehler = null
    try {
      const neu = await updateSlot(slot.id, einplanAnfrage(slot, stunde, einheitId))
      onEingeplant?.(neu)
      onClose()
    } catch (e) {
      if (e.detail?.grund === 'veraltet') {
        // Jemand hat den Termin inzwischen belegt oder geändert: frische Liste statt Rätsel.
        fehler = 'Dieser Termin hat sich inzwischen geändert. Die Liste ist neu geladen — wähl bitte noch einmal.'
        await ladeTermine()
      } else {
        fehler = e.message
      }
    } finally {
      laeuft = false
    }
  }

  const gruppenTitel = 'text-xs font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1'
  const option = 'flex items-center gap-2 px-3 py-1.5 text-sm rounded-md cursor-pointer text-light-tx dark:text-dark-tx ' +
    'hover:bg-light-bg-2 dark:hover:bg-dark-bg-2'
</script>

{#snippet auswahl(liste)}
  <div class="space-y-0.5">
    {#each liste as s (s.id)}
      <label class={option}>
        <input type="radio" name="einplanen-termin" value={s.id} bind:group={wahl} />
        <span>{terminText(s)}</span>
      </label>
    {/each}
  </div>
{/snippet}

{#if open}
  <Dialog open {onClose} titelId="einplanen-titel" breite="max-w-md">
    <h2 id="einplanen-titel" class="text-base font-semibold text-light-tx dark:text-dark-tx mb-1">Stunde einplanen</h2>
    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-4 truncate">„{stunde?.titel}“</p>

    {#if laedt}
      <LoadingBanner message="Termine werden geladen …" />
    {:else}
      {#if !alle.length && !fehler}
        <InfoBanner message="Es gibt ab heute keinen freien Termin. Gib in der Jahresübersicht einen Termin frei oder leg die Stunde über das Wochenmuster an." />
      {:else}
        <div class="max-h-72 overflow-y-auto space-y-3 mb-4">
          {#if termine.eigene.length}
            <div>
              <p class={gruppenTitel}>Termine dieser Einheit</p>
              {@render auswahl(termine.eigene)}
            </div>
          {/if}
          {#if termine.freie.length}
            <div>
              <p class={gruppenTitel}>Freie Termine</p>
              {@render auswahl(termine.freie)}
            </div>
          {/if}
        </div>
      {/if}

      {#if fehler}
        <div class="mb-3"><ErrorBanner message={fehler} /></div>
      {/if}

      <div class="flex justify-end gap-2">
        <button type="button" onclick={onClose}
                class="px-3 py-1.5 text-sm rounded-md text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-bg-2 dark:hover:bg-dark-bg-2">
          Abbrechen
        </button>
        <button type="button" onclick={einplanen} disabled={!wahl || laeuft}
                class="px-3 py-1.5 text-sm rounded-md bg-primary dark:bg-primary-dark text-white hover:opacity-90
                       disabled:opacity-50 disabled:cursor-not-allowed">
          {laeuft ? 'Wird eingeplant …' : 'Einplanen'}
        </button>
      </div>
    {/if}
  </Dialog>
{/if}
