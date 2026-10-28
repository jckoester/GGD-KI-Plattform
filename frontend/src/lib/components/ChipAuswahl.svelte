<script>
    /**
     * Mehrere Einträge wählen: gewählte als Chips, darunter ein Suchfeld mit Vorschlägen
     * (Combobox nach WAI-ARIA). Skaliert auf viele Einträge, anders als eine Checkbox-Liste.
     * Nutzer: Fächer für Operatoren (AF), Rückfall-Assistenten (C2).
     *
     * Props:
     * - eintraege: [{ wert, name, color? }] — die Auswahl (Fächer: `faecherAlsEintraege`)
     * - gewaehlt: Werte (bindable)
     * - id: Kennung des Suchfelds (für das <label for> des Aufrufers)
     * - beschreibung: Kennung eines erklärenden Textes (aria-describedby), optional
     * - platzhalter: Text im leeren Suchfeld
     * - farbpunkt: Farbpunkt vor dem Namen zeigen (Fächer ja, Assistenten nein)
     *
     * Tastatur: Pfeile wählen einen Vorschlag, Enter übernimmt, Escape schließt die Liste,
     * Backspace im leeren Feld entfernt den letzten Chip. Die Logik steht in
     * `$lib/chip_auswahl.js` (mit Tests).
     */
    import { X } from "lucide-svelte";
    import SubjectDot from "$lib/components/SubjectDot.svelte";
    import {
        anzeige,
        hinzu,
        naechsterFokus,
        vorschlaege,
        weg,
    } from "$lib/chip_auswahl.js";

    let {
        eintraege = [],
        gewaehlt = $bindable([]),
        id,
        beschreibung = undefined,
        platzhalter = "Hinzufügen…",
        farbpunkt = true,
    } = $props();

    let eingabe = $state("");
    let offen = $state(false);
    let fokus = $state(-1);
    let feld = $state(null);

    const liste = $derived(vorschlaege(eintraege, gewaehlt, eingabe));
    const listeId = $derived(`${id}-vorschlaege`);

    function waehle(wert) {
        gewaehlt = hinzu(gewaehlt, wert);
        eingabe = "";
        fokus = -1;
        feld?.focus();
    }

    function entferne(wert) {
        gewaehlt = weg(gewaehlt, wert);
        feld?.focus();
    }

    function taste(e) {
        switch (e.key) {
            case "ArrowDown":
            case "ArrowUp":
                e.preventDefault();
                offen = true;
                fokus = naechsterFokus(fokus, liste.length, e.key === "ArrowDown" ? 1 : -1);
                break;
            case "Enter":
                if (offen && fokus >= 0 && liste[fokus]) {
                    e.preventDefault();
                    waehle(liste[fokus].wert);
                }
                break;
            case "Escape":
                if (offen) {
                    e.preventDefault();
                    offen = false;
                    fokus = -1;
                }
                break;
            case "Backspace":
                if (!eingabe && gewaehlt.length) {
                    gewaehlt = gewaehlt.slice(0, -1);
                }
                break;
        }
    }
</script>

<div
    class="rounded border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg-2 dark:bg-dark-bg-2
           px-2 py-1.5 focus-within:ring-2 focus-within:ring-primary"
>
    <div class="flex flex-wrap items-center gap-1.5">
        {#each gewaehlt as wert (wert)}
            {@const f = anzeige(eintraege, wert)}
            <span
                class="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-sm
                       border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg
                       {f.bekannt ? 'text-light-tx dark:text-dark-tx' : 'text-light-tx-2 dark:text-dark-tx-2 italic'}"
                title={f.bekannt ? f.name : `${wert}: gibt es hier (noch) nicht`}
            >
                {#if farbpunkt}<SubjectDot color={f.color} />{/if}
                {f.name}
                <button
                    type="button"
                    onclick={() => entferne(wert)}
                    aria-label="{f.name} entfernen"
                    class="rounded-full text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx
                           dark:hover:text-dark-tx focus:outline-none focus:ring-2 focus:ring-primary"
                >
                    <X class="w-3.5 h-3.5" />
                </button>
            </span>
        {/each}
        <input
            bind:this={feld}
            {id}
            type="text"
            bind:value={eingabe}
            onkeydown={taste}
            onfocus={() => (offen = true)}
            onblur={() => { offen = false; fokus = -1; }}
            oninput={() => { offen = true; fokus = liste.length ? 0 : -1; }}
            placeholder={gewaehlt.length ? "" : platzhalter}
            role="combobox"
            aria-expanded={offen && liste.length > 0}
            aria-controls={listeId}
            aria-autocomplete="list"
            aria-activedescendant={fokus >= 0 ? `${listeId}-${fokus}` : undefined}
            aria-describedby={beschreibung}
            autocomplete="off"
            class="flex-1 min-w-[8rem] bg-transparent py-0.5 text-sm text-light-tx dark:text-dark-tx
                   placeholder:text-light-tx-2 dark:placeholder:text-dark-tx-2 focus:outline-none"
        />
    </div>
    {#if offen && liste.length > 0}
        <ul
            id={listeId}
            role="listbox"
            aria-label="Vorschläge"
            class="mt-1.5 max-h-56 overflow-y-auto rounded border border-light-ui-3 dark:border-dark-ui-3
                   bg-light-bg dark:bg-dark-bg"
        >
            {#each liste as f, i (f.wert)}
                <li
                    id="{listeId}-{i}"
                    role="option"
                    aria-selected={i === fokus}
                    onmousedown={(e) => { e.preventDefault(); waehle(f.wert); }}
                    class="flex items-center gap-2 px-3 py-1.5 text-sm cursor-pointer
                           text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                           {i === fokus ? 'bg-light-ui-2 dark:bg-dark-ui-2' : ''}"
                >
                    {#if farbpunkt}<SubjectDot color={f.color} />{/if}
                    {f.name}
                </li>
            {/each}
        </ul>
    {/if}
</div>
