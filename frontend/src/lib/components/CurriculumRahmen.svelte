<script>
    // Rahmenangaben eines Curriculums (0.46, E19/E20): Wochenstunden je Stufe, Lehrwerk,
    // Beschlüsse, Schwerpunkte, Absprachen. Im Editor änderbar, in der Leseansicht nur,
    // wenn etwas angegeben ist.
    import { renderMarkdown } from "$lib/markdown.js";
    import {
        RAHMEN_TEXTFELDER,
        STUNDEN_JE_WOCHENSTUNDE,
        rahmenAngegeben,
        rahmenMit,
        stufen,
        verplanbar,
        wochenstundenText,
    } from "$lib/curriculum_rahmen.js";
    import { ChevronDown, ChevronRight } from "@lucide/svelte";
    import { untrack } from "svelte";

    let {
        rahmen = {},
        jahrgangsstufe = "",
        verplant = 0,
        editMode = false,
        onchange = () => {},
    } = $props();

    // Im Editor offen, solange noch nichts angegeben ist — dann fällt auf, dass etwas fehlt.
    // Nur der Anfangswert zählt: Danach klappt die Person selbst auf und zu.
    let offen = $state(untrack(() => editMode && !rahmenAngegeben(rahmen)));

    const bandStufen = $derived(stufen(jahrgangsstufe));
    const rahmenStd = $derived(verplanbar(rahmen, jahrgangsstufe));
    const wsText = $derived(wochenstundenText(rahmen, jahrgangsstufe));
    const sichtbar = $derived(editMode || rahmenAngegeben(rahmen));

    function setze(feld, wert, stufe = null) {
        onchange(rahmenMit(rahmen, feld, wert, stufe));
    }
</script>

{#if sichtbar}
    <section
        class="mb-4 rounded-lg border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg"
        aria-labelledby="rahmen-titel"
    >
        <button
            type="button"
            onclick={() => (offen = !offen)}
            aria-expanded={offen}
            class="w-full flex items-center gap-2 px-4 py-2 text-left"
        >
            {#if offen}<ChevronDown class="w-4 h-4" />{:else}<ChevronRight class="w-4 h-4" />{/if}
            <h2 id="rahmen-titel" class="text-base font-semibold text-light-tx dark:text-dark-tx">Rahmen</h2>
            {#if rahmenStd !== null}
                <span class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                    · verplant {verplant} von {rahmenStd} Std.
                </span>
            {:else if editMode}
                <span class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                    · Wochenstunden, Lehrwerk, Beschlüsse, Schwerpunkte, Absprachen in der Fachschaft
                </span>
            {/if}
        </button>

        {#if offen}
            <div class="px-4 pb-4 space-y-3">
                <!-- Wochenstunden -->
                <div>
                    <div class="text-sm font-medium text-light-tx dark:text-dark-tx mb-1">Wochenstunden</div>
                    {#if editMode}
                        {#if bandStufen.length}
                            <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
                                {#each bandStufen as s (s)}
                                    <label class="flex items-center gap-1.5 text-sm text-light-tx-2 dark:text-dark-tx-2">
                                        Kl. {s}
                                        <input
                                            type="text"
                                            inputmode="decimal"
                                            value={rahmen?.wochenstunden?.[String(s)] ?? ""}
                                            oninput={(e) => setze("wochenstunden", e.currentTarget.value, s)}
                                            aria-label={`Wochenstunden in Klasse ${s}`}
                                            class="w-14 px-2 py-1 text-sm rounded border
                                                   border-light-ui-3 dark:border-dark-ui-3
                                                   bg-light-bg dark:bg-dark-bg
                                                   text-light-tx dark:text-dark-tx
                                                   focus:outline-none focus:border-primary dark:focus:border-primary-dark"
                                        />
                                    </label>
                                {/each}
                            </div>
                        {:else}
                            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                                Erst die Jahrgangsstufe angeben.
                            </p>
                        {/if}
                    {:else}
                        <p class="text-sm text-light-tx dark:text-dark-tx">{wsText || "–"}</p>
                    {/if}
                    <p class="mt-1 text-xs text-light-tx-2 dark:text-dark-tx-2">
                        {#if rahmenStd !== null}
                            Verplanbar: {rahmenStd} Std. ({STUNDEN_JE_WOCHENSTUNDE} je Wochenstunde), verplant: {verplant} Std.
                        {:else}
                            Verplanbar sind {STUNDEN_JE_WOCHENSTUNDE} Stunden je Wochenstunde — sobald jede Stufe eine Angabe hat.
                        {/if}
                    </p>
                </div>

                {#each RAHMEN_TEXTFELDER as f (f.feld)}
                    {#if editMode}
                        <label class="block">
                            <span class="text-sm font-medium text-light-tx dark:text-dark-tx">{f.label}</span>
                            <textarea
                                value={rahmen?.[f.feld] ?? ""}
                                oninput={(e) => setze(f.feld, e.currentTarget.value)}
                                placeholder={f.platzhalter}
                                rows="2"
                                class="mt-1 w-full px-2 py-1 text-sm rounded border
                                       border-light-ui-3 dark:border-dark-ui-3
                                       bg-light-bg dark:bg-dark-bg
                                       text-light-tx dark:text-dark-tx
                                       focus:outline-none focus:border-primary dark:focus:border-primary-dark"
                            ></textarea>
                            {#if f.hinweis}
                                <span class="block text-xs text-light-tx-2 dark:text-dark-tx-2">{f.hinweis}</span>
                            {/if}
                        </label>
                    {:else if rahmen?.[f.feld]}
                        <div>
                            <div class="text-sm font-medium text-light-tx dark:text-dark-tx">{f.label}</div>
                            <div
                                class="prose prose-sm dark:prose-invert max-w-none
                                       prose-p:my-1 prose-ul:my-1 prose-ol:my-1
                                       prose-p:text-light-tx dark:prose-p:text-dark-tx
                                       prose-a:text-light-bl dark:prose-a:text-dark-bl"
                            >
                                {@html renderMarkdown(rahmen[f.feld])}
                            </div>
                        </div>
                    {/if}
                {/each}
            </div>
        {/if}
    </section>
{/if}
