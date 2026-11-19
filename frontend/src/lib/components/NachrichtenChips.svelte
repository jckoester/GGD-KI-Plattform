<script>
    // Was an der nächsten Nachricht hängt, unter dem Eingabefeld (0.49): Bausteine, Produkte
    // aus der Werkstatt und hochgeladene Dateien in **einer** Reihe.
    //
    // Eingeklappt wird nach Höhe, nicht nach Anzahl: Wie viele Chips in eine Zeile passen,
    // hängt von Breite und Titel ab. Bis 0.48 klappten nur die Bausteine ab fünf Stück ein;
    // mit Produkten und Anhängen daneben lief die Reihe auf dem Telefon trotzdem über
    // (Jan, 19.11.2026: unter der Eingabe ist Platz für drei Zeilen). Eingeklappt also zwei
    // Zeilen Chips und eine Zeile für „N weitere“.
    //
    // Eingeklappt wird **nur, wenn es knapp ist** (`einklappen`, auf der Chat-Seite `kompakt`:
    // sichtbare Höhe unter 560 px, etwa Telefon oder iPad mit offener Tastatur). Sonst stehen
    // alle Chips da, gedeckelt an einem Fünftel der sichtbaren Höhe (Jan, 19.11.2026: immer
    // einklappen hilft nicht).
    import { tick } from "svelte";
    import { ChevronDown, ChevronUp } from "lucide-svelte";
    import ContextChips from "./ContextChips.svelte";
    import ProduktChips from "./ProduktChips.svelte";
    import AttachmentChip from "./AttachmentChip.svelte";
    import { ZWEI_ZEILEN_PX, versteckteChips } from "$lib/chip_form.js";

    let {
        nodes = [],
        produkte = [],
        anhaenge = [],
        onremoveNode,
        onremoveProdukt,
        onremoveAnhang,
        disabled = false,
        einklappen = false,
    } = $props();

    let feld = $state(null);
    let offen = $state(false);
    let hatMehr = $state(false);
    let versteckt = $state(0);

    const anzahl = $derived(nodes.length + produkte.length + anhaenge.length);

    async function messen() {
        await tick();
        if (!feld) return;
        hatMehr = einklappen && feld.scrollHeight > ZWEI_ZEILEN_PX + 1;
        versteckt = offen ? 0 : versteckteChips(feld);
        if (!hatMehr) offen = false;
    }

    // Neu messen, wenn sich der Inhalt ändert (die Höhe des Rahmens bleibt dabei oft gleich) …
    $effect(() => {
        void anzahl;
        void offen;
        void einklappen;
        messen();
    });

    // … und wenn sich die Breite ändert (Drehen, Fenster).
    $effect(() => {
        if (!feld) return;
        const beobachter = new ResizeObserver(() => messen());
        beobachter.observe(feld);
        return () => beobachter.disconnect();
    });
</script>

{#if anzahl > 0}
    <div>
        <!-- Ausgeklappt gedeckelt an der **sichtbaren** Höhe (`stores/geraet.js`), nicht an
             `dvh` — mit offener Tastatur wäre ein Fünftel der vollen Höhe zu viel. -->
        <div
            bind:this={feld}
            class="relative flex flex-wrap gap-1.5 {einklappen && !offen
                ? 'max-h-[3.75rem] overflow-hidden'
                : 'max-h-[calc(var(--sichtbare-hoehe,100dvh)*0.2)] overflow-y-auto'}"
        >
            <ContextChips {nodes} onremove={onremoveNode} {disabled} />
            <ProduktChips {produkte} onremove={onremoveProdukt} {disabled} />
            {#each anhaenge as att (att.id)}
                <AttachmentChip
                    filename={att.filename}
                    status={att.status}
                    error={att.error}
                    onremove={() => onremoveAnhang?.(att.id)}
                />
            {/each}
        </div>
        {#if hatMehr}
            <button
                type="button"
                onclick={() => (offen = !offen)}
                class="mt-1 inline-flex items-center gap-1 text-xs
                       text-light-tx-2 dark:text-dark-tx-2
                       hover:text-light-tx dark:hover:text-dark-tx"
                aria-expanded={offen}
            >
                {#if offen}
                    <ChevronUp class="w-3 h-3" /> weniger
                {:else}
                    <ChevronDown class="w-3 h-3" />
                    {versteckt > 0 ? `${versteckt} weitere` : "alle zeigen"}
                {/if}
            </button>
        {/if}
    </div>
{/if}
