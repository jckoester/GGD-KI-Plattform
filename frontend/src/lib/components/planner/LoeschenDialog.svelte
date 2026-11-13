<script>
  /**
   * Rückfrage vor dem Löschen eines Stundenentwurfs (0.42.4).
   *
   * Ein eigener Dialog statt `confirm`: Die Planungsseite fragt nicht über Browser-Dialoge
   * (Wächter in `ausfall.test.js` — ungestaltet, im Dunkelmodus fremd). Text: `loeschFrage`.
   *
   * Props: `stunde` ({titel, datum?}), `onLoeschen()` — async; wirft es, steht die Meldung im Dialog.
   */
  import Dialog from '$lib/components/Dialog.svelte'
  import ErrorBanner from '$lib/components/ErrorBanner.svelte'
  import { loeschFrage } from '$lib/stunde_loeschen.js'

  const { open = false, stunde = null, onLoeschen, onClose } = $props()

  let laeuft = $state(false)
  let fehler = $state(null)

  $effect(() => {
    if (open) fehler = null
  })

  async function loeschen() {
    if (laeuft) return
    laeuft = true
    fehler = null
    try {
      await onLoeschen()
      onClose()
    } catch (e) {
      fehler = e.message
    } finally {
      laeuft = false
    }
  }
</script>

{#if open}
  <Dialog open {onClose} titelId="loeschen-titel" breite="max-w-md">
    <h2 id="loeschen-titel" class="text-base font-semibold text-light-tx dark:text-dark-tx mb-2">Stunde löschen</h2>
    <p class="text-sm text-light-tx dark:text-dark-tx mb-4">{loeschFrage(stunde?.titel ?? '', stunde?.datum ?? null)}</p>
    {#if fehler}
      <div class="mb-3"><ErrorBanner message={fehler} /></div>
    {/if}
    <div class="flex justify-end gap-2">
      <button type="button" onclick={onClose} data-autofocus
              class="px-3 py-1.5 text-sm rounded-md text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-bg-2 dark:hover:bg-dark-bg-2">
        Abbrechen
      </button>
      <button type="button" onclick={loeschen} disabled={laeuft}
              class="px-3 py-1.5 text-sm rounded-md border border-light-re dark:border-dark-re text-light-re dark:text-dark-re
                     hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 disabled:opacity-50 disabled:cursor-not-allowed">
        {laeuft ? 'Wird gelöscht …' : 'Endgültig löschen'}
      </button>
    </div>
  </Dialog>
{/if}
