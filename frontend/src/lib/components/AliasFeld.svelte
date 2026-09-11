<script>
    /**
     * Weitere Namen eines Bausteins — Chips plus Eingabezeile.
     *
     * **Warum eine eigene Komponente.** Die Aliase waren bis Migration 0057 ein
     * Metadatenfeld vom Typ `liste` und bekamen ihre Oberfläche von der generischen
     * Feldschleife des Sammlungs-Editors. Jetzt sind sie eine Eigenschaft **jedes**
     * Knotens — wie Titel oder Status — und werden an zwei Stellen gepflegt: im
     * Sammlungs-Editor und im allgemeinen Knoteneditor. Als Komponente steht die
     * Eingabe einmal da; als Kopie liefen die beiden auseinander.
     *
     * Der Wert ist ein Array; die Reihenfolge zählt (sie geht bei `methode` und
     * `operator` in den Embedding-Input ein), deshalb wird angehängt und nicht sortiert.
     */
    let {
        aliase = $bindable([]),
        disabled = false,
        id = "aliase",
        hinweis = null,
    } = $props()

    let eingabe = $state("")

    function ergaenzen() {
        const wert = eingabe.trim()
        eingabe = ""
        if (!wert) return
        // Dublettenprüfung wie im Backend: klein und ohne doppelte Leerzeichen.
        const schluessel = wert.toLowerCase().split(/\s+/).join(" ")
        const vorhanden = aliase.some(
            (a) => a.toLowerCase().split(/\s+/).join(" ") === schluessel,
        )
        if (vorhanden) return
        aliase = [...aliase, wert]
    }

    function entfernen(i) {
        aliase = aliase.filter((_, j) => j !== i)
    }
</script>

<div>
    <label
        for={id}
        class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
    >
        Andere Bezeichnungen
    </label>
    {#if hinweis}
        <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mb-1">{hinweis}</p>
    {/if}

    {#if aliase.length}
        <div class="flex flex-wrap gap-1.5 mb-2">
            {#each aliase as eintrag, i (eintrag)}
                <span
                    class="inline-flex items-center gap-1 px-2 py-0.5 text-xs
                           rounded-full border border-light-ui-3
                           dark:border-dark-ui-3 text-light-tx dark:text-dark-tx"
                >
                    {eintrag}
                    {#if !disabled}
                        <button
                            type="button"
                            onclick={() => entfernen(i)}
                            class="text-light-tx-2 dark:text-dark-tx-2
                                   hover:text-light-re dark:hover:text-dark-re"
                            aria-label="{eintrag} entfernen">×</button
                        >
                    {/if}
                </span>
            {/each}
        </div>
    {/if}

    <input
        {id}
        {disabled}
        bind:value={eingabe}
        onkeydown={(e) => {
            if (e.key === "Enter") {
                e.preventDefault()
                ergaenzen()
            }
        }}
        onblur={ergaenzen}
        placeholder="Eingeben und Enter"
        class="w-full px-3 py-2 text-sm rounded-md border border-light-ui-3
               dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg
               text-light-tx dark:text-dark-tx disabled:opacity-50"
    />
</div>
