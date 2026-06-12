<script>
  import { ueColor, UE_PALETTE } from '$lib/planner.js'
  import { createUnit } from '$lib/api.js'

  const { open = false, groupId, onCreated, onClose } = $props()

  let titel = $state('')
  let farbe = $state(0)
  let saving = $state(false)
  let error = $state(null)

  $effect(() => {
    if (open) { titel = ''; farbe = 0; error = null }
  })

  async function save() {
    if (!titel.trim()) { error = 'Titel ist erforderlich.'; return }
    saving = true
    error = null
    try {
      const unit = await createUnit(groupId, { titel: titel.trim(), farbe })
      onCreated(unit)
    } catch (e) {
      error = e.message
    } finally {
      saving = false
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
        Unterrichtseinheit anlegen
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

      <div class="mb-5">
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

      {#if error}
        <p class="text-sm text-light-re dark:text-dark-re mb-3">{error}</p>
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
          {saving ? 'Speichern…' : 'Anlegen'}
        </button>
      </div>
    </div>
  </div>
{/if}
