<script>
    import { onMount } from 'svelte';

    let { assistants = [], onselect, onclose } = $props()
    // assistants: AssistantSummary[]
    // onselect(assistant): Nutzer wählt einen Assistenten
    // onclose(): Nutzer schließt ohne Auswahl (Escape oder Klick außerhalb)

    let query = $state('')
    let focusedIndex = $state(0)
    let container = $state(null)

    // Filterlogik
    let filtered = $derived(
        query.trim()
            ? assistants.filter(a =>
                a.name.toLowerCase().includes(query.toLowerCase()) ||
                (a.description ?? '').toLowerCase().includes(query.toLowerCase())
            )
            : assistants
    )

    // Tastatur-Navigation
    function handleKeydown(e) {
        const count = filtered.length
        if (count === 0) return

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
                if (count > 0) {
                    onselect(filtered[focusedIndex])
                }
                break
            case 'Escape':
                e.preventDefault()
                onclose()
                break
        }
    }

    function scrollIntoView(index) {
        const el = container?.querySelector(`[data-index="${index}"]`)
        if (el) {
            el.scrollIntoView({ block: 'nearest' })
        }
    }

    // Klick auf Eintrag
    function handleSelect(assistant) {
        onselect(assistant)
    }

    // Such-Input verliert Fokus = schließen
    function handleBlur() {
        onclose()
    }

    // Initial: das '/' aus dem Input entfernen
    $effect(() => {
        if (query === '/') {
            query = ''
        }
    })

    // Fokus auf das erste Element beim Öffnen
    onMount(() => {
        focusedIndex = 0
    })
</script>

<div
    bind:this={container}
    class="absolute bottom-full left-0 right-0 mb-2 z-50"
    onclick={(e) => e.stopPropagation()}
>
    <div class="w-full max-w-4xl mx-auto bg-light-bg-2 dark:bg-dark-bg-2
                border border-light-ui-3 dark:border-dark-ui-3
                rounded-lg shadow-lg overflow-hidden"
    >
        <!-- Suchfeld -->
        <div class="px-3 py-2 border-b border-light-ui-3 dark:border-dark-ui-3">
            <input
                type="text"
                bind:value={query}
                onkeydown={handleKeydown}
                onblur={handleBlur}
                placeholder="Assistenten suchen…"
                class="w-full bg-transparent text-light-tx dark:text-dark-tx
                       placeholder:text-light-tx-2 dark:placeholder:text-dark-tx-2
                       focus:outline-none focus:ring-2 focus:ring-primary"
                autocomplete="off"
            />
        </div>

        <!-- Ergebnisse -->
        <div class="max-h-[300px] overflow-y-auto">
            {#if filtered.length === 0}
                <div class="px-3 py-4 text-center text-sm text-light-tx-2 dark:text-dark-tx-2">
                    Keine Assistenten gefunden.
                </div>
            {:else}
                {#each filtered as assistant, i}
                    <button
                        data-index={i}
                        onmousedown={(e) => e.preventDefault()}
                        onclick={() => handleSelect(assistant)}
                        class="w-full px-3 py-2 text-left text-sm
                               flex items-start gap-2
                               text-light-tx dark:text-dark-tx
                               hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                               transition-colors
                               {i === focusedIndex ? 'bg-light-ui-2 dark:bg-dark-ui-2' : ''}"
                    >
                        <span class="w-2 h-2 mt-1.5 rounded-full bg-light-bl dark:bg-dark-bl shrink-0"></span>
                        <div class="flex-1 min-w-0">
                            <div class="flex items-center gap-2">
                                <span class="font-medium">{assistant.name}</span>
                                {#if assistant.audience}
                                    <span class="text-xs px-1.5 py-0.5 rounded-full
                                         bg-light-ui-3 dark:bg-dark-ui-3
                                         text-light-tx-2 dark:text-dark-tx-2">
                                        {assistant.audience}
                                    </span>
                                {/if}
                            </div>
                            {#if assistant.description}
                                <p class="text-xs mt-0.5 text-light-tx-2 dark:text-dark-tx-2
                                           line-clamp-1">
                                    {assistant.description}
                                </p>
                            {/if}
                        </div>
                    </button>
                {/each}
            {/if}
        </div>
    </div>
</div>
