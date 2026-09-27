<script>
  /**
   * Persönlicher Ausfall eintragen oder zurücknehmen (Paket 7, AP2).
   *
   * ⚠️ **Ersetzt `confirm` und `prompt`.** Die Rückfrage selbst ist nötig — der
   * Tageseintrag trifft Gruppen, die gerade nicht auf dem Bildschirm stehen, und die
   * Rücknahme nimmt auch einzeln gesetzte Ausfälle mit. Aber `prompt` ist keine Eingabe
   * für einen Grund: einzeilig, ungestaltet, im Dunkelmodus fremd.
   *
   * ⚠️ **Die Reichweite ist eine Wahl, keine Vorgabe** (Jan, 24.09.2026): „Wenn eine
   * Lehrkraft Ausfall selbst einträgt, muss sie die Wahl haben, ob das nur die aktuell
   * bearbeitete Gruppe betrifft oder den ganzen Tag." Über das Zeilenmenü gab es bisher
   * nur den ganzen Tag.
   *
   * Die Texte kommen aus `lib/ausfall.js` — sie sind dort geprüft und werden hier nicht
   * neu formuliert.
   */
  import { eintragFrage, ruecknahmeWarnung } from '$lib/ausfall.js'

  const {
    open = false,
    modus = 'eintragen',        // 'eintragen' | 'zuruecknehmen'
    datum = null,               // ISO-Datum der angeklickten Zeile
    gruppenname = '',
    onConfirm,
    onClose,
  } = $props()

  let reichweite = $state('gruppe')
  let notiz = $state('')
  let arbeitet = $state(false)

  const zuruecknehmen = $derived(modus === 'zuruecknehmen')
  const warnung = $derived(zuruecknehmen ? ruecknahmeWarnung(reichweite) : null)

  // Zurücksetzen beim Öffnen: Ein Dialog, der den vorigen Grund noch trägt, trägt ihn
  // sonst versehentlich ein zweites Mal ein.
  $effect(() => {
    if (open) {
      reichweite = 'gruppe'
      notiz = ''
      arbeitet = false
    }
  })

  const datumText = $derived.by(() => {
    if (!datum) return ''
    const [j, m, t] = datum.split('-')
    return `${+t}.${+m}.${j}`
  })

  async function bestaetigen() {
    arbeitet = true
    try {
      await onConfirm({ reichweite, notiz: notiz.trim() || null })
    } finally {
      arbeitet = false
    }
  }

  function onKeydown(e) {
    if (e.key === 'Escape') onClose()
  }
</script>

{#if open}
  <div
    class="fixed inset-0 z-50 bg-black/40 flex items-center justify-center"
    onclick={(e) => { if (e.target === e.currentTarget) onClose() }}
  >
    <div
      class="bg-light-bg dark:bg-dark-bg border border-light-ui-3 dark:border-dark-ui-3 rounded-xl shadow-2xl w-full max-w-md p-6"
      onkeydown={onKeydown}
    >
      <h2 class="text-base font-semibold text-light-tx dark:text-dark-tx mb-1">
        {zuruecknehmen ? 'Ausfall zurücknehmen' : 'Ich falle aus'}
      </h2>
      <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-4">{datumText}</p>

      <fieldset class="mb-4">
        <legend class="block text-xs font-medium text-light-tx-2 dark:text-dark-tx-2 mb-2">
          Was ist betroffen?
        </legend>
        <label class="flex items-start gap-2 mb-2 text-sm text-light-tx dark:text-dark-tx">
          <input type="radio" bind:group={reichweite} value="gruppe" class="mt-0.5" />
          <span>Nur {gruppenname || 'diese Gruppe'}</span>
        </label>
        <label class="flex items-start gap-2 text-sm text-light-tx dark:text-dark-tx">
          <input type="radio" bind:group={reichweite} value="tag" class="mt-0.5" />
          <span>Alle meine Stunden an diesem Tag</span>
        </label>
      </fieldset>

      {#if !zuruecknehmen}
        <p class="text-sm text-light-tx dark:text-dark-tx mb-4">
          {eintragFrage(reichweite, gruppenname)}
        </p>

        <div class="mb-4">
          <label
            for="ausfall-notiz"
            class="block text-xs font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1"
          >
            Grund <span class="font-normal">(optional, erscheint an den Stunden)</span>
          </label>
          <textarea
            id="ausfall-notiz"
            bind:value={notiz}
            rows="2"
            placeholder="z.B. Fortbildung"
            class="w-full px-3 py-2 text-sm bg-light-bg-2 dark:bg-dark-bg-2 border border-light-ui-3 dark:border-dark-ui-3
                   rounded-lg text-light-tx dark:text-dark-tx outline-none focus:border-primary
                   dark:focus:border-primary-dark transition-colors resize-y"
          ></textarea>
        </div>
      {/if}

      {#if warnung}
        <div class="rounded-lg border border-light-ye/40 dark:border-dark-ye/40 bg-light-ye/5 dark:bg-dark-ye/10 p-3 mb-4">
          <p class="text-xs text-light-tx dark:text-dark-tx">{warnung}</p>
        </div>
      {/if}

      <div class="flex justify-end gap-3">
        <button
          onclick={onClose}
          disabled={arbeitet}
          class="px-4 py-2 text-sm rounded-lg text-light-tx-2 dark:text-dark-tx-2
                 hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 transition-colors disabled:opacity-50"
        >
          Abbrechen
        </button>
        <button
          onclick={bestaetigen}
          disabled={arbeitet}
          class="px-4 py-2 text-sm rounded-lg font-medium bg-primary dark:bg-primary-dark text-white
                 hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {arbeitet ? 'Einen Moment…' : zuruecknehmen ? 'Zurücknehmen' : 'Eintragen'}
        </button>
      </div>
    </div>
  </div>
{/if}
