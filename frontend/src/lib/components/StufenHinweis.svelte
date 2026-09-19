<script>
    /**
     * Kontextnaher Einstieg: Diese Seite gehört zu einer Stufe, die noch nicht
     * eingeblendet ist.
     *
     * ⚠️ **Kein Zugriffsschutz.** Die Seite ist erreichbar und wird vollständig
     * angezeigt — verborgen war nur der Einstieg in der Navigation (Leitprinzip 1 der
     * Konzeptnotiz: Anzeige-Filter, keine Berechtigung). Der Hinweis erklärt also, warum
     * die Oberfläche anders aussieht als in einer Anleitung beschrieben, und bietet an,
     * das zu ändern. Er steht deshalb ÜBER dem Inhalt, nicht an seiner Stelle.
     */
    import { Info } from "lucide-svelte";
    import { setzeStufe, stufenRegistry, uiStufe, stufeVon } from "$lib/stores/uiLevel.js";

    let { eintrag } = $props();

    const noetig = $derived(stufeVon($stufenRegistry, eintrag));
    const stufe = $derived(
        noetig == null
            ? null
            : $stufenRegistry?.stufen?.find((s) => s.stufe === noetig),
    );
    // Nur zeigen, wenn die Stufe wirklich über der eigenen liegt. `$uiStufe === null`
    // heißt „kein Filter" — dann ist nichts verborgen und nichts zu erklären.
    const verborgen = $derived(
        $uiStufe != null && noetig != null && noetig > $uiStufe,
    );
</script>

{#if verborgen && stufe}
    <div
        class="mb-4 flex items-start gap-2 rounded border p-3 text-sm
               bg-light-bl-bg dark:bg-dark-bl-bg
               border-light-bl dark:border-dark-bl
               text-light-tx dark:text-dark-tx"
    >
        <Info size={16} class="mt-0.5 shrink-0 text-light-bl dark:text-dark-bl" />
        <span>
            Diese Seite gehört zu <b>Stufe {stufe.stufe}: {stufe.name}</b> und ist in
            deiner Navigation noch nicht eingeblendet — benutzen kannst du sie trotzdem.
            <button
                onclick={() => setzeStufe(stufe.stufe)}
                class="underline hover:no-underline"
            >
                Dauerhaft einblenden
            </button>
        </span>
    </div>
{/if}
