<script>
    /**
     * Ein Fach wählen — Suchfeld mit Vorschlägen (Combobox nach WAI-ARIA), Icon und Fachfarbe
     * (0.63, AY Teil 2). Für lange Fachlisten statt eines Auswahlfelds. Die Such- und
     * Tastaturlogik teilt sie mit `ChipAuswahl` (`$lib/chip_auswahl.js`).
     *
     * Props:
     * - faecher: [{ id, name, fach_code, icon, color }]
     * - wert: gewählter `fach_code` ("" = keins)
     * - onwahl(fach_code): bei Wahl und beim Leeren ("")
     * - id: Kennung des Suchfelds (für <label for>)
     *
     * Tastatur: Pfeile wählen einen Vorschlag, Enter übernimmt, Escape schließt die Liste.
     */
    import { X } from "@lucide/svelte";
    import SubjectIcon from "$lib/components/SubjectIcon.svelte";
    import { naechsterFokus, vorschlaege } from "$lib/chip_auswahl.js";
    import { fachToenung } from "$lib/absprachen.js";

    let { faecher = [], wert = "", onwahl = () => {}, id } = $props();

    let eingabe = $state("");
    let offen = $state(false);
    let fokus = $state(-1);
    let feld = $state(null);

    const eintraege = $derived(faecher.map((f) => ({ ...f, wert: f.fach_code })));
    const liste = $derived(vorschlaege(eintraege, [], eingabe));
    const gewaehlt = $derived(eintraege.find((f) => f.wert === wert) ?? null);
    const listeId = $derived(`${id}-vorschlaege`);

    function waehle(code) {
        onwahl(code);
        eingabe = "";
        offen = false;
        fokus = -1;
    }

    async function leeren() {
        onwahl("");
        await Promise.resolve();
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
        }
    }
</script>

{#if gewaehlt}
    <!-- Als Block, damit die Marke wie das Suchfeld unter der Beschriftung steht. -->
    <span
        class="flex w-fit items-center gap-1.5 rounded border px-2 py-1 text-sm
               text-light-tx dark:text-dark-tx border-light-ui-3 dark:border-dark-ui-3"
        style={fachToenung(gewaehlt.color)}
    >
        <SubjectIcon name={gewaehlt.icon} size={14} color={gewaehlt.color} />
        {gewaehlt.name}
        <button
            type="button"
            onclick={leeren}
            aria-label="{gewaehlt.name} abwählen"
            class="rounded text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx
                   focus:outline-none focus:ring-2 focus:ring-primary"
        >
            <X class="w-3.5 h-3.5" />
        </button>
    </span>
{:else}
    <div class="relative">
        <input
            bind:this={feld}
            {id}
            type="text"
            bind:value={eingabe}
            onkeydown={taste}
            onfocus={() => (offen = true)}
            onblur={() => { offen = false; fokus = -1; }}
            oninput={() => { offen = true; fokus = liste.length ? 0 : -1; }}
            placeholder="Fach suchen …"
            role="combobox"
            aria-expanded={offen && liste.length > 0}
            aria-controls={listeId}
            aria-autocomplete="list"
            aria-activedescendant={fokus >= 0 ? `${listeId}-${fokus}` : undefined}
            autocomplete="off"
            class="w-full text-sm rounded border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg
                   text-light-tx dark:text-dark-tx px-2 py-1 placeholder:text-light-tx-2 dark:placeholder:text-dark-tx-2
                   focus:outline-none focus:ring-2 focus:ring-primary"
        />
        {#if offen && liste.length > 0}
            <ul
                id={listeId}
                role="listbox"
                aria-label="Fächer"
                class="absolute z-20 mt-1 w-full max-h-56 overflow-y-auto rounded border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg dark:bg-dark-bg shadow"
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
                        <SubjectIcon name={f.icon} size={14} color={f.color} />
                        {f.name}
                    </li>
                {/each}
            </ul>
        {/if}
    </div>
{/if}
