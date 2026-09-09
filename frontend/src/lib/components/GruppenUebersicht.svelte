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
  import {
    getConversations,
    getPlanningJetzt,
    createLesson,
    getContextNodes,
    getLibrary,
  } from '$lib/api.js'
  import {
    fortschritt,
    stundenReihen,
    stundenDatum,
    stundenAktion,
    zuletztEntstanden,
    ROLLEN_LABEL,
  } from '$lib/gruppenseite.js'
  import { assistants } from '$lib/stores/assistants.js'
  import { myTeachingGroups } from '$lib/stores/myGroups.js'
  import { refreshConversationCounts } from '$lib/stores/conversationCounts.js'
  import { fachSammlungen, schuelerSammlungen } from '$lib/collections.js'
  import AssistantCard from './AssistantCard.svelte'
  import ConversationMenu from './ConversationMenu.svelte'
  import NodeTypeIcon from './NodeTypeIcon.svelte'
  import ErrorBanner from './ErrorBanner.svelte'
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

  // ── Jetzt (nur Lehrkraft) ─────────────────────────────────────────────────
  // Der Endpunkt hängt an `require_group_teacher`; für Schüler:innen wird er gar
  // nicht erst gerufen, statt einen 403 wegzuwerfen.
  let jetzt = $state(null)
  let jetztFehler = $state(false)

  $effect(() => {
    if (!group || !istLehrkraft) return
    const id = group.id
    getPlanningJetzt(id)
      .then((daten) => {
        // Nach einem Gruppenwechsel könnte eine ältere Antwort später eintreffen.
        if (group?.id === id) {
          jetzt = daten
          jetztFehler = false
        }
      })
      .catch(() => {
        if (group?.id === id) jetztFehler = true
      })
  })

  const reihen = $derived(stundenReihen(jetzt))

  // Entwurf anlegen und öffnen — derselbe Weg wie im Jahresplan
  // (`planner/+page.svelte`, `handleEditLesson`): Der Entwurf entsteht an der
  // Unterrichtseinheit, mit dem Slot als Bezug und dem Thema als Titel.
  let legtAn = $state(null)
  let entwurfFehler = $state(null)

  async function entwurfAnlegen(stunde) {
    if (legtAn) return
    legtAn = stunde.slot_id
    entwurfFehler = null
    try {
      const neu = await createLesson(stunde.ue_node_id, {
        titel: stunde.thema || 'Neue Stunde',
        slot_id: stunde.slot_id,
      })
      await goto(
        `/subjects/${subject?.slug}/groups/${group?.id}/planner/lessons/${neu.id}`,
      )
    } catch (e) {
      entwurfFehler = e.message ?? 'Der Entwurf konnte nicht angelegt werden.'
      legtAn = null
    }
  }

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

  // ── Zuletzt entstanden ────────────────────────────────────────────────────
  // Zwei Quellen, eine Liste: eigene Bausteine dieser Gruppe und eigene Artefakte
  // aus Chats dieser Gruppe. Beide Abfragen holen bewusst nur Eigenes — Artefakte
  // sind ohnehin privat, und eine halb persönliche, halb geteilte Liste wäre keine.
  let entstanden = $state([])

  $effect(() => {
    if (!group) return
    const id = group.id
    Promise.all([
      getContextNodes({ group_id: id, owner: 'me', limit: 20 }).catch(() => []),
      getLibrary({ groupId: id, limit: 20 }).then((d) => d.items ?? []).catch(() => []),
    ]).then(([bausteine, artefakte]) => {
      if (group?.id === id) entstanden = zuletztEntstanden(bausteine, artefakte)
    })
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

<!-- ── 1. Jetzt (nur Lehrkraft) ────────────────────────────────────────────── -->
{#if istLehrkraft && jetzt && !jetztFehler}
  <section class="py-6 first:pt-0 last:pb-0">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-base font-semibold text-light-tx-2 dark:text-dark-tx-2">
        Jetzt
      </h2>
      {#if group}
        <a
          href="/subjects/{subject?.slug}/groups/{group.id}/planner"
          class="text-sm text-light-bl dark:text-dark-bl hover:underline"
        >
          Jahresplan →
        </a>
      {/if}
    </div>

    {#if !jetzt.hat_plan}
      <!-- Kein Wochenmuster: Ohne den Weg zur Planung stünde hier nur eine
           leere Fläche, und die sagt nicht, was zu tun ist. -->
      <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
        Für diese Gruppe sind noch keine Stunden verplant.
        <a
          href="/subjects/{subject?.slug}/groups/{group?.id}/planner"
          class="text-light-bl dark:text-dark-bl hover:underline"
        >
          Zur Planung
        </a>
      </p>
    {:else}
      {#if jetzt.laufende_einheit || jetzt.naechste_einheit}
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
          {#each [{ e: jetzt.laufende_einheit, label: 'Laufende Einheit' }, { e: jetzt.naechste_einheit, label: 'Nächste Einheit' }] as karte (karte.label)}
            {#if karte.e}
              <div
                class="p-3 rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg-2 dark:bg-dark-bg-2"
              >
                <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mb-1">
                  {karte.label}
                </p>
                <p class="text-sm font-medium text-light-tx dark:text-dark-tx">
                  {karte.e.titel}
                </p>
                <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mt-0.5">
                  {fortschritt(karte.e)}
                </p>
              </div>
            {/if}
          {/each}
        </div>
      {/if}

      {#if entwurfFehler}
        <div class="mb-3"><ErrorBanner message={entwurfFehler} /></div>
      {/if}

      {#if reihen.length > 0}
        <div class="rounded-lg border border-light-ui-3 dark:border-dark-ui-3">
          {#each reihen as stunde (stunde.slot_id)}
            {@const aktion = stundenAktion(stunde)}
            <div
              class="flex items-center gap-3 px-4 py-2
                     border-b last:border-b-0 border-light-ui-2 dark:border-dark-ui-2"
            >
              <span
                class="w-24 shrink-0 text-xs
                       {stunde.rolle === 'heute'
                         ? 'font-medium text-light-tx dark:text-dark-tx'
                         : 'text-light-tx-2 dark:text-dark-tx-2'}"
              >
                {ROLLEN_LABEL[stunde.rolle]}
              </span>
              <span class="w-20 shrink-0 text-xs text-light-tx-2 dark:text-dark-tx-2">
                {stundenDatum(stunde.datum)}
              </span>
              <span class="flex-1 min-w-0 truncate text-sm text-light-tx dark:text-dark-tx">
                {#if aktion.art === 'oeffnen'}
                  <a
                    href="/subjects/{subject?.slug}/groups/{group?.id}/planner/lessons/{aktion.nodeId}"
                    class="hover:underline"
                  >
                    {stunde.thema || 'Ohne Thema'}
                  </a>
                {:else}
                  {stunde.thema || 'Ohne Thema'}
                {/if}
              </span>
              <span class="shrink-0 text-xs text-light-tx-2 dark:text-dark-tx-2">
                {#if aktion.art === 'anlegen'}
                  <!-- „kein Entwurf" war eine Feststellung; hier ist der Ort, an
                       dem man etwas dagegen tut. -->
                  <button
                    onclick={() => entwurfAnlegen(stunde)}
                    disabled={legtAn !== null}
                    class="text-light-bl dark:text-dark-bl hover:underline disabled:opacity-50"
                  >
                    {legtAn === stunde.slot_id ? 'wird angelegt…' : 'Entwurf anlegen'}
                  </button>
                {:else if aktion.art === 'ohne_einheit'}
                  <span title="Ein Entwurf entsteht an der Unterrichtseinheit.">
                    keiner Einheit zugeordnet
                  </span>
                {:else if stunde.nachbereitet}
                  nachbereitet
                {/if}
              </span>
            </div>
          {/each}
        </div>
      {/if}
    {/if}
  </section>
{/if}

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

<!-- ── 4. Zuletzt entstanden ─────────────────────────────────────────────────
     „Entstanden", nicht „verwendet": Für `node_engagement` gibt es heute keinen
     Schreiber, der Personen erfasst — eine Nutzungsspur zu versprechen, die
     niemand füllt, wäre ein leeres Versprechen. -->
{#if entstanden.length > 0}
  <section class="py-6 first:pt-0 last:pb-0">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-base font-semibold text-light-tx-2 dark:text-dark-tx-2">
        Zuletzt entstanden
      </h2>
      <div class="flex items-center gap-3 text-sm">
        <a href="/knowledge/mine" class="text-light-bl dark:text-dark-bl hover:underline">
          meine Bausteine →
        </a>
        <a
          href="/library?subject_id={subject?.id}"
          class="text-light-bl dark:text-dark-bl hover:underline"
        >
          {subject ? `Artefakte in ${subject.name}` : 'Bibliothek'} →
        </a>
      </div>
    </div>

    <div class="rounded-lg border border-light-ui-3 dark:border-dark-ui-3">
      {#each entstanden as eintrag (eintrag.art + eintrag.id)}
        <a
          href={eintrag.href}
          class="flex items-center gap-3 px-4 py-2.5
                 border-b last:border-b-0 border-light-ui-2 dark:border-dark-ui-2
                 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
        >
          <NodeTypeIcon contentType={eintrag.typ} size={16} />
          <span class="flex-1 min-w-0 truncate text-sm text-light-tx dark:text-dark-tx">
            {eintrag.titel}
          </span>
          <!-- Die Herkunft verschwindet nicht, sie teilt nur nicht mehr die Liste. -->
          <span class="shrink-0 text-xs text-light-tx-2 dark:text-dark-tx-2">
            {eintrag.art === 'artefakt' ? 'Artefakt' : 'Baustein'}
          </span>
          <span class="shrink-0 w-20 text-right text-xs text-light-tx-2 dark:text-dark-tx-2">
            {datum(eintrag.datum)}
          </span>
        </a>
      {/each}
    </div>
  </section>
{/if}

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
