<script>
  /**
   * UP-6 Schritt 8: Hinweisleiste für Überhang-Befunde.
   * Sticky unten in der Planner-Seite; je Befund Deep-Link in den Verschiebe-Dialog
   * (Chat mit Gruppenbezug + vorbefülltem Prompt). Dismiss pro Befund (Session).
   */
  import { goto } from '$app/navigation'

  let { findings = [], groupId } = $props()

  let dismissed = $state(new Set())
  const visible = $derived(findings.filter((f) => !dismissed.has(f.ue_node_id)))

  function fmtDate(iso) {
    if (!iso) return ''
    const [, m, d] = iso.split('-')
    return `${+d}.${+m}.`
  }

  function befundText(f) {
    const ka = f.fixpunkt_datum ? ` bis zur Klassenarbeit am ${fmtDate(f.fixpunkt_datum)}` : ''
    const std = `${f.ueberhang} Stunde${f.ueberhang === 1 ? '' : 'n'} Überhang`
    return `UE „${f.titel}" hat ${std}${ka}.`
  }

  function open(f, apply) {
    let p = `${befundText(f)} Bitte schlage vor, wie ich kürzen oder umverteilen kann.`
    if (apply) p += ' Wende deinen Vorschlag direkt an.'
    goto(`/chat?group_id=${groupId}&q=${encodeURIComponent(p)}`)
  }

  function dismiss(id) {
    dismissed = new Set([...dismissed, id])
  }
</script>

{#if visible.length > 0}
  <div class="flex-shrink-0 border-t border-light-ui-3 dark:border-dark-ui-3 bg-light-bg-2 dark:bg-dark-bg-2">
    {#each visible as f (f.ue_node_id)}
      <div class="flex items-center gap-3 px-4 py-2 text-sm">
        <span class="text-light-or dark:text-dark-or flex-shrink-0" aria-hidden="true">⚠</span>
        <span class="flex-1 min-w-0 text-light-tx dark:text-dark-tx truncate">
          {befundText(f)}
        </span>
        <button
          onclick={() => open(f, false)}
          class="flex-shrink-0 px-2.5 py-1 text-xs rounded-md border border-light-ui-3 dark:border-dark-ui-3
                 text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-bg dark:hover:bg-dark-bg transition-colors"
        >Vorschlag zeigen</button>
        <button
          onclick={() => open(f, true)}
          class="flex-shrink-0 px-2.5 py-1 text-xs rounded-md bg-primary dark:bg-primary-dark
                 text-white font-medium hover:opacity-90 transition-opacity"
        >Übernehmen</button>
        <button
          onclick={() => dismiss(f.ue_node_id)}
          aria-label="Hinweis ausblenden"
          class="flex-shrink-0 text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx"
        >✕</button>
      </div>
    {/each}
  </div>
{/if}
