<script>
  /**
   * Eine Tageskachel der Startseite — „Heute" oder „Nächster Schultag".
   *
   * ⚠️ **Der leere Zustand ist der häufige.** An den meisten Tagen des Schuljahres ist
   * mindestens eine der beiden Kacheln leer: Wochenende, Ferien, ein Tag ohne eigenen
   * Unterricht. Deshalb steht die Unterscheidung der Gründe in `lib/mein_tag.js` und
   * nicht als Fallunterscheidung hier — sie ist der Inhalt, nicht die Ausnahme.
   */
  import { goto } from "$app/navigation"
  import { CalendarDays, ChevronRight } from "lucide-svelte"
  import {
    einheitHinweis,
    kennzeichen,
    leerFuehrtZurEinrichtung,
    leerSatz,
    stundenVorspann,
    titelAktion,
    titelText,
  } from "$lib/mein_tag.js"
  import { createLessonForSlot } from "$lib/api.js"
  import ErrorBanner from "$lib/components/ErrorBanner.svelte"
  import SubjectIcon from "$lib/components/SubjectIcon.svelte"

  let { titel, tag, lage = {}, leerHinweis = null } = $props()

  const stunden = $derived(tag?.stunden ?? [])

  // Entwurf anlegen und öffnen — derselbe Ablauf wie auf der Gruppenseite
  // (`GruppenUebersicht.entwurfAnlegen`), nur über den Termin statt über die Einheit.
  let legtAn = $state(null)
  let fehler = $state(null)

  // ⚠️ Der Titel bleibt ein echtes `<a>` mit `href` — siehe `titelAktion`. Gibt es noch
  // keinen Entwurf, fängt der Klick ab und kann es besser: anlegen und hineinspringen.
  // Mittelklick und „in neuem Tab öffnen" gehen dann den `href`-Weg in die Jahresplanung.
  async function inDenEntwurf(ereignis, s, aktion) {
    if (!aktion.slotId) return // es gibt einen Entwurf — der Link tut es selbst
    ereignis.preventDefault()
    if (legtAn) return
    legtAn = s.slot_id
    fehler = null
    try {
      const neu = await createLessonForSlot(aktion.slotId)
      await goto(`${aktion.ziel}/lessons/${neu.id}`)
    } catch (e) {
      fehler = e.message ?? "Der Entwurf konnte nicht angelegt werden."
      legtAn = null
    }
  }
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
        {@const hinweis = einheitHinweis(s)}
        {@const aktion = titelAktion(s)}
        <li class="flex items-start gap-2 text-sm">
          <SubjectIcon
            name={s.subject_icon}
            color={s.subject_color}
            size={15}
            class="mt-0.5 shrink-0"
          />
          <span class="min-w-0 flex-1">
            <span class="block text-light-tx dark:text-dark-tx truncate">
              {stundenVorspann(s)} ·
              {#if aktion}
                <a
                  href={aktion.ziel}
                  onclick={(e) => inDenEntwurf(e, s, aktion)}
                  class="underline hover:no-underline"
                >{legtAn === s.slot_id ? "wird angelegt…" : titelText(s)}</a>
              {:else}
                {titelText(s)}
              {/if}
            </span>
            {#if marke || s.anpassung_noetig}
              <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                {#if marke}{marke}{/if}{#if marke && s.anpassung_noetig} · {/if}{#if s.anpassung_noetig}anzupassen{/if}
              </span>
            {/if}
          </span>
          {#if hinweis?.ziel}
            <a
              href={hinweis.ziel}
              class="flex-shrink-0 flex items-center gap-0.5 text-xs underline
                     text-light-tx-2 dark:text-dark-tx-2
                     hover:text-light-tx dark:hover:text-dark-tx"
            >
              {hinweis.text}<ChevronRight size={12} />
            </a>
          {:else if hinweis}
            <span class="flex-shrink-0 text-xs text-light-tx-2 dark:text-dark-tx-2">
              {hinweis.text}
            </span>
          {/if}
        </li>
      {/each}
    </ul>
    {#if fehler}
      <div class="mt-2"><ErrorBanner message={fehler} /></div>
    {/if}
  {:else}
    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
      {leerHinweis ?? leerSatz(tag, lage)}
    </p>
    {#if leerFuehrtZurEinrichtung(lage)}
      <a
        href="/teaching"
        class="mt-2 inline-flex items-center gap-0.5 text-sm underline
               text-light-bl dark:text-dark-bl"
      >
        Unterrichtsgruppen einrichten<ChevronRight size={13} />
      </a>
    {/if}
  {/if}
</section>
