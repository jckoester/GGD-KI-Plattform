<script>
    /**
     * Querverweise des Bildungsplans in andere Fächer an einer Kompetenz (AY Teil 1).
     *
     * Zugeklappt je Fach eine kleine Marke (Icon und Kürzel in Fachfarbe), aufgeklappt die
     * Liste mit Stufen, Nummer und Titel, verlinkt auf den Baustein. Kein Dauertext: Die
     * Tabellen, in denen sie steht, sind schon dicht (F8, Jan 25.11.2026).
     *
     * liste: Einträge aus `POST /context/querverweise` für genau eine Kompetenz.
     */
    import { page } from "$app/stores";
    import { bausteinPfad } from "$lib/rueckweg.js";
    import {
        bezugText, faecher, kuenftigText, zeilenText, fachKuerzel, fundstelleText, fundstellePfad,
    } from "$lib/querverweise.js";
    import SubjectIcon from "./SubjectIcon.svelte";

    let { liste = [] } = $props();

    let offen = $state(false);
    const listenId = `qv-${Math.random().toString(36).slice(2, 9)}`;
    const marken = $derived(faecher(liste));
    const bezug = $derived(bezugText(liste));

    // Fachfarbe als Rahmen und leichte Tönung — Schrift bleibt in den Text-Tokens, damit sie
    // auf jeder Fachfarbe und in beiden Modi lesbar ist.
    function toenung(farbe) {
        if (!farbe) return "";
        const hex = /^#[0-9a-f]{6}$/i.test(farbe) ? `background-color: ${farbe}1f;` : "";
        return `border-color: ${farbe}; ${hex}`;
    }
</script>

{#if liste.length}
    <button
        type="button"
        class="inline-flex items-center gap-1 align-baseline ml-0.5 mr-1 rounded
               focus:outline-none focus-visible:ring-2 focus-visible:ring-primary dark:focus-visible:ring-primary-dark"
        aria-expanded={offen}
        aria-controls={listenId}
        title={bezug}
        aria-label={bezug}
        onclick={() => (offen = !offen)}
    >
        {#each marken as m (m.fach_id)}
            <span
                class="inline-flex items-center gap-0.5 rounded border px-1 text-[11px] leading-4
                       text-light-tx-2 dark:text-dark-tx-2 border-light-ui-3 dark:border-dark-ui-3"
                style={toenung(m.color)}
            >
                <SubjectIcon name={m.icon} size={11} color={m.color} />
                {m.kuerzel}{#if m.anzahl > 1}<span class="opacity-70">&nbsp;{m.anzahl}</span>{/if}
            </span>
        {/each}
    </button>
    {#if offen}
        <ul
            id={listenId}
            class="block my-1 space-y-0.5 text-xs text-light-tx dark:text-dark-tx
                   border-l-2 border-light-ui-3 dark:border-dark-ui-3 pl-2"
        >
            {#each liste as e (e.ziel_id)}
                <li>
                    <div class="flex items-start gap-1">
                        <SubjectIcon name={e.icon} size={12} color={e.color} class="mt-0.5 shrink-0" />
                        <a
                            href={bausteinPfad(e.ziel_id, $page.url)}
                            class="underline text-light-bl dark:text-dark-bl hover:text-primary dark:hover:text-primary-dark"
                        >
                            <span class="font-medium">{fachKuerzel(e)}</span>
                            {zeilenText(e)}
                        </a>
                        {#if kuenftigText(e)}
                            <span class="text-light-tx-2 dark:text-dark-tx-2">({kuenftigText(e)})</span>
                        {/if}
                    </div>
                    <!-- Wo das andere Fach die Stelle behandelt (Schritt 5) -->
                    {#if e.fundstellen?.length}
                        <ul class="ml-4 text-light-tx-2 dark:text-dark-tx-2">
                            {#each e.fundstellen as f (f.curriculum_id + f.kapitel_id)}
                                <li>
                                    behandelt in
                                    <a href={fundstellePfad(f)} class="underline hover:text-primary dark:hover:text-primary-dark"
                                        >{fundstelleText(f)}</a>
                                </li>
                            {/each}
                        </ul>
                    {:else if e.fundstellen}
                        <div class="ml-4 text-light-tx-2 dark:text-dark-tx-2">
                            in keinem Curriculum von {e.fach} verknüpft
                        </div>
                    {/if}
                </li>
            {/each}
        </ul>
    {/if}
{/if}
