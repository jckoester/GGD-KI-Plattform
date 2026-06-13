<script>
  import { goto } from '$app/navigation'
  import { page } from '$app/stores'
  import { subjectMap } from '$lib/stores/subjects.js'
  import { myTeachingGroups } from '$lib/stores/myGroups.js'
  import {
    getLesson,
    patchLesson,
    exportLesson,
    listSnapshots,
    restoreSnapshot,
    addChatContextNode,
  } from '$lib/api.js'
  import { periodLabel, dateLabel, weekdayLabel } from '$lib/planner.js'
  import ErrorBanner from '$lib/components/ErrorBanner.svelte'
  import LoadingBanner from '$lib/components/LoadingBanner.svelte'
  import CompetenceBar from '$lib/components/planner/CompetenceBar.svelte'
  import PhaseTable from '$lib/components/planner/PhaseTable.svelte'

  const { data } = $props()
  const nodeId = $derived(data.nodeId)
  const slug = $derived(data.slug)
  const groupId = $derived(data.groupId)

  const group = $derived($myTeachingGroups.find(g => g.id === groupId) ?? null)
  const subject = $derived(group ? ($subjectMap[group.subject_id] ?? null) : null)

  let lesson = $state(null)
  let loading = $state(true)
  let error = $state(null)
  let saveError = $state(null)
  let saving = $state(false)

  // Lokale Arbeitskopie der Phasen + refs
  let phasen = $state([])
  let refs = $state([])
  let refsDismissed = $state([])
  let stundenziel = $state('')
  let titel = $state('')
  let suggestions = $state([])

  // Debounce-Timer für Auto-Save
  let saveTimer = null

  async function load_() {
    loading = true
    error = null
    try {
      lesson = await getLesson(nodeId)
      phasen = lesson.phasen.map(p => ({ id: p.id ?? crypto.randomUUID(), ...p }))
      refs = lesson.refs ?? []
      refsDismissed = lesson.refs_dismissed ?? []
      stundenziel = lesson.stundenziel ?? ''
      titel = lesson.titel
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  }

  $effect(() => {
    if (nodeId) load_()
  })

  function scheduleSave() {
    clearTimeout(saveTimer)
    saveTimer = setTimeout(doSave, 1200)
  }

  async function doSave() {
    if (!lesson) return
    saving = true
    saveError = null
    try {
      await patchLesson(nodeId, {
        titel,
        stundenziel: stundenziel || null,
        phasen: phasen.map(p => ({
          id: p.id,
          name: p.name,
          dauer_min: p.dauer_min,
          beschreibung: p.beschreibung,
          prio: p.prio ?? 'kern',
          methode: p.methode ?? null,
          material: p.material ?? [],
        })),
        refs,
        refs_dismissed: refsDismissed,
      })
    } catch (e) {
      saveError = e.message
    } finally {
      saving = false
    }
  }

  function onPhasenChange(newPhasen) {
    phasen = newPhasen
    scheduleSave()
  }

  function onRefsChange(newRefs) {
    refs = newRefs
    scheduleSave()
  }

  function onDismissSuggestion(nodeId_) {
    refsDismissed = [...refsDismissed, nodeId_]
    suggestions = suggestions.filter(s => s.node_id !== nodeId_)
    scheduleSave()
  }

  function onSuggestCompetences(linkedNodeId) {
    // Keine direkte Lookup-Möglichkeit im Frontend — Backend gibt Vorschläge beim PATCH zurück
    // Hier wird nur getriggert; tatsächliche Vorschläge kommen vom nächsten Save
  }

  // ── Export ───────────────────────────────────────────────────────────────────
  async function download(format) {
    try {
      const blob = await exportLesson(nodeId, format)
      const ext = format
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `stundenentwurf.${ext}`
      a.click()
      URL.revokeObjectURL(a.href)
    } catch (e) {
      saveError = e.message
    }
  }

  async function copyMd() {
    try {
      const blob = await exportLesson(nodeId, 'md')
      const text = await blob.text()
      await navigator.clipboard.writeText(text)
    } catch (e) {
      saveError = e.message
    }
  }

  // ── Assistent öffnen ─────────────────────────────────────────────────────────
  function openAssistant() {
    goto(`/chat?group_id=${groupId}&node_id=${nodeId}`)
  }

  // ── Material-Erzeugung (✦ Szenario 6) ───────────────────────────────────────
  function openMaterialCreate(phase) {
    const prompt = encodeURIComponent(
      `Erstelle Material für Phase "${phase.name}" (${phase.dauer_min}′) im Stundenentwurf "${titel}".`
    )
    goto(`/chat?group_id=${groupId}&q=${prompt}`)
  }

  // ── Slot-Label ───────────────────────────────────────────────────────────────
  const slotLabel = $derived(() => {
    if (!lesson?.slot) return ''
    const s = lesson.slot
    const wd = weekdayLabel(s.date)
    const dl = dateLabel(s.date)
    const pl = s.start_period
      ? (s.periods >= 2 ? `${s.start_period}.–${s.start_period + 1}. Std (${s.verfuegbare_min}′)` : `${s.start_period}. Std (45′)`)
      : `${s.periods} Std (${s.verfuegbare_min}′)`
    return `${wd} ${dl} · ${pl}`
  })

  const plannerBase = $derived(`/subjects/${slug}/groups/${groupId}/planner`)
</script>

{#if loading}
  <div class="p-6"><LoadingBanner message="Stundenentwurf wird geladen …" /></div>
{:else if error}
  <div class="p-6"><ErrorBanner message={error} /></div>
{:else if lesson}
  <div class="flex flex-col h-full">

    <!-- Kopf -->
    <div class="flex-shrink-0 border-b border-light-ui-3 dark:border-dark-ui-3 px-4 py-3 bg-light-bg dark:bg-dark-bg">
      <!-- Breadcrumb -->
      <nav class="text-xs text-light-tx-2 dark:text-dark-tx-2 mb-2 flex items-center gap-1.5 flex-wrap">
        <a href={plannerBase} class="hover:text-light-bl dark:hover:text-dark-bl">Jahresübersicht</a>
        {#if lesson.ue}
          <span>›</span>
          <span>{lesson.ue.titel}</span>
        {/if}
        <span>›</span>
        <span>Stunde {lesson.nav.position} von {lesson.nav.total}</span>
      </nav>

      <!-- Titel + Slot-Info -->
      <div class="flex items-start gap-3 flex-wrap">
        <div class="flex-1 min-w-0">
          <!-- UE-Flag -->
          {#if lesson.ue}
            <div class="flex items-center gap-1.5 mb-1">
              <span class="w-3 h-3 rounded-full flex-shrink-0"
                    style="background-color: hsl({(lesson.ue.farbe ?? 0) * 45}deg 50% 50%)"></span>
              <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">{lesson.ue.titel}</span>
            </div>
          {/if}

          <!-- Titel (editable) -->
          <input
            type="text"
            bind:value={titel}
            onchange={scheduleSave}
            class="text-xl font-bold text-light-tx dark:text-dark-tx bg-transparent
                   border-b border-transparent focus:border-primary dark:focus:border-primary-dark
                   outline-none w-full"
          />

          {#if lesson.slot}
            <span class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-0.5">
              · {slotLabel()}
            </span>
          {/if}
        </div>

        <!-- Navigation + Export + Assistent -->
        <div class="flex items-center gap-2 flex-shrink-0 flex-wrap">
          <!-- Stunden-Navigation -->
          {#if lesson.nav.prev_node_id}
            <a href="{plannerBase}/lessons/{lesson.nav.prev_node_id}"
               class="text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-bl dark:hover:text-dark-bl px-2 py-1 rounded border border-light-ui-3 dark:border-dark-ui-3">
              ← Stunde {lesson.nav.position - 1}
            </a>
          {/if}
          {#if lesson.nav.next_node_id}
            <a href="{plannerBase}/lessons/{lesson.nav.next_node_id}"
               class="text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-bl dark:hover:text-dark-bl px-2 py-1 rounded border border-light-ui-3 dark:border-dark-ui-3">
              Stunde {lesson.nav.position + 1} →
            </a>
          {/if}

          <!-- Export -->
          <div class="flex items-center gap-1">
            <button onclick={() => download('md')}
                    class="text-xs px-2 py-1 rounded border border-light-ui-3 dark:border-dark-ui-3
                           text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-bg-2 dark:hover:bg-dark-bg-2">
              MD
            </button>
            <button onclick={copyMd}
                    class="text-xs px-2 py-1 rounded border border-light-ui-3 dark:border-dark-ui-3
                           text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-bg-2 dark:hover:bg-dark-bg-2"
                    title="Als Markdown in Zwischenablage kopieren (Obsidian)">
              📋
            </button>
            <button onclick={() => download('pdf')}
                    class="text-xs px-2 py-1 rounded border border-light-ui-3 dark:border-dark-ui-3
                           text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-bg-2 dark:hover:bg-dark-bg-2">
              PDF
            </button>
            <button onclick={() => download('docx')}
                    class="text-xs px-2 py-1 rounded border border-light-ui-3 dark:border-dark-ui-3
                           text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-bg-2 dark:hover:bg-dark-bg-2">
              DOCX
            </button>
          </div>

          <!-- Assistent -->
          <button
            onclick={openAssistant}
            class="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg
                   bg-primary dark:bg-primary-dark text-white font-medium
                   hover:opacity-90 transition-opacity"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
                 fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"
                 stroke-linejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="10"/>
              <path d="M12 8v4l3 3"/>
            </svg>
            Assistent
          </button>

          <!-- Undo (Snapshot) -->
          <a href={plannerBase}
             class="text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-bl dark:hover:text-dark-bl
                    px-2 py-1 rounded border border-light-ui-3 dark:border-dark-ui-3"
             title="Zur Jahresübersicht (Undo über Verlauf-Button)">
            ↩︎ Übersicht
          </a>
        </div>
      </div>

      <!-- Stundenziel -->
      <div class="mt-2">
        <input
          type="text"
          bind:value={stundenziel}
          onchange={scheduleSave}
          placeholder="Stundenziel eingeben …"
          class="w-full text-sm text-light-tx dark:text-dark-tx bg-transparent
                 border-b border-transparent focus:border-primary dark:focus:border-primary-dark
                 outline-none placeholder:text-light-tx-2 dark:placeholder:text-dark-tx-2 placeholder:italic"
        />
      </div>

      {#if saveError}
        <p class="text-xs text-light-re dark:text-dark-re mt-1">{saveError}</p>
      {/if}
      {#if saving}
        <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mt-1">Speichern …</p>
      {/if}
    </div>

    <!-- Inhalt (scrollbar) -->
    <div class="flex-1 overflow-y-auto px-4 py-4 space-y-6">

      <!-- Kompetenz-Leiste -->
      <section>
        <h2 class="text-sm font-semibold text-light-tx dark:text-dark-tx mb-2">Kompetenzen</h2>
        <CompetenceBar
          {refs}
          {suggestions}
          subjectId={lesson.subject_id}
          onChange={onRefsChange}
          onDismissSuggestion={onDismissSuggestion}
        />
      </section>

      <!-- Phasen-Tabelle -->
      <section>
        <h2 class="text-sm font-semibold text-light-tx dark:text-dark-tx mb-2">Verlaufsplan</h2>
        <PhaseTable
          {phasen}
          verfuegbareMin={lesson.slot?.verfuegbare_min ?? 45}
          onChange={onPhasenChange}
          onSuggestCompetences={onSuggestCompetences}
          onMaterialCreate={openMaterialCreate}
        />
      </section>

    </div>
  </div>
{/if}
