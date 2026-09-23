<script>
  /**
   * Eine Tageskachel der Startseite — „Heute" oder „Nächster Schultag".
   *
   * ⚠️ **Der leere Zustand ist der häufige.** An den meisten Tagen des Schuljahres ist
   * mindestens eine der beiden Kacheln leer: Wochenende, Ferien, ein Tag ohne eigenen
   * Unterricht. Deshalb steht die Unterscheidung der Gründe in `lib/mein_tag.js` und
   * nicht als Fallunterscheidung hier — sie ist der Inhalt, nicht die Ausnahme.
   */
  import { CalendarDays, ChevronRight } from "lucide-svelte"
  import {
    kennzeichen,
    leerFuehrtZurEinrichtung,
    leerSatz,
    naechsterSchritt,
    plannerLink,
    stundenZeile,
  } from "$lib/mein_tag.js"

  let { titel, tag, lage = {}, leerHinweis = null } = $props()

  const stunden = $derived(tag?.stunden ?? [])
</script>

<section class="rounded-lg border border-light-ui-3 dark:border-dark-ui-3 p-4">
  <h2 class="flex items-center gap-2 text-sm font-semibold text-light-tx dark:text-dark-tx mb-3">
    <CalendarDays size={16} class="text-light-tx-2 dark:text-dark-tx-2" />
    {titel}
  </h2>

  {#if stunden.length}
    <ul class="flex flex-col gap-1.5">
      {#each stunden as s (s.slot_id)}
        {@const marke = kennzeichen(s)}
        {@const schritt = naechsterSchritt(s)}
        {@const ziel = plannerLink(s)}
        <li class="flex items-start justify-between gap-3 text-sm">
          <span class="min-w-0 flex-1">
            <span class="block text-light-tx dark:text-dark-tx truncate">
              {stundenZeile(s)}
            </span>
            {#if marke || s.anpassung_noetig}
              <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                {#if marke}{marke}{/if}{#if marke && s.anpassung_noetig} · {/if}{#if s.anpassung_noetig}anzupassen{/if}
              </span>
            {/if}
          </span>
          {#if schritt.moeglich && ziel}
            <a
              href={ziel}
              class="flex-shrink-0 flex items-center gap-0.5 text-xs underline
                     text-light-tx-2 dark:text-dark-tx-2
                     hover:text-light-tx dark:hover:text-dark-tx"
            >
              {schritt.text}<ChevronRight size={12} />
            </a>
          {:else}
            <span class="flex-shrink-0 text-xs text-light-tx-2 dark:text-dark-tx-2">
              {schritt.text}
            </span>
          {/if}
        </li>
      {/each}
    </ul>
  {:else}
    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
      {leerHinweis ?? leerSatz(tag, lage)}
    </p>
    {#if leerFuehrtZurEinrichtung(lage)}
      <a
        href="/profile/teaching-groups"
        class="mt-2 inline-flex items-center gap-0.5 text-sm underline
               text-light-bl dark:text-dark-bl"
      >
        Unterrichtsgruppen einrichten<ChevronRight size={13} />
      </a>
    {/if}
  {/if}
</section>
