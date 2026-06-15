<script>
  import { ueColor, UE_PALETTE } from '$lib/planner.js'
  import { createUnit, updateUnit, deleteUnit, getGroupCurriculumChapters } from '$lib/api.js'
  import LoadingBanner from '$lib/components/LoadingBanner.svelte'
  import ErrorBanner from '$lib/components/ErrorBanner.svelte'

  // `unit` gesetzt → Bearbeiten-Modus, sonst Anlegen.
  const { open = false, groupId, unit = null, onCreated, onUpdated, onDeleted, onClose } = $props()

  const isEdit = $derived(!!unit)

  let titel = $state('')
  let farbe = $state(0)
  let saving = $state(false)
  let error = $state(null)
  let confirmDelete = $state(false)
  let deleting = $state(false)

  // Curriculum-Kapitel-Auswahl
  let curricula = $state([])
  let gradeUnbekannt = $state(false)
  let loadingChapters = $state(false)
  let chaptersError = $state(null)
  let selectedKapitelId = $state('')

  $effect(() => {
    if (open) {
      titel = unit?.title ?? ''
      farbe = unit?.metadata_?.farbe ?? 0
      error = null
      confirmDelete = false
      selectedKapitelId = unit?.kapitel_node_id ?? ''
      loadChapters()
    }
  })

  async function loadChapters() {
    loadingChapters = true
    chaptersError = null
    try {
      const data = await getGroupCurriculumChapters(groupId)
      curricula = data.curricula ?? []
      gradeUnbekannt = data.grade_unbekannt ?? false
    } catch (e) {
      chaptersError = e.message
      curricula = []
      gradeUnbekannt = false
    } finally {
      loadingChapters = false
    }
  }

  const hasChapters = $derived(curricula.some(c => c.kapitel.length > 0))

  function findKapitel(id) {
    if (!id) return null
    for (const c of curricula) {
      const k = c.kapitel.find(k => k.id === id)
      if (k) return k
    }
    return null
  }

  const selectedStd = $derived(findKapitel(selectedKapitelId)?.std ?? null)

  function onKapitelChange() {
    // Leeres Titelfeld mit dem Kapiteltitel vorbelegen
    if (titel.trim()) return
    const k = findKapitel(selectedKapitelId)
    if (k) titel = k.titel
  }

  function kapitelLabel(k) {
    let label = k.reihenfolge ? `${k.reihenfolge}. ${k.titel}` : k.titel
    if (k.std) label += ` · ${k.std} Std`
    return label
  }

  async function save() {
    if (!titel.trim()) { error = 'Titel ist erforderlich.'; return }
    saving = true
    error = null
    try {
      if (isEdit) {
        // Beim Bearbeiten immer alle Felder senden (kapitel_node_id explizit, ggf. null).
        const payload = { titel: titel.trim(), farbe, kapitel_node_id: selectedKapitelId || null }
        const updated = await updateUnit(groupId, unit.id, payload)
        onUpdated?.(updated)
      } else {
        const payload = { titel: titel.trim(), farbe }
        if (selectedKapitelId) payload.kapitel_node_id = selectedKapitelId
        const created = await createUnit(groupId, payload)
        onCreated?.(created)
      }
    } catch (e) {
      error = e.message
    } finally {
      saving = false
    }
  }

  async function remove() {
    if (!isEdit) return
    deleting = true
    error = null
    try {
      await deleteUnit(groupId, unit.id)
      onDeleted?.(unit)
    } catch (e) {
      error = e.message
      confirmDelete = false
    } finally {
      deleting = false
    }
  }

  function onKeydown(e) {
    if (e.key === 'Escape') onClose()
    if (e.key === 'Enter' && !saving) save()
  }

  const PALETTE_NAMES = ['Blau', 'Grün', 'Lila', 'Rot', 'Gold', 'Cyan', 'Braun', 'Stahlblau']
</script>

{#if open}
  <!-- Backdrop -->
  <div
    class="fixed inset-0 z-50 bg-black/40 flex items-center justify-center"
    onclick={(e) => { if (e.target === e.currentTarget) onClose() }}
  >
    <div
      class="bg-light-bg dark:bg-dark-bg border border-light-ui-3 dark:border-dark-ui-3 rounded-xl shadow-2xl w-full max-w-md p-6"
      onkeydown={onKeydown}
    >
      <h2 class="text-base font-semibold text-light-tx dark:text-dark-tx mb-4">
        {isEdit ? 'Unterrichtseinheit bearbeiten' : 'Unterrichtseinheit anlegen'}
      </h2>

      <div class="mb-4">
        <label class="block text-xs font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1">Titel</label>
        <input
          type="text"
          bind:value={titel}
          placeholder="z.B. Quadratische Funktionen"
          class="w-full px-3 py-2 text-sm bg-light-bg-2 dark:bg-dark-bg-2 border border-light-ui-3 dark:border-dark-ui-3 rounded-lg
                 text-light-tx dark:text-dark-tx outline-none focus:border-primary dark:focus:border-primary-dark transition-colors"
        />
      </div>

      <div class="mb-4">
        <label class="block text-xs font-medium text-light-tx-2 dark:text-dark-tx-2 mb-2">Farbe</label>
        <div class="flex gap-2 flex-wrap">
          {#each UE_PALETTE as [light], i}
            <button
              onclick={() => { farbe = i }}
              title={PALETTE_NAMES[i]}
              class="w-7 h-7 rounded-full transition-all
                     {farbe === i ? 'ring-2 ring-offset-2 ring-offset-light-bg dark:ring-offset-dark-bg ring-light-tx dark:ring-dark-tx scale-110' : 'hover:scale-105'}"
              style="background-color: {light}"
            ></button>
          {/each}
        </div>
      </div>

      <!-- Curriculum-Kapitel (optional) -->
      <div class="mb-5">
        <label class="block text-xs font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1">
          Curriculum-Kapitel <span class="font-normal">(optional)</span>
        </label>
        {#if loadingChapters}
          <LoadingBanner message="Curriculum wird geladen…" />
        {:else if chaptersError}
          <ErrorBanner message={chaptersError} />
        {:else}
          <select
            bind:value={selectedKapitelId}
            onchange={onKapitelChange}
            class="w-full px-3 py-2 text-sm bg-light-bg-2 dark:bg-dark-bg-2 border border-light-ui-3 dark:border-dark-ui-3 rounded-lg
                   text-light-tx dark:text-dark-tx outline-none focus:border-primary dark:focus:border-primary-dark transition-colors"
          >
            <option value="">— Kein Kapitel —</option>
            {#if curricula.length === 1}
              {#each curricula[0].kapitel as k}
                <option value={k.id}>{kapitelLabel(k)}</option>
              {/each}
            {:else}
              {#each curricula as c}
                {#if c.kapitel.length > 0}
                  <optgroup label={c.jahrgangsstufe ? `${c.titel} (Kl. ${c.jahrgangsstufe})` : c.titel}>
                    {#each c.kapitel as k}
                      <option value={k.id}>{kapitelLabel(k)}</option>
                    {/each}
                  </optgroup>
                {/if}
              {/each}
            {/if}
          </select>
          {#if !hasChapters}
            <p class="mt-1 text-xs text-light-tx-2 dark:text-dark-tx-2">
              Kein Curriculum für diese Gruppe gefunden – die Verknüpfung ist optional.
            </p>
          {:else if gradeUnbekannt}
            <p class="mt-1 text-xs text-light-tx-2 dark:text-dark-tx-2">
              Jahrgang nicht erkannt – es werden alle Curricula des Fachs angezeigt.
            </p>
          {/if}
          {#if selectedStd != null}
            <p class="mt-1 text-xs text-light-tx-2 dark:text-dark-tx-2">
              Soll-Umfang des Kapitels: {selectedStd} Stunden
            </p>
          {/if}
        {/if}
      </div>

      {#if error}
        <p class="text-sm text-light-re dark:text-dark-re mb-3">{error}</p>
      {/if}

      {#if confirmDelete}
        <!-- Bestätigung des Löschens -->
        <div class="rounded-lg border border-light-re/40 dark:border-dark-re/40 bg-light-re/5 dark:bg-dark-re/10 p-3">
          <p class="text-sm text-light-tx dark:text-dark-tx mb-1 font-medium">
            Unterrichtseinheit „{unit?.title}" löschen?
          </p>
          <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mb-3">
            Zugewiesene Stunden werden wieder freigegeben (nicht gelöscht).
            Bereits angelegte Stundenentwürfe bleiben erhalten.
          </p>
          <div class="flex justify-end gap-3">
            <button
              onclick={() => { confirmDelete = false }}
              disabled={deleting}
              class="px-4 py-2 text-sm rounded-lg text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 transition-colors"
            >
              Abbrechen
            </button>
            <button
              onclick={remove}
              disabled={deleting}
              class="px-4 py-2 text-sm rounded-lg font-medium bg-light-re dark:bg-dark-re text-white
                     hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {deleting ? 'Löschen…' : 'Endgültig löschen'}
            </button>
          </div>
        </div>
      {:else}
        <div class="flex items-center justify-between gap-3">
          <!-- Löschen (nur im Bearbeiten-Modus) -->
          {#if isEdit}
            <button
              onclick={() => { confirmDelete = true }}
              title="Unterrichtseinheit löschen"
              aria-label="Unterrichtseinheit löschen"
              class="p-2 rounded-lg text-light-tx-2 dark:text-dark-tx-2
                     hover:text-light-re dark:hover:text-dark-re hover:bg-light-re/10 dark:hover:bg-dark-re/10 transition-colors"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"
                   fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                   aria-hidden="true">
                <path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                <line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/>
              </svg>
            </button>
          {:else}
            <span></span>
          {/if}

          <div class="flex justify-end gap-3">
            <button
              onclick={onClose}
              class="px-4 py-2 text-sm rounded-lg text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 transition-colors"
            >
              Abbrechen
            </button>
            <button
              onclick={save}
              disabled={saving || !titel.trim()}
              class="px-4 py-2 text-sm rounded-lg font-medium bg-primary dark:bg-primary-dark text-white
                     hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? 'Speichern…' : isEdit ? 'Speichern' : 'Anlegen'}
            </button>
          </div>
        </div>
      {/if}
    </div>
  </div>
{/if}
