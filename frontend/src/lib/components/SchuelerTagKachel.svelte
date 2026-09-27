<script>
  /**
   * Der Unterrichtstag aus Schüler:innen-Sicht.
   *
   * ⚠️ **Eine eigene Komponente, keine Variante von `TagesKachel`.** Die Daten haben
   * eine andere Form (`faecher` statt `stunden`, kein Thema, keine Einheit, kein
   * Entwurf) — und das ist Absicht: Die Vorbereitung der Lehrkraft gehört ihr
   * (`docs/user/datenschutz.md`). Eine gemeinsame Komponente mit Rollen-Weichen wäre
   * genau die Stelle, an der später eine Weiche vergessen wird.
   */
  import { CalendarDays } from "lucide-svelte"
  import { fachLink, schuelerLeerSatz } from "$lib/mein_tag.js"
  import SubjectIcon from "$lib/components/SubjectIcon.svelte"

  let { titel, tag, hatGruppen = false } = $props()

  const faecher = $derived(tag?.faecher ?? [])
</script>

<section class="rounded-lg border border-light-ui-3 dark:border-dark-ui-3 p-4">
  <h2 class="flex items-center gap-2 text-sm font-semibold text-light-tx dark:text-dark-tx mb-3">
    <CalendarDays size={16} class="text-light-tx-2 dark:text-dark-tx-2" />
    {titel}
  </h2>

  {#if faecher.length}
    <ul class="flex flex-col gap-1.5">
      {#each faecher as f, i (`${f.group_id}-${f.start_period}-${i}`)}
        {@const ziel = fachLink(f)}
        <li class="flex items-start gap-2 text-sm">
          <SubjectIcon
            name={f.subject_icon}
            color={f.subject_color}
            size={15}
            class="mt-0.5 shrink-0"
          />
          <span class="min-w-0 flex-1 truncate text-light-tx dark:text-dark-tx">
            {f.stunde} ·
            {#if ziel}
              <a href={ziel} class="underline hover:no-underline">{f.fach}</a>
            {:else}
              {f.fach}
            {/if}
          </span>
          {#if f.hinweis}
            <span class="flex-shrink-0 text-xs text-light-tx-2 dark:text-dark-tx-2">
              {f.hinweis}
            </span>
          {/if}
        </li>
      {/each}
    </ul>
  {:else}
    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
      {schuelerLeerSatz(tag, hatGruppen)}
    </p>
  {/if}
</section>
