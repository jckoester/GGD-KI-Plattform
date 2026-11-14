<script>
    /**
     * Einrichtung beim ersten Login (0.43) — Rahmen: Seiten, Schrittanzeige, Weiter/Zurück/Später.
     *
     * Welche Seiten, in welcher Reihenfolge und wo ein Wiedereinstieg beginnt, steht in
     * `$lib/einrichtung.js`. Jede Wahl auf einer Seite wird sofort gespeichert; dieser Rahmen
     * speichert nur den **Stand**: „später“ samt Seite beim Schließen (auch Escape und Klick
     * daneben), „erledigt“, sobald die letzte Seite erreicht ist.
     *
     * Props: `daten` (Antwort von `GET /einrichtung`), `rolle`, `onClose(neueDaten?)`.
     */
    import { untrack } from 'svelte'
    import Dialog from '$lib/components/Dialog.svelte'
    import { Check, Circle } from 'lucide-svelte'
    import { getCalendarTeachers, putEinrichtung } from '$lib/api.js'
    import {
        ERSCHEINUNGSBILDER, fertigZeilen, fortschritt, gutZuWissen, planungsStufe, SEITEN, seitenNummer,
        sichtbareSeiten, startIndex, wegeWeiter,
    } from '$lib/einrichtung.js'
    import { renderMarkdown } from '$lib/markdown.js'
    import { themePref } from '$lib/stores/theme.js'
    import { budget } from '$lib/stores/budget.js'
    import { user } from '$lib/stores/user.js'
    import { setzeStufe, stufenRegistry, uiStufe } from '$lib/stores/uiLevel.js'
    import { aktuelleTeachingGroups } from '$lib/stores/myGroups.js'
    import { oeffneFeedback } from '$lib/stores/feedbackDialog.js'
    import KuerzelWahl from '$lib/components/KuerzelWahl.svelte'
    import WarningBanner from '$lib/components/WarningBanner.svelte'
    import LoadingBanner from '$lib/components/LoadingBanner.svelte'

    const { daten, rolle, onClose } = $props()

    // Seitenliste und Einstieg einmal beim Öffnen — eine Antwort, die während des Durchgangs
    // nachkommt, soll die Seiten nicht unter der Hand verschieben.
    const seiten = untrack(() => sichtbareSeiten(rolle, daten))
    let index = $state(untrack(() => startIndex(rolle, seiten, daten)))
    let erledigt = $state(false)
    let neu = $state(null)

    const seite = $derived(seiten[index])
    const letzte = $derived(index === seiten.length - 1)

    $effect(() => {
        if (letzte && !erledigt) {
            erledigt = true
            putEinrichtung('erledigt', seitenNummer(rolle, seite))
                .then((d) => (neu = d))
                .catch(() => {})
        }
    })

    async function schliessen() {
        if (erledigt) return onClose(neu)
        try {
            onClose(await putEinrichtung('spaeter', seitenNummer(rolle, seite)))
        } catch {
            // Nicht gespeichert: Der Dialog kommt beim nächsten Laden wieder — besser als festhängen.
            onClose(null)
        }
    }

    // ── Seiteninhalte ──────────────────────────────────────────────────────
    const absaetze = $derived(gutZuWissen(daten, $budget))
    const abPlanung = $derived(planungsStufe($stufenRegistry))

    // Kürzel-Liste erst, wenn die Seite drankommt — der Abruf meldet sich bei der Quelle an.
    let kuerzelListe = $state(null)
    let kuerzel = $state(untrack(() => $user?.preferences?.webuntis_kuerzel ?? ''))
    $effect(() => {
        if (seite === 'stundenplan' && kuerzelListe === null) {
            kuerzelListe = { laedt: true }
            getCalendarTeachers()
                .then((l) => (kuerzelListe = l))
                .catch((e) => (kuerzelListe = { error: e.message, teachers: [] }))
        }
    })

    const zeilen = $derived(fertigZeilen({
        theme: $themePref,
        stufe: $uiStufe,
        stufen: $stufenRegistry?.stufen,
        kuerzelGesetzt: Boolean($user?.preferences?.webuntis_kuerzel),
        stundenplan: daten?.stundenplan?.configured,
        gruppen: $aktuelleTeachingGroups.length,
    }))
    const wege = $derived(wegeWeiter($uiStufe, abPlanung))

    async function wegGehen(weg) {
        await schliessen()
        if (weg.aktion === 'feedback') oeffneFeedback()
    }

    const weiter = () => (index = Math.min(index + 1, seiten.length - 1))
    const zurueck = () => (index = Math.max(index - 1, 0))

    const knopf = 'px-3 py-1.5 text-sm rounded-md'
    const nebenKnopf = `${knopf} text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-bg-2 dark:hover:bg-dark-bg-2`
    const hauptKnopf = `${knopf} bg-primary dark:bg-primary-dark text-white hover:opacity-90`
</script>

<Dialog open onClose={schliessen} titelId="einrichtung-titel" breite="max-w-2xl max-h-[90dvh] flex flex-col">
    <div class="flex items-start justify-between gap-4 mb-1">
        <div>
            <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">Einrichtung · {fortschritt(index, seiten)}</p>
            <h2 id="einrichtung-titel" class="text-lg font-semibold text-light-tx dark:text-dark-tx">
                {SEITEN[seite].titel}
            </h2>
        </div>
        {#if !letzte}
            <button type="button" class={nebenKnopf} onclick={schliessen}>Später</button>
        {/if}
    </div>
    <div class="h-1 mb-4 rounded bg-light-ui-2 dark:bg-dark-ui-2" aria-hidden="true">
        <div class="h-1 rounded bg-primary dark:bg-primary-dark transition-all"
             style="width: {((index + 1) / seiten.length) * 100}%"></div>
    </div>

    <div class="flex-1 min-h-0 overflow-y-auto text-sm text-light-tx dark:text-dark-tx">
        {#if seite === 'willkommen'}
            <p class="mb-2">
                Hier hast du Zugang zu KI-Modellen für Unterricht und Vorbereitung — über die Schule,
                ohne dass dein Name den Schulserver verlässt.
            </p>
            <p class="mb-4 text-light-tx-2 dark:text-dark-tx-2">
                In ein paar Minuten richtest du dir die Plattform ein. Jede Wahl gilt sofort, und alles
                lässt sich später im Profil und unter „Unterricht“ ändern.
            </p>
            <p class="mb-2 font-medium">Erscheinungsbild</p>
            <div class="flex flex-wrap gap-2" role="group" aria-label="Erscheinungsbild">
                {#each ERSCHEINUNGSBILDER as e (e.wert)}
                    <button type="button" aria-pressed={$themePref === e.wert} onclick={() => themePref.set(e.wert)}
                            class="px-4 py-2 rounded-md text-sm font-medium transition-colors
                                   {$themePref === e.wert
                                       ? 'bg-primary dark:bg-primary-dark text-white'
                                       : 'bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}">
                        {e.name}
                    </button>
                {/each}
            </div>
        {:else if seite === 'gut_zu_wissen'}
            <div class="space-y-4">
                {#each absaetze as a (a.titel)}
                    <div>
                        <p class="font-medium">{a.titel}</p>
                        <p class="text-light-tx-2 dark:text-dark-tx-2">
                            {a.text}
                            {#each a.links ?? [] as l (l.href)}
                                <a href={l.href} target="_blank" rel="noopener"
                                   class="ml-1 text-light-bl dark:text-dark-bl hover:underline">{l.text}</a>
                            {/each}
                        </p>
                    </div>
                {/each}
                {#if daten?.hinweis}
                    <div class="pt-3 border-t border-light-ui-3 dark:border-dark-ui-3">
                        <p class="font-medium mb-1">Von deiner Schule</p>
                        <div class="prose prose-sm dark:prose-invert max-w-none">{@html renderMarkdown(daten.hinweis)}</div>
                    </div>
                {/if}
            </div>
        {:else if seite === 'stufe'}
            {#if $stufenRegistry?.stufen?.length}
                <p class="mb-3 text-light-tx-2 dark:text-dark-tx-2">
                    Wähle, wie viel du sehen möchtest. Jede Stufe enthält die vorherigen. Zurückschalten
                    blendet nur aus — nichts geht verloren. Weitere Stufen zeigt dir „Es gibt mehr“ am
                    Ende der Seitenleiste.
                </p>
                <div class="space-y-2">
                    {#each $stufenRegistry.stufen as st (st.stufe)}
                        {@const aktiv = $uiStufe === st.stufe}
                        <button type="button" onclick={() => setzeStufe(st.stufe)} aria-pressed={aktiv}
                                class="w-full text-left p-3 rounded-lg border transition-colors
                                       {aktiv
                                           ? 'border-primary dark:border-primary-dark bg-light-bl-bg dark:bg-dark-bl-bg'
                                           : 'border-light-ui-3 dark:border-dark-ui-3 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}">
                            <span class="flex items-center gap-2 font-medium">
                                {#if aktiv}<Check size={15} class="shrink-0 text-light-bl dark:text-dark-bl" />{/if}
                                Stufe {st.stufe}: {st.name}
                            </span>
                            <span class="block mt-1 text-xs text-light-tx-2 dark:text-dark-tx-2">{st.beschreibung}</span>
                            {#if st.aufwand}
                                <span class="block mt-1 text-xs italic text-light-tx-2 dark:text-dark-tx-2">{st.aufwand}</span>
                            {/if}
                        </button>
                    {/each}
                </div>
                {#if abPlanung}
                    <p class="mt-3 text-light-tx-2 dark:text-dark-tx-2">
                        Ab Stufe {abPlanung} steht „Planung“ in der Seitenleiste: Jahresübersicht und
                        Stundenentwürfe für deine Unterrichtsgruppen.
                    </p>
                {/if}
            {:else}
                <p class="text-light-tx-2 dark:text-dark-tx-2">Für deine Rolle gibt es keinen Zuschnitt — du siehst alles.</p>
            {/if}
        {:else if seite === 'stundenplan'}
            <p class="mb-4 text-light-tx-2 dark:text-dark-tx-2">
                Mit deinem Kürzel liest die Plattform deinen Stundenplan: Wochenmuster, Ausfälle und
                Vertretungen. Daraus entstehen auf der nächsten Seite deine Unterrichtsgruppen.
            </p>
            {#if !kuerzelListe || kuerzelListe.laedt}
                <LoadingBanner message="Kürzel werden geladen …" />
            {:else if kuerzelListe.error && !kuerzelListe.teachers?.length}
                <WarningBanner message={`Der Stundenplan antwortet gerade nicht (${kuerzelListe.error}). Du kannst weitergehen und das Kürzel später unter „Unterricht“ wählen.`} />
            {:else}
                <KuerzelWahl teachers={kuerzelListe.teachers} bind:kuerzel />
            {/if}
        {:else if seite === 'gruppen'}
            <!-- Schritt 5 -->
            <p class="text-light-tx-2 dark:text-dark-tx-2">{SEITEN[seite].titel}</p>
        {:else if seite === 'fertig'}
            <ul class="space-y-1.5 mb-5">
                {#each zeilen as z (z.text)}
                    <li class="flex items-start gap-2">
                        {#if z.ok}
                            <Check size={16} class="mt-0.5 shrink-0 text-light-gr dark:text-dark-gr" />
                        {:else}
                            <Circle size={16} class="mt-0.5 shrink-0 text-light-tx-2 dark:text-dark-tx-2" />
                        {/if}
                        <span>
                            {z.text}
                            <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">· {z.ok ? 'ändern' : 'nachholen'} unter „{z.nachholen}“</span>
                        </span>
                    </li>
                {/each}
            </ul>
            <p class="mb-2 font-medium">Wie weiter?</p>
            <div class="flex flex-col sm:flex-row gap-2">
                {#each wege as w (w.text)}
                    {#if w.href}
                        <a href={w.href} onclick={() => wegGehen(w)}
                           class="px-3 py-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3 text-center
                                  hover:bg-light-bg-2 dark:hover:bg-dark-bg-2">{w.text}</a>
                    {:else}
                        <button type="button" onclick={() => wegGehen(w)}
                                class="px-3 py-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                                       hover:bg-light-bg-2 dark:hover:bg-dark-bg-2">{w.text}</button>
                    {/if}
                {/each}
            </div>
            <p class="mt-4 text-xs text-light-tx-2 dark:text-dark-tx-2">
                Die Einrichtung findest du jederzeit wieder unter „Unterricht“ und im Profil.
            </p>
        {/if}
    </div>

    <div class="flex justify-between gap-2 mt-4 pt-4 border-t border-light-ui-3 dark:border-dark-ui-3">
        <button type="button" class={nebenKnopf} onclick={zurueck} disabled={index === 0}
                class:invisible={index === 0}>Zurück</button>
        {#if letzte}
            <button type="button" class={hauptKnopf} onclick={schliessen} data-autofocus>Fertig</button>
        {:else}
            <button type="button" class={hauptKnopf} onclick={weiter} data-autofocus>Weiter</button>
        {/if}
    </div>
</Dialog>
