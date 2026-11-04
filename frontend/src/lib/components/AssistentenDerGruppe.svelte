<script>
    /**
     * Reiter „Assistenten" der Gruppenseite (0.32, Päckchen AJ): Was eine Schüler:in dieser
     * Gruppe sieht — und welche eigenen Assistenten sie nicht sieht, mit Grund.
     *
     * Gerechnet wird im Backend mit derselben Regel wie Chat und Liste
     * (`app/groups/schuelersicht.py`); hier wird nur angezeigt. Die Vorschau („Als
     * Schüler:in ansehen") beantwortet dieselbe Frage durch Ausprobieren — der Knopf führt
     * mit dieser Gruppe und ihrem Jahrgang hinein.
     */
    import { untrack } from "svelte";
    import { getGruppenSchuelersicht } from "$lib/api.js";
    import { STUDENT_GRADES } from "$lib/grades.js";
    import { oeffneVorschau } from "$lib/stores/vorschauDialog.js";
    import {
        assistentLink, grundText, jahrgangText, jahrgangWaehlbar, stufenText,
    } from "$lib/schuelersicht.js";
    import { EyeOff, Eye } from "lucide-svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import InfoBanner from "$lib/components/InfoBanner.svelte";
    import LoadingBanner from "$lib/components/LoadingBanner.svelte";

    let { group } = $props();

    let sicht = $state(null);
    let fehler = $state(null);
    let laedt = $state(true);
    // Nur für Gruppen ohne bekannten Jahrgang (Plan F1): „" = nicht gewählt.
    let gewaehlt = $state("");

    async function laden() {
        if (!group?.id) return;
        laedt = true;
        fehler = null;
        try {
            sicht = await getGruppenSchuelersicht(group.id, gewaehlt ? Number(gewaehlt) : null);
        } catch (e) {
            fehler = e.message || "Die Assistenten der Gruppe konnten nicht geladen werden.";
        } finally {
            laedt = false;
        }
    }

    // Neu laden nur, wenn die Gruppe wechselt — der gewählte Jahrgang lädt über `onchange`.
    $effect(() => {
        group?.id;
        untrack(laden);
    });

    function ansehen() {
        oeffneVorschau({ gruppeId: group.id, ...(sicht?.jahrgang ? { jahrgang: sicht.jahrgang } : {}) });
    }

    const feld = "rounded border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx px-2 py-1 text-sm";
</script>

{#snippet eintrag(a, grund = null)}
    <li class="py-2 border-t first:border-t-0 border-light-ui-3 dark:border-dark-ui-3">
        <div class="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <a href={assistentLink(a)} class="font-medium text-light-bl dark:text-dark-bl hover:underline">
                {a.name}
            </a>
            {#if stufenText(a)}
                <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">Klasse {stufenText(a)}</span>
            {/if}
            {#if a.ausgeblendet}
                <span class="inline-flex items-center gap-1 text-xs text-light-tx-2 dark:text-dark-tx-2"
                      title="Benutzbar, aber nicht in Übersichten und Vorschlägen — nur über einen Link erreichbar">
                    <EyeOff size={12} /> ausgeblendet
                </span>
            {/if}
            {#if a.eigen && !grund}
                <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">von dir</span>
            {/if}
        </div>
        {#if grund}
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">{grundText(grund, a)}</p>
        {:else if a.description}
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 line-clamp-2">{a.description}</p>
        {/if}
    </li>
{/snippet}

<div class="space-y-6 max-w-3xl">
    <div class="flex flex-wrap items-start justify-between gap-3">
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 max-w-xl">
            So sieht eine Schüler:in dieser Gruppe die Assistenten — nach derselben Regel wie im
            Chat. Was einzelne Schüler:innen über andere Gruppen zusätzlich haben (AGs, andere
            Fächer), steht hier nicht.
        </p>
        <button
            onclick={ansehen}
            class="inline-flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg
                   bg-primary dark:bg-primary-dark text-white"
        >
            <Eye size={16} /> Als Schüler:in ansehen
        </button>
    </div>

    {#if fehler}
        <ErrorBanner message={fehler} />
    {:else if laedt && !sicht}
        <LoadingBanner />
    {:else if sicht}
        <div class="flex flex-wrap items-center gap-3 text-sm text-light-tx-2 dark:text-dark-tx-2">
            <span>{jahrgangText(sicht)}</span>
            {#if jahrgangWaehlbar(sicht)}
                <label class="flex items-center gap-2">
                    Klasse:
                    <select bind:value={gewaehlt} onchange={laden} class={feld}>
                        <option value="">nicht gewählt</option>
                        {#each STUDENT_GRADES as stufe (stufe)}
                            <option value={String(stufe)}>{stufe}</option>
                        {/each}
                    </select>
                </label>
            {/if}
        </div>
        {#if sicht.jahrgang != null && !sicht.modelle_bekannt}
            <InfoBanner message="Die Modellfreigabe für diese Klassenstufe ließ sich gerade nicht abfragen — die Liste ist deshalb nicht nach Modell gefiltert." />
        {/if}

        <section>
            <h2 class="text-base font-semibold text-light-tx dark:text-dark-tx mb-1">
                Für diese Gruppe freigegeben
            </h2>
            {#if sicht.fuer_die_gruppe.length}
                <ul>
                    {#each sicht.fuer_die_gruppe as a (a.id)}{@render eintrag(a)}{/each}
                </ul>
            {:else}
                <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                    Noch keiner. Im Assistenten-Editor gibst du einen Assistenten unter „Freigeben
                    für: Unterrichtsgruppe" für diese Gruppe frei.
                </p>
            {/if}
        </section>

        <section>
            <h2 class="text-base font-semibold text-light-tx dark:text-dark-tx mb-1">
                Schulweit{sicht.jahrgang != null ? ` für Klasse ${sicht.jahrgang}` : ""}
            </h2>
            {#if sicht.schulweit.length}
                <ul>
                    {#each sicht.schulweit as a (a.id)}{@render eintrag(a)}{/each}
                </ul>
            {:else}
                <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">Keine.</p>
            {/if}
        </section>

        {#if sicht.eigene_unsichtbar.length}
            <section>
                <h2 class="text-base font-semibold text-light-tx dark:text-dark-tx mb-1">
                    Deine Assistenten, die diese Gruppe nicht sieht
                </h2>
                <ul>
                    {#each sicht.eigene_unsichtbar as a (a.id)}{@render eintrag(a, a.grund)}{/each}
                </ul>
            </section>
        {/if}
    {/if}
</div>
