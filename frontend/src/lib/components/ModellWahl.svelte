<script>
    /**
     * Der Modellwähler — **ein** Baustein für Chat und Assistenten-Editor (0.27, Schritt 3).
     *
     * ⚠️ Bis 0.27 bauten beide ein eigenes `<select>` mit eigenen Klassen; geteilt war nur
     * die Beschriftung der Einträge (`eintragsText`). Eine Gestaltungsänderung oder ein
     * zusätzlicher Hinweis war damit zweimal zu machen.
     *
     * Zwei Varianten:
     * - `kompakt` (Chat): klein, in einer Zeile mit der Beschriftung; ohne Modelle ein
     *   Platzhaltereintrag (`leerText`), rot, wenn auch kein Modell gesetzt ist.
     * - `voll` (Editor): volle Breite, optional ein Vorgabe-Eintrag (`vorgabe`, etwa
     *   „Schulweiter Standard" mit Wert `""`) und darunter die Angaben zum gewählten Modell.
     *   Ohne Modellliste ein Textfeld, damit sich ein Name trotzdem eintragen lässt.
     *
     * Die Angabenzeile gibt es bewusst nur in `voll` (F7, 31.10.2026): Im Chat ist der Platz
     * knapp; die Kosten eines Assistenten stehen dort am Assistenten selbst.
     */
    import { budget } from "$lib/stores/budget.js";
    import { kurshinweis } from "$lib/einheiten.js";
    import { angaben, eintragsText } from "$lib/modellangaben.js";

    let {
        id,
        modelle = [],
        wert = $bindable(""),
        variante = "kompakt",
        disabled = false,
        onchange = undefined,
        vorgabe = null,
        leerText = "Kein Modell verfügbar",
        platzhalter = "",
    } = $props();

    const kompakt = $derived(variante === "kompakt");
    const modellAngaben = $derived(
        kompakt
            ? []
            : angaben(
                  modelle.find((m) => m.id === wert),
                  $budget?.eur_usd_rate,
                  $budget?.einheiten_je_euro,
              ),
    );
</script>

{#if kompakt}
    <div class="flex items-center gap-1.5 shrink-0">
        <label for={id} class="text-xs text-light-tx-2 dark:text-dark-tx-2 whitespace-nowrap">
            Modell
        </label>
        <select
            {id}
            bind:value={wert}
            {disabled}
            {onchange}
            class="rounded border border-light-ui-3 dark:border-dark-ui-3
                   bg-light-bg-2 dark:bg-dark-bg-2
                   px-1.5 py-0.5 text-xs disabled:opacity-60
                   {modelle.length === 0 && !wert
                ? 'text-light-re dark:text-dark-re'
                : 'text-light-tx dark:text-dark-tx'}"
        >
            {#if modelle.length > 0}
                {#each modelle as model (model.id)}
                    <option value={model.id}
                        >{eintragsText(model, $budget?.eur_usd_rate, $budget?.einheiten_je_euro)}</option
                    >
                {/each}
            {:else}
                <option value={wert || ""}>{wert || leerText}</option>
            {/if}
        </select>
    </div>
{:else}
    <label for={id} class="block text-sm font-medium text-light-tx dark:text-dark-tx">
        Modell
    </label>
    {#if modelle.length > 0}
        <select
            {id}
            bind:value={wert}
            {disabled}
            {onchange}
            class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                   bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                   px-3 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
        >
            {#if vorgabe !== null}
                <option value="">{vorgabe}</option>
            {/if}
            {#each modelle as model (model.id)}
                <option value={model.id}
                    >{eintragsText(model, $budget?.eur_usd_rate, $budget?.einheiten_je_euro)}</option
                >
            {/each}
        </select>
        <!-- Angaben zum **gewählten** Modell. Ein `<option>` erlaubt keine Gestaltung,
             deshalb steht hier, was man zum Entscheiden braucht — und nur, was bekannt ist. -->
        {#if modellAngaben.length > 0}
            <ul class="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-light-tx-2 dark:text-dark-tx-2">
                {#each modellAngaben as a (a.was)}
                    <li><span class="font-medium">{a.was}:</span> {a.wert}</li>
                {/each}
            </ul>
            <details class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                <summary class="cursor-pointer">Was bedeuten diese Angaben?</summary>
                <div class="mt-1 space-y-1">
                    <p>
                        <strong>Kosten</strong> sind eine Schätzung an einer mittleren Nachricht —
                        abgerechnet wird nach tatsächlichem Verbrauch. {kurshinweis(
                            $budget?.einheiten_je_euro,
                        )}.
                    </p>
                    <p>
                        Das <strong>Kontextfenster</strong> sagt, wie viel Vorgeschichte das Modell
                        auf einmal sehen kann. Fehlt die Angabe, meldet der Proxy sie nicht — sie
                        lässt sich in der LiteLLM-Konfiguration eintragen.
                    </p>
                    <p>
                        Sind die <strong>Fähigkeiten</strong> nicht nutzbar, wirken die Schalter
                        weiter unten nicht: Der Assistent kann dann weder im Wissensspeicher suchen
                        noch Unterricht planen.
                    </p>
                </div>
            </details>
        {/if}
    {:else}
        <input
            {id}
            bind:value={wert}
            {disabled}
            type="text"
            placeholder={platzhalter}
            class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                   bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                   px-3 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
        />
    {/if}
{/if}
