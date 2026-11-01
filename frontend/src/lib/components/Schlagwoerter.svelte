<script>
  /**
   * Schlagwörter einer Assistentenkarte (0.26, F37 a): Fachnamen statt Slugs, höchstens drei,
   * der Rest als „+n“ mit Tooltip.
   */
  import { schlagwoerterAnzeige } from '$lib/assistentenliste.js'
  import { subjects } from '$lib/stores/subjects.js'
  import { BADGE } from '$lib/badges.js'

  let { tags = [] } = $props()

  const anzeige = $derived(schlagwoerterAnzeige(tags, $subjects))
</script>

{#if anzeige.namen.length > 0}
  <div class="flex flex-wrap gap-1 mt-2">
    {#each anzeige.namen as name (name)}
      <span class={BADGE}>{name}</span>
    {/each}
    {#if anzeige.mehr.length > 0}
      <span class={BADGE} title={anzeige.mehr.join(', ')}>+{anzeige.mehr.length}</span>
    {/if}
  </div>
{/if}
