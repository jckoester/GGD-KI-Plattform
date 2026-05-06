<script>
  import { onMount } from 'svelte'
  import SubjectDot from '$lib/components/SubjectDot.svelte'
  import { studentPickerItems, teacherPickerItems } from '$lib/stores/subjectPickerItems.js'
  import { user } from '$lib/stores/user.js'

  let { onselect, onclose } = $props()
  // onselect(item): item = { type: 'subject'|'group', id, subjectId?, label, color }
  //                 oder null → Fachkontext entfernen
  // onclose(): Nutzer schließt ohne Auswahl

  const isTeacher = $derived($user?.roles?.includes('teacher') ?? false)
  const items = $derived(isTeacher ? $teacherPickerItems : $studentPickerItems)

  let query = $state('')
  let focusedIndex = $state(0)
  let container = $state(null)
  let inputEl = $state(null)

  const filtered = $derived(
    query.trim()
      ? items.filter(item => item.label.toLowerCase().includes(query.toLowerCase()))
      : items
  )

  function handleKeydown(e) {
    const count = filtered.length
    switch (e.key) {
      case 'ArrowUp':
        e.preventDefault()
        focusedIndex = (focusedIndex - 1 + count) % count
        scrollIntoView(focusedIndex)
        break
      case 'ArrowDown':
        e.preventDefault()
        focusedIndex = (focusedIndex + 1) % count
        scrollIntoView(focusedIndex)
        break
      case 'Enter':
        e.preventDefault()
        if (count > 0) onselect(filtered[focusedIndex])
        break
      case 'Escape':
        e.preventDefault()
        onclose()
        break
    }
  }

  function scrollIntoView(index) {
    container?.querySelector(`[data-index="${index}"]`)?.scrollIntoView({ block: 'nearest' })
  }

  function handleBlur() { onclose() }

  $effect(() => { if (query === '#') query = '' })

  onMount(() => {
    focusedIndex = 0
    inputEl?.focus()
  })
</script>

<div
  bind:this={container}
  class="absolute bottom-full left-0 right-0 mb-2 z-50"
  onclick={(e) => e.stopPropagation()}
>
  <div class="w-full max-w-4xl mx-auto bg-light-bg-2 dark:bg-dark-bg-2
              border border-light-ui-3 dark:border-dark-ui-3
              rounded-lg shadow-lg overflow-hidden">
    <!-- Suchfeld -->
    <div class="px-3 py-2 border-b border-light-ui-3 dark:border-dark-ui-3">
      <input
        bind:this={inputEl}
        type="text"
        bind:value={query}
        onkeydown={handleKeydown}
        onblur={handleBlur}
        placeholder="Fach suchen…"
        class="w-full bg-transparent text-light-tx dark:text-dark-tx
               placeholder:text-light-tx-2 dark:placeholder:text-dark-tx-2
               focus:outline-none focus:ring-2 focus:ring-primary"
        autocomplete="off"
      />
    </div>

    <!-- Ergebnisse -->
    <div class="max-h-[260px] overflow-y-auto">
      <!-- Kein Fach -->
      <button
        onmousedown={(e) => e.preventDefault()}
        onclick={() => onselect(null)}
        class="w-full text-left px-3 py-2 text-sm flex items-center gap-2
               text-light-tx-2 dark:text-dark-tx-2
               hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
               border-b border-light-ui-2 dark:border-dark-ui-2"
      >
        <span class="w-2 h-2 rounded-full border border-light-ui-3 dark:border-dark-ui-3 shrink-0"></span>
        Kein Fach
      </button>

      {#if filtered.length === 0}
        <div class="px-3 py-4 text-center text-sm text-light-tx-2 dark:text-dark-tx-2">
          Kein Fach gefunden.
        </div>
      {:else}
        {#each filtered as item, i}
          <button
            data-index={i}
            onmousedown={(e) => e.preventDefault()}
            onclick={() => onselect(item)}
            class="w-full text-left text-sm flex items-center gap-2
                   text-light-tx dark:text-dark-tx
                   hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
                   {item.type === 'group' && isTeacher ? 'pl-8 pr-3 py-1.5' : 'px-3 py-2'}
                   {i === focusedIndex ? 'bg-light-ui-2 dark:bg-dark-ui-2' : ''}"
          >
            <SubjectDot color={item.color} />
            <span class="truncate {item.type === 'subject' ? 'font-medium' : ''}">
              {item.label}
            </span>
          </button>
        {/each}
      {/if}
    </div>
  </div>
</div>
