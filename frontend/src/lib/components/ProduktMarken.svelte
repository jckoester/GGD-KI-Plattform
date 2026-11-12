<script>
  // Marken „erstellt Bilder“, „plant Stunden“ … an einer Assistentenkarte (0.40, Päckchen AM).
  // Die Arten lädt die Komponente selbst (einmal je Sitzung, `ladeProduktarten`) — so braucht
  // keine Seite, die Karten zeigt, etwas weiterzureichen.
  import { onMount } from 'svelte'
  import { Wrench } from 'lucide-svelte'
  import { BADGE } from '$lib/badges.js'
  import { markenVon } from '$lib/assistentenliste.js'
  import { ladeProduktarten } from '$lib/produktarten.js'

  let { assistant } = $props()
  let arten = $state([])
  const marken = $derived(markenVon(assistant, arten))

  onMount(async () => {
    if ((assistant?.produces ?? []).length) arten = await ladeProduktarten()
  })
</script>

{#each marken as marke (marke)}
  <span class="{BADGE} inline-flex items-center gap-1 shrink-0" title="Werkzeug: {marke}">
    <Wrench size={11} aria-hidden="true" />{marke}
  </span>
{/each}
