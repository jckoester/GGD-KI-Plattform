<script>
  /**
   * Die Übersicht einer Unterrichtsgruppe — für **beide** Rollen dieselbe Seite.
   *
   * **Warum eine Komponente.** Was eine Schüler:in „mein Fach Mathematik" nennt, ist im
   * Datenmodell die Unterrichtsgruppe — genau das, was die Lehrkraft „Klasse 8c" nennt.
   * Die Rollen sehen denselben Gegenstand aus zwei Richtungen. Zwei Seiten dafür
   * bedeuteten zwei Wahrheiten darüber, was „die Gruppe" enthält; eine davon wäre
   * irgendwann die falsche.
   *
   * ⚠️ **Nicht `exclude_groups` mitschleppen.** Die alte Schüler-Fachseite fragte ihre
   * Chats mit diesem Parameter ab — serverseitig `group_id IS NULL`. Schülerchats tragen
   * aber **immer** eine `group_id` (der Fach-Wähler bietet ihnen nur Gruppen an), der
   * Abschnitt war damit strukturell leer. Richtig ist der Parameter allein auf der
   * Lehrkraft-Fachseite, wo es persönliche Fach-Chats ohne Gruppe tatsächlich gibt.
   *
   * Leitfrage der Seite: „Wo war ich stehengeblieben?" Daher die Reihenfolge
   * Jetzt → Weiterarbeiten → Assistenten → Zuletzt entstanden → Nachschlagen.
   * Die Abschnitte „Jetzt" (AP5) und „Zuletzt entstanden" (AP7) sind noch leer —
   * bewusst ohne Platzhaltertext: Ein Kasten, der eine spätere Phase ankündigt, ist
   * genau das, was diese Seite loswerden soll.
   */
  import { goto } from '$app/navigation'
  import { getConversations } from '$lib/api.js'
  import { assistants } from '$lib/stores/assistants.js'
  import { myTeachingGroups } from '$lib/stores/myGroups.js'
  import { refreshConversationCounts } from '$lib/stores/conversationCounts.js'
  import { fachSammlungen, schuelerSammlungen } from '$lib/collections.js'
  import AssistantCard from './AssistantCard.svelte'
  import ConversationMenu from './ConversationMenu.svelte'
  import NodeTypeIcon from './NodeTypeIcon.svelte'
  import { Search } from 'lucide-svelte'

  let { group, subject = null, istLehrkraft = false } = $props()

  // ── Assistenten dieser Gruppe ─────────────────────────────────────────────
  const gruppenAssistenten = $derived(
    subject
      ? $assistants.filter(
          (a) =>
            a.subject_id === subject.id &&
            (a.scope === 'all' ||
              a.scope === 'subject_department' ||
              a.scope_group_id === group?.id),
        )
      : [],
  )

  // ── Chats dieser Gruppe ───────────────────────────────────────────────────
  // 25 statt 5: Die Liste ist scrollbar, fünf Zeilen sind nur die sichtbare Höhe.
  // Wer mehr braucht als 25, will ohnehin in die Historie.
  const LIMIT = 25
  let chats = $state([])
  let chatsGesamt = $state(0)
  let laedt = $state(true)

  async function ladeChats() {
    if (!group) return
    laedt = true
    try {
      const daten = await getConversations({ limit: LIMIT, groupId: group.id })
      chats = daten.items
      chatsGesamt = daten.total
    } finally {
      laedt = false
    }
  }

  function chatGeloescht(id) {
    chats = chats.filter((c) => c.id !== id)
    chatsGesamt = Math.max(0, chatsGesamt - 1)
    refreshConversationCounts()
  }

  $effect(() => {
    // Läuft bei Mount und bei Gruppenwechsel
    if (group) ladeChats()
  })

  function datum(wert) {
    if (!wert) return ''
    return new Date(wert).toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    })
  }
</script>

<!--
  Die Trennlinien setzt `divide-y` am Rahmen, nicht jeder Abschnitt für sich.

  **Warum das der Unterschied ist:** Drei der fünf Abschnitte sind bedingt — „Jetzt"
  nur für Lehrkräfte, „Assistenten" nur wenn es welche gibt. Eine fest an einen
  Abschnitt geschriebene Linie säße dann irgendwann oben (ein Strich über dem ersten
  Inhalt) oder fehlte in der Mitte. `divide-y` zusammen mit `first:pt-0`/`last:pb-0`
  zählt, was **tatsächlich gerendert** wurde: Svelte lässt nicht erfüllte `{#if}`-Zweige
  ganz weg, und Kommentarknoten sind keine Elemente — `:first-child` trifft also den
  ersten sichtbaren Abschnitt.

  Überschriften wie auf `/profile` (`text-base font-semibold`) — der nächste Verwandte
  dieser Seite: heterogene Abschnitte untereinander. Die vorher hier stehende
  Beschriftungsgröße (`text-xs uppercase`) ist im Projekt das Etikett *neben* etwas,
  keine Überschrift *über* etwas, und gliederte entsprechend wenig.
-->
<div class="divide-y divide-light-ui-2 dark:divide-dark-ui-2">

<!-- ── 1. Jetzt (nur Lehrkraft) — AP5 ───────────────────────────────────────
     Laufende/nächste Unterrichtseinheit, letzte und nächste Stunden.
     Kommt aus `GET /planning/groups/{id}/aktuell`. -->

<!-- ── 2. Weiterarbeiten ──────────────────────────────────────────────────── -->
<section class="py-6 first:pt-0 last:pb-0">
  <div class="flex items-center justify-between mb-4">
    <h2 class="text-base font-semibold text-light-tx-2 dark:text-dark-tx-2">
      Weiterarbeiten
    </h2>
    <div class="flex items-center gap-3">
      {#if chatsGesamt > chats.length}
        <a href="/history"
           class="text-sm text-light-bl dark:text-dark-bl hover:underline">
          alle Chats →
        </a>
      {/if}
      <button
        onclick={() => goto('/chat')}
        class="text-sm px-3 py-1.5 rounded-md bg-primary dark:bg-primary-dark
               text-white font-medium hover:opacity-90 transition-opacity"
      >
        + Neuer Chat
      </button>
    </div>
  </div>

  {#if laedt}
    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 py-4">Wird geladen…</p>
  {:else if chats.length === 0}
    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
      Hier ist noch nichts. Der erste Chat fängt oben rechts an.
    </p>
  {:else}
    <div class="max-h-64 overflow-y-auto rounded-lg border
                border-light-ui-3 dark:border-dark-ui-3">
      {#each chats as chat (chat.id)}
        <!-- Der Titel ist der Link, nicht die Zeile: Ein Menü-Knopf in einem
             anklickbaren Kasten wäre ein Bedienelement im Bedienelement. -->
        <div
          class="flex items-center gap-2 px-4 py-2.5
                 border-b last:border-b-0 border-light-ui-2 dark:border-dark-ui-2
                 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
        >
          <a
            href="/chat?id={chat.id}"
            class="flex-1 min-w-0 truncate text-sm text-light-tx dark:text-dark-tx"
          >
            {chat.title ?? 'Unbenannter Chat'}
          </a>
          <span class="text-xs text-light-tx-2 dark:text-dark-tx-2 whitespace-nowrap">
            {datum(chat.last_message_at)}
          </span>
          <ConversationMenu
            conversationId={chat.id}
            title={chat.title}
            subject_id={chat.subject_id}
            group_id={chat.group_id}
            onDeleted={() => chatGeloescht(chat.id)}
            iconSize={14}
          />
        </div>
      {/each}
    </div>
  {/if}
</section>

<!-- ── 3. Assistenten ─────────────────────────────────────────────────────── -->
{#if gruppenAssistenten.length > 0}
  <section class="py-6 first:pt-0 last:pb-0">
    <h2 class="text-base font-semibold text-light-tx-2 dark:text-dark-tx-2 mb-4">
      Assistenten
    </h2>
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {#each gruppenAssistenten as assistent (assistent.id)}
        <AssistantCard assistant={assistent} {subject} groups={$myTeachingGroups} />
      {/each}
    </div>
  </section>
{/if}

<!-- ── 4. Zuletzt entstanden — AP7 ───────────────────────────────────────────
     Bausteine (`/context/nodes?group_id=`) und Artefakte (Chat-Join) in *einer*
     nach Datum sortierten Liste. „Entstanden", nicht „verwendet": Für
     `node_engagement` gibt es heute keinen Schreiber, der Personen erfasst. -->

<!-- ── 5. Nachschlagen ───────────────────────────────────────────────────────
     Ein Abschnitt für beide Rollen, verschieden gefüllt: Lehrkräfte sehen alle
     fachgebundenen Sammlungen (das schließt ihr Planungsvokabular ein),
     Schüler:innen die, die für sie geschrieben sind (`schueler: true`).
     Das ist **keine** Rechteregel — alle sind `read_scope: school` und ohnehin
     lesbar; es geht allein darum, wofür es einen sichtbaren Weg gibt. -->
<section class="py-6 first:pt-0 last:pb-0">
  <h2 class="text-base font-semibold text-light-tx-2 dark:text-dark-tx-2 mb-4">
    Nachschlagen
  </h2>
  <div class="flex flex-wrap gap-2">
    {#each istLehrkraft ? fachSammlungen() : schuelerSammlungen() as sammlung (sammlung.typ)}
      <a
        href="/knowledge/collections/{sammlung.typ}?subject_id={subject?.id}"
        title={sammlung.beschreibung}
        class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md
               border border-light-ui-3 dark:border-dark-ui-3
               text-light-tx dark:text-dark-tx
               hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
      >
        <NodeTypeIcon contentType={sammlung.typ} size={16} />
        {sammlung.label}
      </a>
    {/each}
    <a
      href="/knowledge/search"
      class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md
             border border-light-ui-3 dark:border-dark-ui-3
             text-light-tx dark:text-dark-tx
             hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
    >
      <Search size={16} />
      Suche
    </a>
  </div>
</section>

</div>
