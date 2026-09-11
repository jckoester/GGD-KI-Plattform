<script>
    /**
     * „Als Baustein speichern" — ein Formular, zwei Einstiege (UI-Notiz A5).
     *
     * Aus einem Bibliotheks-Artefakt wird ein Baustein im Wissensgraphen: mit
     * Bausteinart, Sichtbarkeit, Ablaufdatum und einem Platz in der Vernetzung. Das
     * Artefakt bleibt daneben liegen — die Übernahme ist ein Redaktionsakt, keine
     * Verschiebung.
     *
     * **Was der Server sagt, gilt.** Welche Arten zur Wahl stehen und ob die
     * Sichtbarkeit festliegt, kommt aus `GET /artifacts/{id}/baustein`. Bei
     * Schüler:innen erscheinen die Sichtbarkeitsfelder gar nicht erst: Ein Auswahlfeld
     * anzubieten, dessen Wert der Server ohnehin überschreibt, wäre eine Lüge — und
     * eines, das er *nicht* überschriebe, veröffentlichte einen Text, den jemand für
     * sich geschrieben hat.
     */
    import { onMount } from "svelte"
    import { Loader2 } from "lucide-svelte"
    import { bausteinAusArtefakt, getBausteinVorschlag } from "$lib/api.js"
    import {
        ablaufHinweis,
        brauchtGruppe,
        erfolgsMeldung,
        knopfBeschriftung,
        nutzlast,
        scopeVorgabe,
        typOptionen,
    } from "$lib/uebernahme.js"
    import {
        gruppenFuerScope,
        gueltigeGruppenwahl,
        myFachschaften,
        myTeachingGroups,
    } from "$lib/stores/myGroups.js"
    import {
        alsTagMonat,
        ladeSchuljahr,
        schoolYear,
        schuljahresEnde,
    } from "$lib/stores/schoolYear.js"
    import ErrorBanner from "$lib/components/ErrorBanner.svelte"
    import SuccessBanner from "$lib/components/SuccessBanner.svelte"
    import WarningBanner from "$lib/components/WarningBanner.svelte"

    let { artefakt, onclose, ongespeichert = null } = $props()

    let vorschlag = $state(null)
    let laedt = $state(true)
    let laeuft = $state(false)
    let fehler = $state(null)
    let erfolg = $state(null)
    let ergebnis = $state(null)

    let contentType = $state("")
    let titel = $state("")
    let readScope = $state("private")
    let writeScope = $state("private")
    let readGroupId = $state(null)
    let writeGroupId = $state(null)
    let validUntil = $state("")
    let schuljahr = $state("")

    const optionen = $derived(typOptionen(vorschlag))
    const scopesFest = $derived(vorschlag?.scopes_erzwungen != null)
    const gruppen = $derived({
        unterricht: $myTeachingGroups,
        fachschaften: $myFachschaften,
    })
    const readGruppen = $derived(gruppenFuerScope(readScope, gruppen))
    const writeGruppen = $derived(gruppenFuerScope(writeScope, gruppen))
    const hinweisAblauf = $derived(ablaufHinweis(contentType, validUntil))

    onMount(async () => {
        ladeSchuljahr()
        try {
            vorschlag = await getBausteinVorschlag(artefakt.id)
            titel = artefakt.title ?? ""
            contentType = vorschlag.vorgabe_typ ?? optionen[0]?.key ?? ""
            typGewechselt()
        } catch (e) {
            fehler = e.message
        } finally {
            laedt = false
        }
    })

    /**
     * Sichtbarkeit auf die Vorgabe der neuen Bausteinart stellen.
     *
     * Beim Umschalten, nicht in einem `$effect`: Ein Effekt liefe auch beim Laden und
     * überschriebe eine gerade getroffene Wahl — derselbe Fehler, der im Knoteneditor
     * schon einmal die Gruppe eines bestehenden Knotens geleert hat.
     */
    function typGewechselt() {
        const v = scopeVorgabe(vorschlag, contentType)
        readScope = v.read
        writeScope = v.write
        readGroupId = writeGroupId = null
    }

    function readScopeGewechselt() {
        readGroupId = gueltigeGruppenwahl(readGroupId, gruppenFuerScope(readScope, gruppen))
    }
    function writeScopeGewechselt() {
        writeGroupId = gueltigeGruppenwahl(writeGroupId, gruppenFuerScope(writeScope, gruppen))
    }

    async function speichern() {
        if (!contentType || laeuft) return
        laeuft = true
        fehler = null
        try {
            ergebnis = await bausteinAusArtefakt(
                artefakt.id,
                nutzlast({
                    contentType,
                    titel,
                    readScope: scopesFest ? null : readScope,
                    writeScope: scopesFest ? null : writeScope,
                    readGroupId,
                    writeGroupId,
                    validUntil,
                    schuljahr,
                }),
            )
            erfolg = erfolgsMeldung(ergebnis)
            ongespeichert?.(ergebnis)
        } catch (e) {
            fehler = e.message
        } finally {
            laeuft = false
        }
    }
</script>

<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
    <div
        class="w-full max-w-lg max-h-[85vh] overflow-y-auto rounded-lg p-6
               bg-light-bg dark:bg-dark-bg
               border border-light-ui-3 dark:border-dark-ui-3"
    >
        <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx">
            Als Baustein speichern
        </h2>
        <p class="mt-1 text-sm text-light-tx-2 dark:text-dark-tx-2">
            „{artefakt.title}" bekommt einen Platz im Wissensgraphen. Das Artefakt bleibt
            in der Bibliothek erhalten.
        </p>

        {#if laedt}
            <div class="flex items-center gap-2 py-8 text-light-tx-2 dark:text-dark-tx-2">
                <Loader2 class="w-4 h-4 animate-spin" /> Lädt…
            </div>
        {:else if erfolg}
            <div class="mt-4"><SuccessBanner message={erfolg} /></div>
            <div class="mt-5 flex justify-end gap-2">
                {#if ergebnis?.node_id}
                    <a
                        href="/knowledge/{ergebnis.node_id}"
                        class="px-3 py-1.5 text-sm rounded-lg
                               text-light-tx dark:text-dark-tx
                               hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
                    >
                        Baustein ansehen
                    </a>
                {/if}
                <button
                    onclick={onclose}
                    class="px-3 py-1.5 text-sm rounded-lg
                           bg-primary dark:bg-primary-dark text-white"
                >
                    Fertig
                </button>
            </div>
        {:else if vorschlag && !vorschlag.uebernehmbar}
            <div class="mt-4"><WarningBanner message={vorschlag.grund} /></div>
            <div class="mt-5 flex justify-end">
                <button
                    onclick={onclose}
                    class="px-3 py-1.5 text-sm rounded-lg
                           text-light-tx dark:text-dark-tx
                           hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
                >
                    Schließen
                </button>
            </div>
        {:else if optionen.length === 0}
            <div class="mt-4">
                <WarningBanner
                    message="Für deine Rolle ist zurzeit keine Bausteinart zur Übernahme freigegeben."
                />
            </div>
            <div class="mt-5 flex justify-end">
                <button
                    onclick={onclose}
                    class="px-3 py-1.5 text-sm rounded-lg
                           text-light-tx dark:text-dark-tx
                           hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
                >
                    Schließen
                </button>
            </div>
        {:else}
            {#if vorschlag.vorhandener_baustein_id}
                <!-- Zweite Übernahme: Der Plan schreibt eine Fassung vor, keinen
                     Zweitknoten — sonst stünden zwei aktive Bausteine desselben
                     Inhalts nebeneinander, und niemand wüsste, welcher gilt. -->
                <div class="mt-4 rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                            bg-light-bg-2 dark:bg-dark-bg-2 px-3 py-2">
                    <p class="text-sm text-light-tx dark:text-dark-tx">
                        Dieses Artefakt ist bereits als
                        <a
                            href="/knowledge/{vorschlag.vorhandener_baustein_id}"
                            class="text-light-bl dark:text-dark-bl underline"
                        >{vorschlag.vorhandener_baustein_titel}</a>
                        gespeichert. Speichern legt eine neue Fassung an; die bisherige
                        wandert ins Archiv und bleibt darüber erreichbar.
                    </p>
                </div>
            {/if}

            <form
                onsubmit={(e) => { e.preventDefault(); speichern() }}
                class="mt-4 space-y-4"
            >
                <div>
                    <label
                        for="uebernahme-typ"
                        class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
                    >
                        Bausteinart
                    </label>
                    <select
                        id="uebernahme-typ"
                        bind:value={contentType}
                        onchange={typGewechselt}
                        class="w-full px-3 py-2 text-sm rounded-md
                               border border-light-ui-3 dark:border-dark-ui-3
                               bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
                    >
                        {#each optionen as o (o.key)}
                            <option value={o.key}>{o.label}</option>
                        {/each}
                    </select>
                </div>

                <div>
                    <label
                        for="uebernahme-titel"
                        class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
                    >
                        Titel
                    </label>
                    <input
                        id="uebernahme-titel"
                        type="text"
                        bind:value={titel}
                        class="w-full px-3 py-2 text-sm rounded-md
                               border border-light-ui-3 dark:border-dark-ui-3
                               bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                               focus:outline-none focus:border-primary dark:focus:border-primary-dark"
                    />
                </div>

                {#if scopesFest}
                    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                        Nur du kannst diesen Baustein sehen und bearbeiten.
                    </p>
                {:else}
                    <div>
                        <label
                            for="uebernahme-read"
                            class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
                        >
                            Wer darf lesen?
                        </label>
                        <select
                            id="uebernahme-read"
                            bind:value={readScope}
                            onchange={readScopeGewechselt}
                            class="w-full px-3 py-2 text-sm rounded-md
                                   border border-light-ui-3 dark:border-dark-ui-3
                                   bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
                        >
                            <option value="private">Nur ich</option>
                            <option value="group">Eine Unterrichtsgruppe</option>
                            <option value="subject">Die Fachschaft</option>
                            <option value="school">Die ganze Schule</option>
                        </select>
                    </div>

                    {#if brauchtGruppe(readScope)}
                        <div>
                            <label
                                for="uebernahme-read-gruppe"
                                class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
                            >
                                {readScope === "group" ? "Unterrichtsgruppe" : "Fachschaft"}
                            </label>
                            <select
                                id="uebernahme-read-gruppe"
                                bind:value={readGroupId}
                                class="w-full px-3 py-2 text-sm rounded-md
                                       border border-light-ui-3 dark:border-dark-ui-3
                                       bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
                            >
                                <option value={null}>— bitte wählen —</option>
                                {#each readGruppen as g (g.id)}
                                    <option value={g.id}>{g.name}</option>
                                {/each}
                            </select>
                        </div>
                    {/if}

                    <div>
                        <label
                            for="uebernahme-write"
                            class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
                        >
                            Wer darf ändern?
                        </label>
                        <select
                            id="uebernahme-write"
                            bind:value={writeScope}
                            onchange={writeScopeGewechselt}
                            class="w-full px-3 py-2 text-sm rounded-md
                                   border border-light-ui-3 dark:border-dark-ui-3
                                   bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
                        >
                            <option value="private">Nur ich</option>
                            <option value="group">Eine Unterrichtsgruppe</option>
                            <option value="subject">Die Fachschaft</option>
                        </select>
                    </div>

                    {#if brauchtGruppe(writeScope)}
                        <div>
                            <label
                                for="uebernahme-write-gruppe"
                                class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
                            >
                                {writeScope === "group" ? "Unterrichtsgruppe" : "Fachschaft"}
                            </label>
                            <select
                                id="uebernahme-write-gruppe"
                                bind:value={writeGroupId}
                                class="w-full px-3 py-2 text-sm rounded-md
                                       border border-light-ui-3 dark:border-dark-ui-3
                                       bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
                            >
                                <option value={null}>— bitte wählen —</option>
                                {#each writeGruppen as g (g.id)}
                                    <option value={g.id}>{g.name}</option>
                                {/each}
                            </select>
                        </div>
                    {/if}
                {/if}

                <details class="border-t border-light-ui-3 dark:border-dark-ui-3 pt-3">
                    <summary
                        class="cursor-pointer text-sm text-light-tx-2 dark:text-dark-tx-2"
                    >
                        Ablauf und Schuljahr
                    </summary>
                    <div class="mt-3 space-y-3">
                        <div>
                            <label
                                for="uebernahme-ablauf"
                                class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
                            >
                                Ablaufdatum
                            </label>
                            <div class="flex flex-wrap gap-2 items-center">
                                <input
                                    id="uebernahme-ablauf"
                                    type="date"
                                    bind:value={validUntil}
                                    class="px-3 py-2 text-sm rounded-md
                                           border border-light-ui-3 dark:border-dark-ui-3
                                           bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
                                />
                                {#if $schuljahresEnde}
                                    <button
                                        type="button"
                                        onclick={() => (validUntil = $schuljahresEnde)}
                                        class="text-xs px-2 py-1.5 rounded-md
                                               bg-light-ui-2 dark:bg-dark-ui-2
                                               text-light-tx dark:text-dark-tx
                                               hover:bg-light-ui-3 dark:hover:bg-dark-ui-3"
                                    >
                                        Schuljahresende ({alsTagMonat($schuljahresEnde)})
                                    </button>
                                {/if}
                            </div>
                            {#if hinweisAblauf}
                                <p class="mt-1 text-xs text-light-tx-2 dark:text-dark-tx-2">
                                    {hinweisAblauf}
                                </p>
                            {/if}
                        </div>
                        <div>
                            <label
                                for="uebernahme-schuljahr"
                                class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
                            >
                                Schuljahr
                            </label>
                            <input
                                id="uebernahme-schuljahr"
                                type="text"
                                bind:value={schuljahr}
                                placeholder={$schoolYear?.schuljahr ?? "z. B. 2026/2027"}
                                class="w-full px-3 py-2 text-sm rounded-md
                                       border border-light-ui-3 dark:border-dark-ui-3
                                       bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
                            />
                        </div>
                    </div>
                </details>

                {#if fehler}
                    <ErrorBanner message={fehler} />
                {/if}

                <div class="flex justify-end gap-2 pt-1">
                    <button
                        type="button"
                        onclick={onclose}
                        class="px-3 py-1.5 text-sm rounded-lg
                               text-light-tx dark:text-dark-tx
                               hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
                    >
                        Abbrechen
                    </button>
                    <button
                        type="submit"
                        disabled={laeuft || !contentType}
                        class="px-3 py-1.5 text-sm rounded-lg
                               bg-primary dark:bg-primary-dark text-white
                               disabled:opacity-40"
                    >
                        {laeuft ? "Speichert…" : knopfBeschriftung(vorschlag)}
                    </button>
                </div>
            </form>
        {/if}
    </div>
</div>
