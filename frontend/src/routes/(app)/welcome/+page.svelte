<script>
    import { goto } from '$app/navigation'
    import { MessageSquare } from 'lucide-svelte'
    import { user } from '$lib/stores/user.js'
    import { getMeinTag, getMeinTagSchueler } from '$lib/api.js'
    import {
        KEIN_NAECHSTER,
        zeigtSchuelerTag,
        zeigtTag,
        zweiteUeberschrift,
    } from '$lib/mein_tag.js'
    import TagesKachel from '$lib/components/TagesKachel.svelte'
    import SchuelerTagKachel from '$lib/components/SchuelerTagKachel.svelte'
    import GruppenKachel from '$lib/components/GruppenKachel.svelte'
    import ErrorBanner from '$lib/components/ErrorBanner.svelte'
    import {
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

    // Zwei Rollen, zwei Endpunkte. Die Schüler:innen-Antwort trägt Thema, Einheit und
    // Entwurf gar nicht erst — sie werden nicht ausgeblendet, sie stehen nicht drin.
    $effect(() => {
        const laden = isTeacher ? getMeinTag : getMeinTagSchueler
        laden()
            .then((d) => (tag = d))
            .catch((e) => (tagFehler = e.message))
    })

    /**
     * Welche Kacheln erscheinen — **als Objekt, nicht als lose Variablen.**
     *
     * Von dieser Aufstellung hängen zwei Dinge ab: was gerendert wird und **ob die Seite
     * mittig steht**. Als einzelne Booleans mit einer Oder-Kette daneben wäre die
     * nächste Kachel irgendwann nur an einer der beiden Stellen eingetragen — die Seite
     * zentrierte sich dann, obwohl darunter Inhalt steht, und schnüge ihn oben ab. So
     * zählt jeder neue Eintrag von selbst mit.
     */
    const kacheln = $derived({
        heute: !!tag && isTeacher && $zeigtKachel('heute') && zeigtTag(tag.heute, lage),
        naechster: !!tag && isTeacher && $zeigtKachel('naechster') && zeigtTag(tag.naechster, lage),
        gruppen: !!tag && isTeacher && $zeigtKachel('gruppen'),
        schuelerHeute:
            !!tag && !isTeacher && zeigtSchuelerTag(tag.heute, tag.hat_gruppen),
        schuelerNaechster:
            !!tag && !isTeacher && !!tag.naechster
            && zeigtSchuelerTag(tag.naechster, tag.hat_gruppen),
        fehler: !!tagFehler,
    })

    // Steht nichts darunter, gehört das Chatfeld in die Mitte — so war die Seite vor den
    // Kacheln, und so ist sie als Einstieg gedacht (Jan, 24.09.2026).
    const hatKacheln = $derived(Object.values(kacheln).some(Boolean))

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

<div
    class="h-full overflow-y-auto flex flex-col items-center px-4 py-12"
    class:justify-center={!hatKacheln}
>
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

        <!-- Der Tag — für Lehrkräfte mit Planung, für Schüler:innen nur die Fächer -->
        {#if kacheln.schuelerHeute}
            <SchuelerTagKachel titel="Heute" tag={tag.heute} hatGruppen={tag.hat_gruppen} />
        {/if}
        {#if kacheln.schuelerNaechster}
            <SchuelerTagKachel
                titel={zweiteUeberschrift(tag.naechster)}
                tag={tag.naechster}
                hatGruppen={tag.hat_gruppen}
            />
        {/if}

        {#if kacheln.fehler}
            <ErrorBanner message={tagFehler} />
        {/if}

        {#if isTeacher}
            {#if tag}
                {#if kacheln.heute}
                    <TagesKachel titel="Heute" tag={tag.heute} lage={lage} />
                {/if}
                {#if kacheln.naechster}
                    <TagesKachel
                        titel={zweiteUeberschrift(tag.naechster)}
                        tag={tag.naechster}
                        lage={lage}
                        leerHinweis={tag.naechster ? null : KEIN_NAECHSTER}
                    />
                {/if}
                {#if kacheln.gruppen}
                    <GruppenKachel />
                {/if}

                <!-- ⚠️ **Die Wahl selbst steht seit dem 25.09.2026 im Profil** (Jan).
                     Hier stand sie, weil man beim Ansehen merkt, dass eine Kachel stört —
                     dafür wurde die Startseite zu ihrer eigenen Einstellungsseite. Der
                     Weg bleibt: ein Verweis, keine zweite Bedienstelle. -->
                <a
                    href="/profile"
                    class="text-xs text-light-tx-2 dark:text-dark-tx-2 hover:underline"
                >
                    Kacheln wählen
                </a>
            {/if}
        {/if}



    </div>
</div>
