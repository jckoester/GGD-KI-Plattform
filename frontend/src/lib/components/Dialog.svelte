<script>
  /**
   * Rahmen eines modalen Dialogs (0.21, Päckchen H) — Hintergrund, Rolle, Escape, Fokus.
   *
   * Bis dahin baute jeder Dialog seinen Rahmen selbst, mit unterschiedlichem Stand:
   * `UnitDialog` und `AusfallDialog` hatten Rolle und Escape, `PatternEditor` keins von beiden,
   * und **keiner** führte den Fokus — er blieb auf der Seite darunter, Tab lief aus dem Dialog
   * hinaus, und nach dem Schließen stand er am Seitenanfang. Was hier geschieht:
   *
   * - `role="dialog"`, `aria-modal`, `aria-labelledby` (die Überschrift trägt `titelId`);
   * - **Fokus hinein** beim Öffnen: ein Element mit `data-autofocus`, sonst das erste
   *   Eingabefeld, sonst das erste bedienbare Element, sonst der Rahmen selbst;
   * - **Fokus bleibt drin**: Tab und Umschalt+Tab laufen am Ende bzw. Anfang im Kreis;
   * - **Escape schließt**, ein Klick auf den Hintergrund ebenso;
   * - **Fokus zurück** beim Schließen auf das Element, das ihn vorher hatte (meist der Knopf,
   *   der den Dialog geöffnet hat). Gibt es das nicht mehr — etwa einen Menüpunkt, dessen
   *   Menü beim Öffnen zugeklappt ist —, auf das, was `fokusZurueck()` liefert.
   *
   * `onkeydown` bekommt alle übrigen Tasten (etwa Enter = Speichern im `UnitDialog`).
   */
  import { tick } from 'svelte'

  const {
    open = false,
    onClose,
    titelId,
    breite = 'max-w-md',
    onkeydown = null,
    fokusZurueck = null,
    children,
  } = $props()

  let rahmen = $state(null)

  const BEDIENBAR = [
    'a[href]', 'button:not([disabled])', 'input:not([disabled]):not([type="hidden"])',
    'select:not([disabled])', 'textarea:not([disabled])', '[tabindex]:not([tabindex="-1"])',
  ].join(',')

  function bedienbare() {
    return rahmen ? [...rahmen.querySelectorAll(BEDIENBAR)].filter((e) => e.offsetParent !== null || e === document.activeElement) : []
  }

  $effect(() => {
    if (!open) return
    const vorher = document.activeElement
    tick().then(() => {
      if (!rahmen) return
      const ziel =
        rahmen.querySelector('[data-autofocus]') ??
        bedienbare().find((e) => e.matches('input, select, textarea')) ??
        bedienbare()[0] ??
        rahmen
      ziel.focus()
    })
    return () => {
      // `body` heißt: Beim Öffnen hatte schon niemand mehr den Fokus (der Menüpunkt war weg).
      const da = vorher instanceof HTMLElement && vorher !== document.body && vorher.isConnected
      const ziel = da ? vorher : fokusZurueck?.()
      ziel?.focus?.()
    }
  })

  function tasten(e) {
    if (e.key === 'Escape') {
      e.stopPropagation()
      onClose?.()
      return
    }
    if (e.key === 'Tab') {
      const liste = bedienbare()
      if (!liste.length) {
        e.preventDefault()
        return
      }
      const erstes = liste[0]
      const letztes = liste.at(-1)
      if (e.shiftKey && (document.activeElement === erstes || document.activeElement === rahmen)) {
        e.preventDefault()
        letztes.focus()
      } else if (!e.shiftKey && document.activeElement === letztes) {
        e.preventDefault()
        erstes.focus()
      }
      return
    }
    onkeydown?.(e)
  }
</script>

{#if open}
  <!-- Klick daneben schließt (Maus); per Tastatur Escape oder die Knöpfe. -->
  <div
    role="presentation"
    class="fixed inset-0 z-50 bg-black/40 flex items-center justify-center"
    onclick={(e) => { if (e.target === e.currentTarget) onClose?.() }}
  >
    <div
      bind:this={rahmen}
      class="bg-light-bg dark:bg-dark-bg border border-light-ui-3 dark:border-dark-ui-3 rounded-xl shadow-2xl w-full {breite} p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titelId}
      tabindex="-1"
      onkeydown={tasten}
    >
      {@render children?.()}
    </div>
  </div>
{/if}
