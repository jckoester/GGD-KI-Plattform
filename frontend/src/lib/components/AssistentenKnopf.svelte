<script>
  /**
   * Der geteilte Knopf zum Assistenten eines Einstiegs (0.15, Plan F7).
   *
   * Der Hauptteil öffnet den ersten Kandidaten, der Pfeil daneben klappt alle aus — nur,
   * wenn es mehr als einen gibt. Die Reihenfolge liefert `passendeAssistenten`
   * (`$lib/assistentenwahl.js`); gemerkt wird nichts.
   *
   * Ohne Kandidaten bleibt der Hauptteil bedienbar und meldet `null`: Der Einstieg öffnet
   * dann den Chat, und die Chatseite sagt, dass kein passender Assistent eingerichtet ist —
   * statt dass der Knopf stillschweigend fehlt.
   *
   * `kompakt` ist die Fassung für eine Zeile der Startseite: nur das Symbol. Dort gibt es
   * **keinen geteilten Knopf** (Jan, 09.10.2026): Auf dem Telefon traf man statt des kleinen
   * Pfeils den Hauptteil und landete ungefragt beim ersten Assistenten. Ab zwei Kandidaten
   * öffnet die ganze Fläche deshalb immer das Menü; mit einem öffnet sie ihn direkt — ein
   * Menü mit einem Eintrag wäre nur ein Tipp mehr.
   */
  import { Bot, ChevronDown } from 'lucide-svelte'

  let {
    kandidaten = [],
    onwaehle,
    beschriftung = 'Assistent',
    kompakt = false,
    beschaeftigt = false,
  } = $props()

  let offen = $state(false)
  let wurzel = $state(null)

  const erster = $derived(kandidaten[0] ?? null)
  const nurMenue = $derived(kompakt && kandidaten.length > 1)
  const titel = $derived(erster ? `Mit „${erster.name}“ öffnen` : 'Assistent öffnen')

  function waehle(assistent) {
    offen = false
    onwaehle?.(assistent)
  }

  function aussen(ereignis) {
    if (offen && wurzel && !wurzel.contains(ereignis.target)) offen = false
  }

  function taste(ereignis) {
    if (offen && ereignis.key === 'Escape') offen = false
  }

  const voll = 'h-8 inline-flex items-center gap-1.5 text-sm font-medium text-white bg-primary dark:bg-primary-dark hover:opacity-90 transition-opacity disabled:opacity-60'
  const klein = 'inline-flex items-center text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx disabled:opacity-60'
  // Eine Trefferfläche, die sich auf dem Telefon treffen lässt — der negative Rand hält die
  // Zeile so hoch wie ihr Text.
  const flaeche = 'h-8 min-w-8 justify-center -my-1.5 rounded-md'
</script>

<svelte:window onclick={aussen} onkeydown={taste} />

<div bind:this={wurzel} class="relative inline-flex">
  {#if nurMenue}
    <button
      type="button"
      onclick={() => (offen = !offen)}
      disabled={beschaeftigt}
      aria-haspopup="menu"
      aria-expanded={offen}
      aria-label="Assistent wählen"
      title="Assistent wählen"
      class="{klein} {flaeche} gap-0.5"
    >
      <Bot size={15} aria-hidden="true" />
      <ChevronDown size={12} aria-hidden="true" />
    </button>
  {:else}
    <button
      type="button"
      onclick={() => waehle(erster)}
      disabled={beschaeftigt}
      title={titel}
      aria-label={kompakt ? titel : undefined}
      class="{kompakt ? `${klein} ${flaeche}` : `${voll} px-3`}
             {kandidaten.length > 1 ? 'rounded-l-md' : 'rounded-md'}"
    >
      <Bot size={kompakt ? 15 : 14} aria-hidden="true" />
      {#if !kompakt}{beschriftung}{/if}
    </button>
    {#if kandidaten.length > 1}
      <button
        type="button"
        onclick={() => (offen = !offen)}
        disabled={beschaeftigt}
        aria-haspopup="menu"
        aria-expanded={offen}
        aria-label="Anderen Assistenten wählen"
        title="Anderen Assistenten wählen"
        class="{voll} px-1.5 rounded-r-md border-l border-white/30"
      >
        <ChevronDown size={14} aria-hidden="true" />
      </button>
    {/if}
  {/if}
  {#if offen}
    <ul
      role="menu"
      class="absolute right-0 top-full mt-1 z-20 min-w-48 py-1 rounded-md shadow-lg
             border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg"
    >
      {#each kandidaten as assistent (assistent.id)}
        <li role="none">
          <button
            type="button"
            role="menuitem"
            onclick={() => waehle(assistent)}
            class="w-full text-left px-3 {kompakt ? 'py-2.5' : 'py-1.5'} text-sm
                   text-light-tx dark:text-dark-tx hover:bg-light-bg-2 dark:hover:bg-dark-bg-2"
          >
            {assistent.name}
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</div>
