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
    createReview,
    deleteReview,
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

  // Nachbereiten-Modus
  let reviewMode = $state(false)
  let reviewStatus = $state({})   // phase_id → 'erledigt'|'offen'|'gestrichen'
  let reviewReflexion = $state('')
  let reviewRefsOffen = $state([]) // node_id UUIDs der betroffenen Refs
  let reviewStep = $state('phases') // 'phases' | 'refs' | 'done'
  let reviewResult = $state(null)
  let reviewError = $state(null)
  let reviewLoading = $state(false)

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
    if (nodeId) {
      load_().then(() => {
        if ($page.url.searchParams.get('review') === '1') {
          startReview()
        }
      })
    }
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

  // ── Nachbereiten ─────────────────────────────────────────────────────────────

  function startReview() {
    // Alle Phasen auf 'erledigt' vorbelegen
    const initial = {}
    for (const p of phasen) {
      initial[p.id ?? ''] = 'erledigt'
    }
    reviewStatus = initial
    reviewReflexion = ''
    reviewRefsOffen = []
    reviewStep = 'phases'
    reviewResult = null
    reviewError = null
    reviewMode = true
  }

  function cancelReview() {
    reviewMode = false
    reviewStep = 'phases'
  }

  function proceedToRefs() {
    const hasOpenPhases = Object.values(reviewStatus).some(s => s !== 'erledigt')
    if (hasOpenPhases) {
      reviewStep = 'refs'
    } else {
      submitReview()
    }
  }

  async function submitReview() {
    if (!lesson?.slot) return
    reviewLoading = true
    reviewError = null
    try {
      const result = await createReview(lesson.slot.id, {
        phasen_status: reviewStatus,
        reflexion: reviewReflexion || null,
        refs_offen: reviewRefsOffen,
      })
      reviewResult = result
      reviewStep = 'done'
      // Stunde neu laden um aktualisierten Status zu haben
      await load_()
    } catch (e) {
      reviewError = e.message
    } finally {
      reviewLoading = false
    }
  }

  async function undoReview() {
    if (!lesson?.slot) return
    reviewLoading = true
    reviewError = null
    try {
      await deleteReview(lesson.slot.id)
      reviewMode = false
      reviewStep = 'phases'
      reviewResult = null
      await load_()
    } catch (e) {
      reviewError = e.message
    } finally {
      reviewLoading = false
    }
  }

  const isReviewed = $derived(!!lesson?.slot?.nachbereitet_at)
  const isAutoReviewed = $derived(!!lesson?.slot?.nachbereitet_auto)
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

          <!-- Nachbereiten -->
          {#if isReviewed}
            <div class="flex items-center gap-1.5">
              <span class="text-xs px-2 py-1 rounded border
                           {isAutoReviewed
                             ? 'border-light-ui-3 dark:border-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2'
                             : 'border-green-400 text-green-700 dark:text-green-300'}">
                {isAutoReviewed ? '✓ auto' : '✓ nachbereitet'}
              </span>
              <button
                onclick={undoReview}
                disabled={reviewLoading}
                class="text-xs px-2 py-1 rounded border border-light-ui-3 dark:border-dark-ui-3
                       text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-bg-2 dark:hover:bg-dark-bg-2"
                title="Nachbereitung rückgängig machen"
              >↩︎ Rückgängig</button>
            </div>
          {:else if !reviewMode}
            <button
              onclick={startReview}
              class="flex items-center gap-1 text-sm px-3 py-1.5 rounded-lg border
                     border-green-400 text-green-700 dark:text-green-300
                     hover:bg-green-50 dark:hover:bg-green-950/20 transition-colors font-medium"
            >
              ☑︎ Nachbereiten
            </button>
          {/if}

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
        <div class="flex items-center justify-between mb-2">
          <h2 class="text-sm font-semibold text-light-tx dark:text-dark-tx">Verlaufsplan</h2>
          {#if reviewMode && reviewStep === 'phases'}
            <span class="text-xs text-green-700 dark:text-green-300 font-medium">
              Nachbereiten: Status pro Phase setzen
            </span>
          {/if}
        </div>
        <PhaseTable
          {phasen}
          verfuegbareMin={lesson.slot?.verfuegbare_min ?? 45}
          onChange={reviewMode ? () => {} : onPhasenChange}
          onSuggestCompetences={onSuggestCompetences}
          onMaterialCreate={openMaterialCreate}
          {reviewMode}
          {reviewStatus}
          onReviewStatusChange={(s) => { reviewStatus = s }}
        />
      </section>

      <!-- Review-Footer: Phasen-Schritt -->
      {#if reviewMode && reviewStep === 'phases'}
        <section class="border border-green-200 dark:border-green-900 rounded-lg p-4 space-y-3 bg-green-50/40 dark:bg-green-950/10">
          <h3 class="text-sm font-semibold text-light-tx dark:text-dark-tx">Kurzreflexion (optional)</h3>
          <textarea
            bind:value={reviewReflexion}
            rows="2"
            placeholder="Notizen zur Stunde …"
            class="w-full text-sm bg-light-bg dark:bg-dark-bg border border-light-ui-3 dark:border-dark-ui-3
                   rounded-md px-2.5 py-1.5 resize-none text-light-tx dark:text-dark-tx
                   outline-none focus:border-primary dark:focus:border-primary-dark"
          ></textarea>
          {#if reviewError}
            <p class="text-xs text-light-re dark:text-dark-re">{reviewError}</p>
          {/if}
          <div class="flex gap-2">
            <button
              onclick={proceedToRefs}
              disabled={reviewLoading}
              class="px-4 py-1.5 text-sm font-medium rounded-lg bg-primary dark:bg-primary-dark
                     text-white hover:opacity-90 disabled:opacity-50"
            >Abschließen</button>
            <button
              onclick={cancelReview}
              class="px-3 py-1.5 text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx"
            >Abbrechen</button>
          </div>
        </section>
      {/if}

      <!-- Review-Footer: Refs-Schritt (bei offenen Phasen) -->
      {#if reviewMode && reviewStep === 'refs'}
        <section class="border border-orange-200 dark:border-orange-900 rounded-lg p-4 space-y-3 bg-orange-50/40 dark:bg-orange-950/10">
          <h3 class="text-sm font-semibold text-light-tx dark:text-dark-tx">
            Welche Kompetenzen wurden durch die offenen Phasen nicht behandelt?
          </h3>
          <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
            Markierte Kompetenzen werden nicht als „eingeführt" gespeichert.
          </p>
          {#if refs.length === 0}
            <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 italic">Keine Kompetenzen zugeordnet.</p>
          {:else}
            <div class="space-y-1.5">
              {#each refs as ref}
                <label class="flex items-center gap-2 text-sm cursor-pointer">
                  <input
                    type="checkbox"
                    value={ref.node_id}
                    checked={reviewRefsOffen.includes(ref.node_id)}
                    onchange={(e) => {
                      if (e.currentTarget.checked) {
                        reviewRefsOffen = [...reviewRefsOffen, ref.node_id]
                      } else {
                        reviewRefsOffen = reviewRefsOffen.filter(id => id !== ref.node_id)
                      }
                    }}
                    class="rounded"
                  />
                  <span class="text-light-tx dark:text-dark-tx">
                    {ref.code ?? ''} {ref.titel ?? ref.node_id}
                    {#if ref.partiell}<span class="text-xs text-light-tx-2 dark:text-dark-tx-2">[partiell]</span>{/if}
                  </span>
                </label>
              {/each}
            </div>
          {/if}
          {#if reviewError}
            <p class="text-xs text-light-re dark:text-dark-re">{reviewError}</p>
          {/if}
          <div class="flex gap-2">
            <button
              onclick={submitReview}
              disabled={reviewLoading}
              class="px-4 py-1.5 text-sm font-medium rounded-lg bg-primary dark:bg-primary-dark
                     text-white hover:opacity-90 disabled:opacity-50"
            >{reviewLoading ? 'Speichern …' : 'Abschließen'}</button>
            <button
              onclick={() => { reviewStep = 'phases' }}
              class="px-3 py-1.5 text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx"
            >Zurück</button>
          </div>
        </section>
      {/if}

      <!-- Review-Ergebnis -->
      {#if reviewMode && reviewStep === 'done' && reviewResult}
        <section class="border border-green-200 dark:border-green-900 rounded-lg p-4 space-y-2 bg-green-50/40 dark:bg-green-950/10">
          <p class="text-sm font-medium text-green-700 dark:text-green-300">
            ✓ Stunde nachbereitet — {reviewResult.engagements_written} Engagement{reviewResult.engagements_written !== 1 ? 's' : ''} gespeichert.
          </p>
          {#if reviewResult.open_phases.length > 0}
            <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
              Offene Phasen: {reviewResult.open_phases.join(', ')}
            </p>
          {/if}
          <button
            onclick={undoReview}
            disabled={reviewLoading}
            class="text-xs text-light-tx-2 dark:text-dark-tx-2 hover:text-light-re dark:hover:text-dark-re"
          >↩︎ Rückgängig</button>
        </section>
      {/if}

    </div>
  </div>
{/if}
