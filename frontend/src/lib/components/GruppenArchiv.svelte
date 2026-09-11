<script>
  /**
   * Die Unterrichtsgruppen vergangener Schuljahre.
   *
   * **Warum es das gibt.** `sync_groups` arbeitet als *Immediate Mirror*: Beim Login
   * fallen alle Mitgliedschaften, die nicht mehr im Schulkonto stehen. Mit dem neuen
   * Schuljahr verschwinden die alten Gruppen also von selbst — und mit ihnen
   * Jahrespläne, Stundenentwürfe und Chats, die weiter in der Datenbank liegen. Sie
   * sind nicht gelöscht, sie sind unerreichbar.
   *
   * **Was hier möglich ist und was nicht.** Der Zugang hängt am eigenen Inhalt, nicht
   * an einer wiederbelebten Mitgliedschaft — die gäbe auch wieder Lesezugriff auf
   * *fremdes* gruppen-freigegebenes Material. Erreichbar sind deshalb die eigenen
   * Chats und die eigenen Bausteine. Die **Jahresplanung** einer früheren Gruppe
   * (Stundenraster, Bilanz) ist es nicht: Ihre Endpunkte verlangen eine aktuelle
   * Mitgliedschaft, und die Slots gehören der Gruppe, nicht einer Person.
   */
  import { getFormerGroups, getConversations, getContextNodes } from '$lib/api.js'
  import { subjectMap } from '$lib/stores/subjects.js'
  import ErrorBanner from './ErrorBanner.svelte'
  import NodeTypeIcon from './NodeTypeIcon.svelte'
  import { Archive, ChevronDown, ChevronRight } from 'lucide-svelte'

  let { subjectId = null } = $props()

  let gruppen = $state([])
  let laedt = $state(true)
  let fehler = $state(null)

  // Aufgeklappte Gruppen samt ihrem Inhalt. Aufgeklappt wird einzeln geladen:
  // Die Übersicht braucht nur Zahlen, und wer alles vorlädt, lädt meistens umsonst.
  let offen = $state(new Set())
  let inhalt = $state({})

  async function umschalten(gruppe) {
    const id = gruppe.group_id
    const neu = new Set(offen)
    if (neu.has(id)) {
      neu.delete(id)
      offen = neu
      return
    }
    neu.add(id)
    offen = neu
    if (inhalt[id]) return

    inhalt = { ...inhalt, [id]: { laedt: true, chats: [], bausteine: [] } }
    try {
      // Beide Abfragen nebeneinander — die eine wartet nicht auf die andere.
      const [chats, bausteine] = await Promise.all([
        gruppe.chats > 0
          ? getConversations({ groupId: id, limit: 25 }).then((d) => d.items ?? [])
          : Promise.resolve([]),
        gruppe.bausteine > 0
          ? getContextNodes({ group_id: id, owner: 'me', limit: 50 })
          : Promise.resolve([]),
      ])
      inhalt = { ...inhalt, [id]: { laedt: false, chats, bausteine } }
    } catch (e) {
      inhalt = {
        ...inhalt,
        [id]: { laedt: false, chats: [], bausteine: [], fehler: e.message },
      }
    }
  }

  $effect(() => {
    const fach = subjectId
    laedt = true
    getFormerGroups(fach)
      .then((daten) => {
        gruppen = daten.items ?? []
        fehler = null
      })
      .catch((e) => {
        fehler = e.message ?? 'Das Archiv konnte nicht geladen werden.'
      })
      .finally(() => {
        laedt = false
      })
  })

  function zahl(n, eins, viele) {
    return `${n} ${n === 1 ? eins : viele}`
  }
</script>

{#if fehler}
  <ErrorBanner message={fehler} />
{:else if laedt}
  <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 py-4">Wird geladen…</p>
{:else if gruppen.length === 0}
  <div class="py-8 text-center text-light-tx-2 dark:text-dark-tx-2">
    <Archive size={24} class="mx-auto mb-2 opacity-60" />
    <p class="text-sm max-w-md mx-auto">
      Hier erscheinen Unterrichtsgruppen vergangener Schuljahre, sobald es welche
      gibt — mit den Chats und Bausteinen, die du darin angelegt hast.
    </p>
  </div>
{:else}
  <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-4">
    Gruppen aus vergangenen Schuljahren. Du siehst hier, was dir gehört: deine Chats
    und deine Bausteine. Die Jahresplanung dieser Gruppen ist nicht mehr aufrufbar.
  </p>
  <div class="flex flex-col gap-3">
    {#each gruppen as gruppe (gruppe.group_id)}
      {@const zu = !offen.has(gruppe.group_id)}
      {@const dabei = inhalt[gruppe.group_id]}
      <section class="rounded-lg border border-light-ui-3 dark:border-dark-ui-3 overflow-hidden">
        <!-- Aufgeklappt wird in der Seite, nicht über einen Filter-Link: Weder
             `/history` noch `/knowledge` nehmen eine Gruppe aus der Adresszeile
             entgegen — ein solcher Link zeigte wortlos die ungefilterte Liste. -->
        <button
          onclick={() => umschalten(gruppe)}
          aria-expanded={!zu}
          class="w-full flex items-center gap-2 px-4 py-3 text-left
                 bg-light-bg-2 dark:bg-dark-bg-2
                 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
        >
          {#if zu}
            <ChevronRight size={16} class="text-light-tx-2 dark:text-dark-tx-2 shrink-0" />
          {:else}
            <ChevronDown size={16} class="text-light-tx-2 dark:text-dark-tx-2 shrink-0" />
          {/if}
          <span class="font-medium text-sm text-light-tx dark:text-dark-tx truncate">
            {gruppe.name}
          </span>
          <span class="flex-1"></span>
          <span class="text-xs text-light-tx-2 dark:text-dark-tx-2 shrink-0">
            {#if gruppe.chats > 0}{zahl(gruppe.chats, 'Chat', 'Chats')}{/if}
            {#if gruppe.chats > 0 && gruppe.bausteine > 0}&nbsp;·&nbsp;{/if}
            {#if gruppe.bausteine > 0}{zahl(gruppe.bausteine, 'Baustein', 'Bausteine')}{/if}
          </span>
          <span class="text-xs text-light-tx-2 dark:text-dark-tx-2 shrink-0 w-20 text-right">
            {#if gruppe.schuljahr}
              {gruppe.schuljahr}
            {:else if gruppe.subject_id != null && $subjectMap[gruppe.subject_id]}
              {$subjectMap[gruppe.subject_id].name}
            {/if}
          </span>
        </button>

        {#if !zu}
          <div class="border-t border-light-ui-2 dark:border-dark-ui-2">
            {#if dabei?.laedt}
              <p class="px-4 py-3 text-sm text-light-tx-2 dark:text-dark-tx-2">Wird geladen…</p>
            {:else if dabei?.fehler}
              <div class="px-4 py-3"><ErrorBanner message={dabei.fehler} /></div>
            {:else}
              {#each dabei?.bausteine ?? [] as knoten (knoten.id)}
                <!-- Ein Stundenentwurf öffnet im Planer (seit 09/2026 auch ohne
                     Mitgliedschaft lesbar) — dort steht der Verlaufsplan. Alles
                     andere in der Knotenansicht. -->
                {@const ziel =
                  knoten.content_type === 'unterrichtsstunde'
                    ? `/subjects/${$subjectMap[knoten.subject_id]?.slug ?? ''}/groups/${gruppe.group_id}/planner/lessons/${knoten.id}`
                    : `/knowledge/${knoten.id}`}
                <a
                  href={ziel}
                  class="flex items-center gap-2 px-4 py-2 text-sm
                         border-b last:border-b-0 border-light-ui-2 dark:border-dark-ui-2
                         text-light-tx dark:text-dark-tx
                         hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                >
                  <NodeTypeIcon contentType={knoten.content_type} size={14} />
                  <span class="flex-1 min-w-0 truncate">{knoten.title}</span>
                </a>
              {/each}
              {#each dabei?.chats ?? [] as chat (chat.id)}
                <a
                  href="/chat?id={chat.id}"
                  class="flex items-center gap-2 px-4 py-2 text-sm
                         border-b last:border-b-0 border-light-ui-2 dark:border-dark-ui-2
                         text-light-tx dark:text-dark-tx
                         hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                >
                  <span class="flex-1 min-w-0 truncate">
                    {chat.title ?? 'Unbenannter Chat'}
                  </span>
                </a>
              {/each}
              {#if (dabei?.bausteine?.length ?? 0) === 0 && (dabei?.chats?.length ?? 0) === 0}
                <p class="px-4 py-3 text-sm text-light-tx-2 dark:text-dark-tx-2">
                  Nichts Eigenes mehr in dieser Gruppe.
                </p>
              {/if}
            {/if}
          </div>
        {/if}
      </section>
    {/each}
  </div>
{/if}
