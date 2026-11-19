<script>
    /**
     * Veröffentlichen und „Als Entwurf kopieren“ (0.45, Päckchen AP Teil A) — im Kopf von
     * Ansicht und Editor eines Curriculums.
     *
     * Entwurf: Knopf „Veröffentlichen“ mit Übersicht im Dialog (warnt, sperrt nicht), oder wer
     * es darf. Veröffentlicht: „Als Entwurf kopieren“ für die Fachschaft, oder der Weg zum schon
     * begonnenen Entwurf. Die Rechte rechnet das Backend (`CurriculumRead`).
     */
    import { goto } from "$app/navigation";
    import { CopyPlus, Send, X } from "lucide-svelte";
    import Dialog from "./Dialog.svelte";
    import ErrorBanner from "./ErrorBanner.svelte";
    import LoadingBanner from "./LoadingBanner.svelte";
    import SuccessBanner from "./SuccessBanner.svelte";
    import {
        getVeroeffentlichenUebersicht,
        kopiereCurriculumAlsEntwurf,
        veroeffentlicheCurriculum,
    } from "$lib/api.js";
    import { uebersichtZeilen } from "$lib/curriculum_freigabe.js";

    /** `gesperrt`: ungespeicherte Änderungen im Editor — erst speichern. */
    /** `onveroeffentlicht`: nach dem Schließen des Ergebnisses — die Seite lädt neu. */
    let { curriculum, gesperrt = false, onveroeffentlicht = null } = $props();

    let offen = $state(false);
    let uebersicht = $state(null);
    let fehler = $state(null);
    let laeuft = $state(false);
    let ergebnis = $state(null);

    const knopf =
        "inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3 " +
        "text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors " +
        "disabled:opacity-50 disabled:cursor-not-allowed";

    async function oeffnen() {
        offen = true;
        uebersicht = null;
        fehler = null;
        ergebnis = null;
        try {
            uebersicht = await getVeroeffentlichenUebersicht(curriculum.id);
        } catch (e) {
            fehler = e.message;
        }
    }

    async function veroeffentlichen() {
        laeuft = true;
        fehler = null;
        try {
            ergebnis = await veroeffentlicheCurriculum(curriculum.id);
        } catch (e) {
            fehler = e.message;
        } finally {
            laeuft = false;
        }
    }

    function schliessen() {
        offen = false;
        // Nach dem Veröffentlichen frisch laden — Status, Knöpfe, Hinweis.
        if (!ergebnis) return;
        if (onveroeffentlicht) onveroeffentlicht();
        else goto(`/knowledge/curriculum/${curriculum.id}`);
    }

    async function kopieren() {
        laeuft = true;
        fehler = null;
        try {
            const { id } = await kopiereCurriculumAlsEntwurf(curriculum.id);
            goto(`/knowledge/curriculum/${id}/edit`);
        } catch (e) {
            fehler = e.message;
        } finally {
            laeuft = false;
        }
    }

    const zeilen = $derived(uebersichtZeilen(uebersicht));
</script>

{#if curriculum?.status === "draft"}
    {#if curriculum.darf_veroeffentlichen}
        <button
            type="button"
            class={knopf}
            onclick={oeffnen}
            disabled={gesperrt}
            title={gesperrt ? "Erst speichern" : "Übersicht ansehen und veröffentlichen"}
        >
            <Send class="w-4 h-4" /> Veröffentlichen
        </button>
    {:else}
        <span class="self-center text-xs text-light-tx-2 dark:text-dark-tx-2">
            Veröffentlichen dürfen: {curriculum.wer_veroeffentlicht}.
        </span>
    {/if}
{:else if curriculum?.status === "active"}
    {#if curriculum.offener_entwurf}
        <a href="/knowledge/curriculum/{curriculum.offener_entwurf.id}" class={knopf}>
            <CopyPlus class="w-4 h-4" /> Zum Entwurf
        </a>
    {:else if curriculum.darf_kopieren}
        <button
            type="button"
            class={knopf}
            onclick={kopieren}
            disabled={laeuft}
            title="Eine Kopie als Entwurf anlegen — sie ersetzt dieses Curriculum, sobald sie veröffentlicht ist"
        >
            <CopyPlus class="w-4 h-4" /> Als Entwurf kopieren
        </button>
    {/if}
{/if}
{#if fehler && !offen}
    <span class="self-center text-xs text-light-re dark:text-dark-re">{fehler}</span>
{/if}

{#if offen}
    <Dialog open onClose={schliessen} titelId="freigabe-titel" breite="max-w-lg max-h-[85vh] overflow-y-auto mx-4">
        <div class="flex items-start justify-between gap-4">
            <h2 id="freigabe-titel" class="text-lg font-semibold text-light-tx dark:text-dark-tx">
                {ergebnis ? "Veröffentlicht" : "Curriculum veröffentlichen"}
            </h2>
            <button
                onclick={schliessen}
                aria-label="Schließen"
                class="p-1 rounded hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 text-light-tx-2 dark:text-dark-tx-2"
            >
                <X class="w-4 h-4" />
            </button>
        </div>
        <div class="mt-3 space-y-3 text-sm">
            {#if fehler}
                <ErrorBanner message={fehler} />
            {/if}
            {#if ergebnis}
                <SuccessBanner
                    message={ergebnis.vorgaenger
                        ? `„${curriculum.title}“ ist veröffentlicht und ersetzt „${ergebnis.vorgaenger.title}“. ${ergebnis.einheiten_umgehaengt} Einheiten hängen jetzt an den neuen Kapiteln.`
                        : `„${curriculum.title}“ ist veröffentlicht — für alle sichtbar und in der Jahresplanung wählbar.`}
                />
            {:else if !uebersicht && !fehler}
                <LoadingBanner message="Übersicht wird geladen…" />
            {:else if uebersicht}
                <p class="text-light-tx-2 dark:text-dark-tx-2">
                    Danach sehen alle das Curriculum, auch in Suche, Chat und Jahresplanung. Die Übersicht
                    zeigt, was auffällt — veröffentlichen kannst du trotzdem.
                </p>
                <ul class="space-y-1" data-uebersicht="veroeffentlichen">
                    {#each zeilen as z, i (i)}
                        <li
                            class={z.warnung
                                ? "text-light-ye dark:text-dark-ye"
                                : "text-light-tx dark:text-dark-tx"}
                        >
                            {z.warnung ? "⚠ " : ""}{z.text}
                        </li>
                    {/each}
                </ul>
                <div class="flex justify-end gap-2 pt-2">
                    <button type="button" class={knopf} onclick={schliessen}>Abbrechen</button>
                    <button
                        type="button"
                        onclick={veroeffentlichen}
                        disabled={laeuft || !uebersicht.darf_veroeffentlichen}
                        class="inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-md bg-primary dark:bg-primary-dark
                               text-on-fill font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
                    >
                        <Send class="w-4 h-4" />
                        {laeuft ? "Wird veröffentlicht…" : "Veröffentlichen"}
                    </button>
                </div>
            {/if}
        </div>
    </Dialog>
{/if}
