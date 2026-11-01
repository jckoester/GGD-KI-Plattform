<script>
    /**
     * Offene Freigaben: eingereichte Assistenten mit Freigeben/Ablehnen (0.27, Plan F8 b).
     *
     * ⚠️ Bis 0.27 stand diese Warteschlange in `/assistants/manage`, während die Seite
     * „Assistenten-Freigabe“ (`/settings/assistants`) nur aktivieren und deaktivieren konnte —
     * die Freigabe stand an dem Ort, der nicht so hieß. Jetzt steht sie hier, und die
     * Verwaltung verweist mit einem Hinweis dorthin.
     *
     * Je Eintrag: Name, Zielgruppe, Klassenstufen, Urheber-Kürzel (F4, falls hinterlegt).
     */
    import { onMount } from "svelte";
    import { goto } from "$app/navigation";
    import { AlertCircle, Check, Eye, Loader2, X } from "lucide-svelte";
    import Dialog from "./Dialog.svelte";
    import ErrorBanner from "./ErrorBanner.svelte";
    import SuccessBanner from "./SuccessBanner.svelte";
    import { approveAssistant, getPendingAssistants, rejectAssistant } from "$lib/api.js";
    import { refreshPendingCount } from "$lib/stores/pendingAssistants.js";
    import { stufenText } from "$lib/assistentenliste.js";

    let { onGeaendert = () => {} } = $props();

    const AUDIENCE_LABELS = { student: "Schüler:innen", teacher: "Lehrkräfte", all: "Alle" };

    let eintraege = $state([]);
    let geladen = $state(false);
    let fehler = $state(null);
    let erfolg = $state(null);

    let ablehnen = $state(null);
    let begruendung = $state("");
    let lehntAb = $state(false);
    let ablehnFehler = $state(null);

    async function laden() {
        try {
            eintraege = (await getPendingAssistants()).items ?? [];
        } catch (e) {
            fehler = e.message;
        } finally {
            geladen = true;
        }
    }

    async function nachAenderung() {
        await Promise.all([laden(), refreshPendingCount()]);
        onGeaendert();
    }

    async function freigeben(a) {
        // Zielgruppe ist ein bewusster Prüfpunkt (Phase 13): student/all sind für
        // Schüler:innen sichtbar — eine Fehlkonfiguration hätte pädagogische Folgen.
        if ((a.audience === "student" || a.audience === "all") && !confirm(
            `„${a.name}“ wird für Schüler:innen sichtbar (Zielgruppe: ${AUDIENCE_LABELS[a.audience]}). ` +
            "Zielgruppe geprüft und freigeben?",
        )) return;
        try {
            await approveAssistant(a.id);
            erfolg = `„${a.name}“ wurde freigegeben.`;
            await nachAenderung();
        } catch (e) {
            fehler = e.message;
        }
    }

    function ablehnenOeffnen(a) {
        ablehnen = a;
        begruendung = "";
        ablehnFehler = null;
    }

    function ablehnenSchliessen() {
        ablehnen = null;
    }

    async function ablehnenBestaetigen() {
        lehntAb = true;
        try {
            await rejectAssistant(ablehnen.id, begruendung || null);
            erfolg = `„${ablehnen.name}“ wurde abgelehnt.`;
            ablehnen = null;
            await nachAenderung();
        } catch (e) {
            ablehnFehler = e.message;
        } finally {
            lehntAb = false;
        }
    }

    onMount(laden);
</script>

<section class="mb-8">
    <h2 class="text-base font-semibold text-light-tx dark:text-dark-tx mb-3 flex items-center gap-2">
        <AlertCircle class="w-4 h-4 text-light-ye dark:text-dark-ye" />
        Offene Freigaben{eintraege.length ? ` (${eintraege.length})` : ""}
    </h2>

    {#if fehler}
        <div class="mb-3"><ErrorBanner message={fehler} /></div>
    {/if}
    {#if erfolg}
        <div class="mb-3"><SuccessBanner message={erfolg} /></div>
    {/if}

    {#if !geladen}
        <Loader2 class="w-5 h-5 animate-spin text-light-tx-2 dark:text-dark-tx-2" />
    {:else if eintraege.length === 0}
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">Keine Einreichung wartet auf Freigabe.</p>
    {:else}
        <div class="space-y-2">
            {#each eintraege as item (item.id)}
                <div class="flex items-center justify-between p-3 rounded-lg
                            bg-light-bg-2 dark:bg-dark-bg-2 border border-light-ui-3 dark:border-dark-ui-3">
                    <div class="flex-1 min-w-0 mr-4">
                        <span class="font-medium text-light-tx dark:text-dark-tx">{item.name}</span>
                        <!-- Zielgruppe hervorgehoben: bewusster Prüfpunkt (content-moderation.md). -->
                        <span
                            class="ml-2 px-1.5 py-0.5 rounded-full text-xs font-medium align-middle
                                   {item.audience === 'teacher'
                                ? 'bg-light-ui-2 dark:bg-dark-ui-2 text-light-tx dark:text-dark-tx'
                                : 'bg-light-or/20 dark:bg-dark-or/20 text-light-or dark:text-dark-or'}"
                            title="Zielgruppe"
                        >
                            {AUDIENCE_LABELS[item.audience] || item.audience}
                        </span>
                        <span class="ml-1 text-xs text-light-tx-2 dark:text-dark-tx-2">
                            {stufenText(item) ? `${stufenText(item)} · ` : ""}{item.urheber_kuerzel ? `von ${item.urheber_kuerzel}` : "ohne Stundenplan-Kürzel"}
                        </span>
                        {#if item.description}
                            <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 truncate">{item.description}</p>
                        {/if}
                    </div>
                    <div class="flex items-center gap-2 shrink-0">
                        <button onclick={() => goto(`/assistants/manage/${item.id}`)} title="Ansehen"
                            class="p-1.5 rounded-md hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 text-light-tx-2 dark:text-dark-tx-2">
                            <Eye class="w-4 h-4" />
                        </button>
                        <button onclick={() => freigeben(item)} title="Freigeben"
                            class="p-1.5 rounded-md hover:bg-light-gr/10 dark:hover:bg-dark-gr/10 text-light-gr dark:text-dark-gr">
                            <Check class="w-4 h-4" />
                        </button>
                        <button onclick={() => ablehnenOeffnen(item)} title="Ablehnen"
                            class="p-1.5 rounded-md hover:bg-light-re/10 dark:hover:bg-dark-re/10 text-light-re dark:text-dark-re">
                            <X class="w-4 h-4" />
                        </button>
                    </div>
                </div>
            {/each}
        </div>
    {/if}
</section>

{#if ablehnen}
    <Dialog open onClose={ablehnenSchliessen} titelId="ablehnen-titel" breite="max-w-sm">
        <h2 id="ablehnen-titel" class="text-lg font-semibold text-light-tx dark:text-dark-tx">Einreichung ablehnen</h2>
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
            Möchtest du die Einreichung „{ablehnen.name}“ wirklich ablehnen?
        </p>
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1 mb-3">
            Begründung (optional) — wird der Lehrkraft im Editor angezeigt.
        </p>
        {#if ablehnFehler}
            <div class="mb-3"><ErrorBanner message={ablehnFehler} /></div>
        {/if}
        <textarea bind:value={begruendung} rows="3" placeholder="Begründung für die Ablehnung (optional)"
            class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg-2 dark:bg-dark-bg-2
                   text-light-tx dark:text-dark-tx px-3 py-2 resize-none mb-4"></textarea>
        <div class="flex justify-end gap-2">
            <button onclick={ablehnenSchliessen} disabled={lehntAb}
                class="px-4 py-2 bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx rounded-lg
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 disabled:opacity-50">Abbrechen</button>
            <button onclick={ablehnenBestaetigen} disabled={lehntAb}
                class="px-4 py-2 bg-light-re dark:bg-dark-re text-white rounded-lg flex items-center gap-2 disabled:opacity-50">
                {#if lehntAb}<Loader2 class="w-4 h-4 animate-spin" /> Wird abgelehnt…{:else}<X class="w-4 h-4" /> Ablehnen{/if}
            </button>
        </div>
    </Dialog>
{/if}
