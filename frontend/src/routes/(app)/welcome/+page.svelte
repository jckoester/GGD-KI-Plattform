<script>
    import { goto } from '$app/navigation'
    import { MessageSquare } from 'lucide-svelte'
    import { user } from '$lib/stores/user.js'
    import { getMeinTag } from '$lib/api.js'
    import { KEIN_NAECHSTER, zweiteUeberschrift } from '$lib/mein_tag.js'
    import TagesKachel from '$lib/components/TagesKachel.svelte'
    import GruppenKachel from '$lib/components/GruppenKachel.svelte'
    import ErrorBanner from '$lib/components/ErrorBanner.svelte'
    import {
        KACHELN,
        schalteKachel,
        zeigtKachel,
    } from '$lib/stores/startkacheln.js'

    let tag = $state(null)
    let tagFehler = $state(null)
    const lage = $derived({
        hatGruppen: tag?.hat_gruppen ?? false,
        hatPlanung: tag?.hat_planung ?? false,
    })

    const displayName = sessionStorage.getItem('display_name') ?? ''

    function greeting() {
        const h = new Date().getHours()
        if (h < 11) return 'Guten Morgen'
        if (h < 17) return 'Guten Tag'
        return 'Guten Abend'
    }

    const isTeacher = $derived($user?.roles?.includes('teacher') ?? false)

    $effect(() => {
        if (!isTeacher) return
        getMeinTag()
            .then((d) => (tag = d))
            .catch((e) => (tagFehler = e.message))
    })

    let inputText = $state('')

    function startChat() {
        const q = inputText.trim()
        if (!q) {
            goto('/chat')
            return
        }
        goto(`/chat?q=${encodeURIComponent(q)}`)
    }

    function handleKeydown(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            startChat()
        }
    }
</script>

<div class="h-full overflow-y-auto flex flex-col items-center px-4 py-12">
    <div class="w-full max-w-xl flex flex-col gap-6">

        <!-- Begrüßung -->
        <div class="text-center">
            <h1 class="text-3xl font-bold text-light-tx dark:text-dark-tx">
                {greeting()}{displayName ? `, ${displayName}` : ''}
            </h1>
            <p class="mt-2 text-light-tx-2 dark:text-dark-tx-2">
                Womit kann ich dir heute helfen?
            </p>
        </div>

        <!-- Chat-Eingabe -->
        <div class="relative">
            <textarea
                bind:value={inputText}
                onkeydown={handleKeydown}
                placeholder="Stell eine Frage oder gib ein Thema ein …"
                rows="3"
                class="w-full resize-none rounded-xl border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg dark:bg-dark-bg-2
                       text-light-tx dark:text-dark-tx
                       placeholder:text-light-tx-3 dark:placeholder:text-dark-tx-3
                       px-4 py-3 pr-14 text-sm leading-relaxed
                       focus:outline-none focus:border-primary dark:focus:border-primary-dark
                       transition-colors"
            ></textarea>
            <button
                onclick={startChat}
                class="absolute bottom-3 right-3 p-2 rounded-lg
                       bg-primary dark:bg-primary-dark text-white
                       hover:opacity-90 transition-opacity disabled:opacity-40"
                disabled={!inputText.trim()}
                aria-label="Chat starten"
            >
                <MessageSquare size={16} />
            </button>
        </div>

        <!-- Der Tag (nur Lehrkräfte) -->
        {#if isTeacher}
            {#if tagFehler}
                <ErrorBanner message={tagFehler} />
            {:else if tag}
                {#if $zeigtKachel('heute')}
                    <TagesKachel titel="Heute" tag={tag.heute} lage={lage} />
                {/if}
                {#if $zeigtKachel('naechster')}
                    <TagesKachel
                        titel={zweiteUeberschrift(tag.naechster)}
                        tag={tag.naechster}
                        lage={lage}
                        leerHinweis={tag.naechster ? null : KEIN_NAECHSTER}
                    />
                {/if}
                {#if $zeigtKachel('gruppen')}
                    <GruppenKachel />
                {/if}

                <!-- Die Wahl steht hier und nicht im Profil: Wer eine Kachel weghaben
                     will, denkt das beim Ansehen — nicht zwei Seiten später. -->
                <details class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                    <summary class="cursor-pointer">Kacheln wählen</summary>
                    <div class="mt-2 flex flex-col gap-1">
                        {#each KACHELN as k (k.id)}
                            <label class="flex items-center gap-2">
                                <input
                                    type="checkbox"
                                    checked={$zeigtKachel(k.id)}
                                    onchange={(e) => schalteKachel(k.id, e.currentTarget.checked)}
                                    class="accent-primary"
                                />
                                {k.name}
                            </label>
                        {/each}
                    </div>
                </details>
            {/if}
        {/if}



    </div>
</div>
