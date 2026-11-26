<script>
    /**
     * Fachfilter für Fachlisten der Bibliothek (Curricula seit 0.46; Jahresverlaufspläne seit 0.59,
     * BD Schritt 7): „Meine Fächer“, „Alle Fächer“ oder ein bestimmtes Fach. Eine Stelle für beide
     * Seiten, damit die Filter nicht auseinanderlaufen. Welche Fächer dann sichtbar sind, rechnet
     * `faecherFiltern` (`$lib/curriculum_baender.js`).
     *
     * Props:
     * - `faecher`: alle Fächer (`{id, name}`)
     * - `eigene`: IDs der eigenen Fächer (Unterrichtsgruppen und Fachschaften)
     * - `wert`: aktueller Filter, `eigene` oder `alle`
     * - `fachWahl` (bindable): gewähltes Fach als Zeichenkette, leer ohne Wahl
     * - `onwahl(wert)`: „Meine Fächer“ oder „Alle Fächer“ geklickt
     */
    let { faecher = [], eigene = [], wert = 'alle', fachWahl = $bindable(''), onwahl = () => {} } = $props()

    // Auswahl im Dropdown: bei „Meine Fächer“ nur die eigenen.
    const auswahl = $derived([...(faecher ?? [])]
        .filter((f) => wert !== 'eigene' || eigene.includes(f.id))
        .sort((a, b) => a.name.localeCompare(b.name, 'de')))
</script>

<div class="flex flex-wrap items-center gap-2 mb-5" data-abschnitt="faecherfilter">
    {#each [['eigene', 'Meine Fächer'], ['alle', 'Alle Fächer']] as [w, text] (w)}
        <button
            type="button"
            onclick={() => { fachWahl = ''; onwahl(w) }}
            aria-pressed={!fachWahl && wert === w}
            class="px-3 py-1.5 text-sm rounded-md border transition-colors
                   {!fachWahl && wert === w
                       ? 'border-primary dark:border-primary-dark text-light-tx dark:text-dark-tx bg-light-ui-2 dark:bg-dark-ui-2 font-medium'
                       : 'border-light-ui-3 dark:border-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
        >
            {text}
        </button>
    {/each}
    <select
        bind:value={fachWahl}
        aria-label="Fach wählen"
        class="pl-2 pr-8 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg
               text-light-tx dark:text-dark-tx"
    >
        <option value="">Fach wählen …</option>
        {#each auswahl as f (f.id)}
            <option value={String(f.id)}>{f.name}</option>
        {/each}
    </select>
</div>
