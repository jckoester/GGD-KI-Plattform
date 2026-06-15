<script>
  import { page } from '$app/stores'
  import { goto, afterNavigate } from '$app/navigation'
  import { subjectMap } from '$lib/stores/subjects.js'
  import { myTeachingGroups } from '$lib/stores/myGroups.js'
  import {
    getPlanningOverview,
    updateSlot,
    swapSlots,
    listSnapshots,
    restoreSnapshot,
    createLesson,
  } from '$lib/api.js'
  import SubjectIcon from '$lib/components/SubjectIcon.svelte'
  import ErrorBanner from '$lib/components/ErrorBanner.svelte'
  import LoadingBanner from '$lib/components/LoadingBanner.svelte'
  import PlannerTable from '$lib/components/planner/PlannerTable.svelte'
  import UnitLegend from '$lib/components/planner/UnitLegend.svelte'
  import UnitDialog from '$lib/components/planner/UnitDialog.svelte'
  import PatternEditor from '$lib/components/planner/PatternEditor.svelte'

  const groupId = $derived(Number($page.params.id))
  const slug = $derived($page.params.slug)
  const group = $derived($myTeachingGroups.find(g => g.id === groupId) ?? null)
  const subject = $derived(group ? ($subjectMap[group.subject_id] ?? null) : null)

  // ── Planungs-Daten ───────────────────────────────────────────────────────────
  let overview = $state(null)
  let slots = $state([])        // eigene Liste für optimistische Updates
  let loading = $state(true)
  let error = $state(null)
  let patchError = $state(null)
  let swapToast = $state(false)
  let swapToastTimer = null

  // ── Modals ───────────────────────────────────────────────────────────────────
  let showUnitDialog = $state(false)
  let editUnit = $state(null)   // UE im Bearbeiten-Modus (null = Anlegen)
  let plannerTable = $state(null)   // Komponenten-Instanz für scrollToUnit
  let showPatternEditor = $state(false)
  let showUndoPanel = $state(false)
  let snapshots = $state([])
  let snapshotsLoading = $state(false)
  let restoringId = $state(null)

  async function loadOverview() {
    loading = true
    error = null
    try {
      const data = await getPlanningOverview(groupId)
      overview = data
      slots = [...data.slots]
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  }

  // Lädt beim ersten Mount UND bei jeder (Rück-)Navigation auf diese Seite — z.B.
  // „Übersicht" aus dem Stundenentwurf. afterNavigate feuert auch initial, deshalb
  // kein zusätzlicher Mount-Effect (sonst Doppel-Load). Sonst zeigte der Plan
  // veraltete Slot↔Stunde-Verknüpfungen.
  afterNavigate(() => {
    if (groupId) loadOverview()
  })

  // ── Slot optimistisch patchen ────────────────────────────────────────────────
  async function patchSlot(slotId, updates) {
    patchError = null
    const idx = slots.findIndex(s => s.id === slotId)
    if (idx === -1) return
    const prev = slots[idx]
    slots[idx] = { ...prev, ...updates }

    try {
      const updated = await updateSlot(slotId, updates)
      slots[idx] = updated
      // Balance + Units im Overview aktualisieren wenn UE-Zuweisung geändert
      if ('ue_node_id' in updates || 'stunde_node_id' in updates) {
        const refreshed = await getPlanningOverview(groupId)
        overview = refreshed
        // Slots beibehalten die wir bereits optimistisch aktualisiert haben
        slots = refreshed.slots.map(s => {
          const local = slots.find(l => l.id === s.id)
          return local ?? s
        })
      }
    } catch (e) {
      slots[idx] = prev
      patchError = e.message
    }
  }

  // ── Slots tauschen ───────────────────────────────────────────────────────────
  async function handleSwapSlots(slotAId, slotBId) {
    patchError = null
    try {
      const [updatedA, updatedB] = await swapSlots(groupId, slotAId, slotBId)
      slots = slots.map(s => {
        if (s.id === updatedA.id) return updatedA
        if (s.id === updatedB.id) return updatedB
        return s
      })
      swapToast = true
      clearTimeout(swapToastTimer)
      swapToastTimer = setTimeout(() => { swapToast = false }, 3000)
    } catch (e) {
      patchError = e.message
    }
  }

  // ── Stundenentwurf öffnen / anlegen ─────────────────────────────────────────
  async function handleEditLesson(slotId, existingLessonNodeId) {
    if (existingLessonNodeId) {
      goto(`/subjects/${slug}/groups/${groupId}/planner/lessons/${existingLessonNodeId}`)
      return
    }
    // Stunde noch nicht angelegt: Slot → UE ermitteln, dann Stunde anlegen
    const slot = slots.find(s => s.id === slotId)
    if (!slot?.ue_node_id) return
    try {
      const result = await createLesson(slot.ue_node_id, {
        titel: slot.thema || 'Neue Stunde',
        slot_id: slotId,
      })
      // Slot optimistisch aktualisieren
      const idx = slots.findIndex(s => s.id === slotId)
      if (idx !== -1) slots[idx] = { ...slots[idx], stunde_node_id: result.id }
      goto(`/subjects/${slug}/groups/${groupId}/planner/lessons/${result.id}`)
    } catch (e) {
      patchError = e.message
    }
  }

  // ── Nachbereitung starten ────────────────────────────────────────────────────
  function handleReview(slotId, lessonNodeId) {
    if (lessonNodeId) {
      goto(`/subjects/${slug}/groups/${groupId}/planner/lessons/${lessonNodeId}?review=1`)
    }
  }

  // ── UE erstellt / bearbeitet ─────────────────────────────────────────────────
  async function refreshAfterUnitChange() {
    // Overview neu laden damit Balance + Units aktuell ist
    const refreshed = await getPlanningOverview(groupId)
    overview = refreshed
    slots = refreshed.slots.map(s => slots.find(l => l.id === s.id) ?? s)
  }

  async function onUnitCreated() {
    showUnitDialog = false
    await refreshAfterUnitChange()
  }

  function openEditUnit(unit) {
    editUnit = unit
    showUnitDialog = true
  }

  async function onUnitUpdated() {
    showUnitDialog = false
    editUnit = null
    await refreshAfterUnitChange()
  }

  async function onUnitDeleted() {
    showUnitDialog = false
    editUnit = null
    await refreshAfterUnitChange()
  }

  function closeUnitDialog() {
    showUnitDialog = false
    editUnit = null
  }

  // ── Muster gespeichert / Slots generiert ────────────────────────────────────
  async function onPatternSaved(hj, updatedPatterns) {
    if (!overview) return
    const otherPatterns = overview.patterns.filter(p => p.halbjahr !== hj)
    overview = { ...overview, patterns: [...otherPatterns, ...updatedPatterns] }
  }

  async function onSlotsGenerated(stats) {
    // Slots neu laden
    const refreshed = await getPlanningOverview(groupId)
    overview = refreshed
    slots = refreshed.slots
  }

  // ── Undo-Panel ───────────────────────────────────────────────────────────────
  async function openUndoPanel() {
    showUndoPanel = true
    snapshotsLoading = true
    try {
      snapshots = await listSnapshots(groupId)
    } catch (e) {
      snapshots = []
    } finally {
      snapshotsLoading = false
    }
  }

  async function restoreFrom(snapshotId) {
    restoringId = snapshotId
    try {
      await restoreSnapshot(snapshotId)
      showUndoPanel = false
      await loadOverview()
    } catch (e) {
      patchError = e.message
    } finally {
      restoringId = null
    }
  }

  const SNAPSHOT_REASON_LABELS = {
    edit: 'Bearbeitung',
    swap: 'Tausch',
    regeneration: 'Neu-Generierung',
    restore: 'Wiederherstellung',
    manual: 'Manuell',
    assistant: 'Assistent',
    reflow: 'Umstrukturierung',
  }
</script>

<svelte:head>
  <title>Jahresplanung{group ? ` – ${group.name}` : ''}</title>
</svelte:head>

<!-- Seitenkopf -->
<div class="border-b border-light-ui-2 dark:border-dark-ui-2 px-6 py-4 flex-shrink-0">
  <div class="flex items-center justify-between">
    <div>
      <div class="flex items-center gap-2 text-sm text-light-tx-2 dark:text-dark-tx-2 mb-1">
        {#if subject}
          <a
            href={`/subjects/${subject.slug}`}
            class="hover:text-light-tx dark:hover:text-dark-tx transition-colors flex items-center gap-1.5"
          >
            <SubjectIcon name={subject.icon} size={14} color={subject.color} />
            {subject.name}
          </a>
          <span>/</span>
          <a
            href={`/subjects/${subject.slug}/groups/${groupId}`}
            class="hover:text-light-tx dark:hover:text-dark-tx transition-colors"
          >
            {group?.name ?? '…'}
          </a>
          <span>/</span>
        {/if}
        <span class="text-light-tx dark:text-dark-tx font-medium">
          Planung {overview?.schuljahr ?? ''}
        </span>
      </div>
    </div>

    <div class="flex items-center gap-2">
      <!-- Assistent-Link -->
      <a
        href={`/chat?group_id=${groupId}`}
        class="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg
               bg-primary dark:bg-primary-dark text-white font-medium
               hover:opacity-90 transition-opacity"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
             fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
          <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/>
          <line x1="8" y1="12" x2="16" y2="12"/>
        </svg>
        Assistent
      </a>

      <!-- Undo-Button -->
      <button
        onclick={openUndoPanel}
        class="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-light-ui-3 dark:border-dark-ui-3
               text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 transition-colors"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
             fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/>
        </svg>
        Verlauf
      </button>

      <!-- Muster-Editor -->
      <button
        onclick={() => { showPatternEditor = true }}
        class="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-light-ui-3 dark:border-dark-ui-3
               text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 transition-colors"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
             fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/>
          <line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
        </svg>
        Wochenmuster
      </button>
    </div>
  </div>
</div>

{#if patchError}
  <div class="px-4 pt-2">
    <ErrorBanner message={patchError} />
  </div>
{/if}

{#if swapToast}
  <div class="fixed bottom-6 left-1/2 -translate-x-1/2 z-50
              px-4 py-2 rounded-lg shadow-xl text-sm font-medium
              bg-light-tx dark:bg-dark-tx text-light-bg dark:text-dark-bg">
    Getauscht — Undo im Verlauf verfügbar
  </div>
{/if}

{#if loading}
  <div class="flex-1 flex items-center justify-center">
    <LoadingBanner message="Jahresplanung wird geladen …" />
  </div>
{:else if error}
  <div class="p-6">
    <ErrorBanner message={error} />
  </div>
{:else if overview}
  <!-- UE-Legende -->
  <UnitLegend
    units={overview.units}
    balance={overview.balance}
    onCreateUnit={() => { editUnit = null; showUnitDialog = true }}
    onEditUnit={openEditUnit}
    onSelectUnit={(unit) => plannerTable?.scrollToUnit(unit.id)}
  />

  <!-- Tabelle (scrollbar) -->
  <div class="flex-1 overflow-y-auto">
    <PlannerTable
      bind:this={plannerTable}
      {slots}
      units={overview.units}
      patterns={overview.patterns}
      ferien={overview.ferien}
      feiertage={overview.feiertage}
      unterrichtsfreie={overview.unterrichtsfreie_tage}
      halbjahreswechsel={overview.halbjahreswechsel}
      beginn={overview.beginn}
      ende={overview.ende}
      onPatchSlot={patchSlot}
      onSwapSlots={handleSwapSlots}
      onEditLesson={handleEditLesson}
      onReview={handleReview}
    />
  </div>
{/if}

<!-- Modals -->
<UnitDialog
  open={showUnitDialog}
  {groupId}
  unit={editUnit}
  onCreated={onUnitCreated}
  onUpdated={onUnitUpdated}
  onDeleted={onUnitDeleted}
  onClose={closeUnitDialog}
/>

<PatternEditor
  open={showPatternEditor}
  {groupId}
  patterns={overview?.patterns ?? []}
  schuljahr={overview?.schuljahr ?? ''}
  onSaved={onPatternSaved}
  onGenerated={onSlotsGenerated}
  onClose={() => { showPatternEditor = false }}
/>

<!-- Undo-Panel (Seitenpanel) -->
{#if showUndoPanel}
  <button
    aria-label="Panel schließen"
    class="fixed inset-0 z-40 bg-black/30 w-full h-full cursor-default"
    onclick={() => { showUndoPanel = false }}
  ></button>
  <aside class="fixed right-0 top-0 bottom-0 z-50 w-80 bg-light-bg dark:bg-dark-bg border-l border-light-ui-3 dark:border-dark-ui-3 shadow-2xl flex flex-col">
    <div class="flex items-center justify-between px-5 py-4 border-b border-light-ui-3 dark:border-dark-ui-3">
      <h2 class="text-sm font-semibold text-light-tx dark:text-dark-tx">Planungsverlauf</h2>
      <button
        onclick={() => { showUndoPanel = false }}
        aria-label="Panel schließen"
        class="p-1 rounded hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 text-light-tx-2 dark:text-dark-tx-2 transition-colors"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"
             fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>
    </div>

    <div class="flex-1 overflow-y-auto py-2">
      {#if snapshotsLoading}
        <div class="px-5 py-4 text-sm text-light-tx-2 dark:text-dark-tx-2">Wird geladen …</div>
      {:else if !snapshots.length}
        <div class="px-5 py-4 text-sm text-light-tx-2 dark:text-dark-tx-2 italic">Noch kein Verlauf vorhanden.</div>
      {:else}
        {#each snapshots as snap (snap.id)}
          <div class="px-4 py-3 border-b border-light-ui-3 dark:border-dark-ui-3 last:border-0">
            <div class="flex items-start justify-between gap-2">
              <div class="min-w-0">
                <div class="text-xs font-medium text-light-tx dark:text-dark-tx">
                  {SNAPSHOT_REASON_LABELS[snap.reason] ?? snap.reason}
                  {#if snap.label}
                    <span class="font-normal text-light-tx-2 dark:text-dark-tx-2"> – {snap.label}</span>
                  {/if}
                </div>
                <div class="text-xs text-light-tx-2 dark:text-dark-tx-2 mt-0.5">
                  {new Date(snap.created_at).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
                </div>
              </div>
              <button
                onclick={() => restoreFrom(snap.id)}
                disabled={restoringId === snap.id}
                class="flex-shrink-0 px-2.5 py-1 text-xs rounded-md font-medium
                       bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 border border-light-ui-3 dark:border-dark-ui-3
                       transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {restoringId === snap.id ? '…' : 'Wiederherstellen'}
              </button>
            </div>
          </div>
        {/each}
      {/if}
    </div>
  </aside>
{/if}
