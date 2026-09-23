<script>
  /**
   * „Meine Unterrichtsgruppen" auf der Startseite.
   *
   * ⚠️ **Hier wird nichts angelegt.** Offene Stundenplan-Vorschläge und
   * Schulkonto-Angebote werden **gezählt** und verlinkt — die Anlege-Oberfläche steht
   * auf `/profile/teaching-groups` und ist dort vollständig. Sie hier zu wiederholen
   * ergäbe einen dritten Ort, an dem man Gruppen anlegt, und drei Orte heißt: zwei
   * veralten.
   */
  import { Users, ChevronRight } from "lucide-svelte"
  import { myTeachingGroups } from "$lib/stores/myGroups.js"
  import { potentialTeachingGroups } from "$lib/stores/potentialTeachingGroups.js"
  import { getGroupOffers } from "$lib/api.js"
  import { offeneEntscheidungen } from "$lib/mein_tag.js"

  let angebote = $state(0)

  const aktuelle = $derived($myTeachingGroups.filter((g) => g.aktuell !== false))
  const offen = $derived(offeneEntscheidungen($potentialTeachingGroups.length, angebote))

  $effect(() => {
    getGroupOffers()
      .then((d) => (angebote = (d?.angebote ?? []).filter((a) => !a.ignoriert).length))
      .catch(() => (angebote = 0))
  })
</script>

<section class="rounded-lg border border-light-ui-3 dark:border-dark-ui-3 p-4">
  <h2 class="flex items-center gap-2 text-sm font-semibold text-light-tx dark:text-dark-tx mb-3">
    <Users size={16} class="text-light-tx-2 dark:text-dark-tx-2" />
    Meine Unterrichtsgruppen
  </h2>

  {#if aktuelle.length}
    <ul class="flex flex-wrap gap-1.5">
      {#each aktuelle as g (g.id)}
        <li>
          <a
            href={`/subjects/${g.slug ?? ''}`}
            class="inline-block rounded-md border border-light-ui-3 dark:border-dark-ui-3
                   px-2 py-1 text-xs text-light-tx dark:text-dark-tx
                   hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
          >
            {g.name}
          </a>
        </li>
      {/each}
    </ul>
  {:else}
    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
      Noch keine Unterrichtsgruppen.
    </p>
  {/if}

  {#if offen}
    <a
      href="/profile/teaching-groups"
      class="mt-3 inline-flex items-center gap-0.5 text-sm underline
             text-light-bl dark:text-dark-bl"
    >
      {offen}<ChevronRight size={13} />
    </a>
  {/if}
</section>
