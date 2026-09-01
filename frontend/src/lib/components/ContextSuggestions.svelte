<script>
    /**
     * Das Vorschlagsfenster des Suchknopfs im Chat (ADR-017, AP8).
     *
     * Es steht **im Fluss über dem Eingabefeld** — jede Zeile, die es wachsen lässt,
     * schiebt das Eingabefeld nach unten. Deshalb ist seine Höhe an den Viewport
     * gebunden und nur die Trefferliste scrollt: Kopfzeile und Aktionsleiste bleiben
     * stehen, sodass „Hinzufügen" in jeder Bildschirmhöhe erreichbar ist, ohne erst ans
     * Listenende zu scrollen. Bei Anzeigelimit 30 (Profil-Einstellung, Obergrenze in
     * `backend/app/preferences/service.py`) liefert der Umschlag bis zu 60 Treffer —
     * gemessen am 01.09.2026 mit „nennen": 59 Treffer, 62 Listenzeilen. Ohne Deckel
     * deckte das Fenster den halben Chat zu.
     */
    import { CheckSquare, Square } from "lucide-svelte";

    import { mehrdeutigeFassungen } from "$lib/bp_fassung.js";
    import {
        alleTreffer,
        gueltigeAuswahl,
        vorschlagsAbschnitte,
    } from "$lib/umschlag.js";
    import ContextNodeLabel from "./ContextNodeLabel.svelte";

    let { umschlag = null, frage = "", onconfirm, ondismiss } = $props();

    const abschnitte = $derived(vorschlagsAbschnitte(umschlag));
    const treffer = $derived(alleTreffer(abschnitte));

    // Die Vorschlagssuche kennt keinen Jahrgang, kann also beide Fassungen derselben
    // Kompetenz vorschlagen — dann muss die Fassung dabeistehen.
    const fassungen = $derived(mehrdeutigeFassungen(treffer));

    // Die Auswahl darf nicht an der Lebensdauer der Komponente hängen — warum, steht
    // bei `gueltigeAuswahl`. Kurz: Eine zweite Suche bei offenem Fenster tauscht nur
    // die Prop aus, und eine beim Erzeugen gesetzte Auswahl hielte alte IDs fest.
    let handauswahl = $state(null);
    const gewaehlt = $derived(gueltigeAuswahl(handauswahl, umschlag, abschnitte));

    const alleGewaehlt = $derived(
        treffer.length > 0 && gewaehlt.size === treffer.length,
    );

    function setzen(ids) {
        handauswahl = { umschlag, ids };
    }

    function umschalten(nodeId) {
        const ids = new Set(gewaehlt);
        ids.has(nodeId) ? ids.delete(nodeId) : ids.add(nodeId);
        setzen(ids);
    }

    function alleUmschalten() {
        setzen(alleGewaehlt ? new Set() : new Set(treffer.map((t) => t.node_id)));
    }

    function bestaetigen() {
        onconfirm?.(treffer.filter((t) => gewaehlt.has(t.node_id)));
    }

    // Was hier gekürzt ist, steht auf der Suchseite vollständig — mit derselben Anfrage.
    const sucheHref = $derived(
        `/knowledge/search?q=${encodeURIComponent(frage)}`,
    );
</script>

<div
    class="flex flex-col max-h-[35dvh] sm:max-h-[40dvh]
           rounded-lg border border-light-ui-3 dark:border-dark-ui-3
           bg-light-bg-2 dark:bg-dark-bg-2 text-sm"
>
    <!-- Kopfzeile: außerhalb des Scrollbereichs, damit sie beim Blättern stehenbleibt. -->
    <div class="shrink-0 flex items-center gap-2 px-3 pt-3 pb-2">
        <p class="flex-1 text-xs font-medium text-light-tx-2 dark:text-dark-tx-2">
            Gefundene Bausteine — welche sollen in den Kontext?
        </p>
        {#if treffer.length}
            <button
                type="button"
                onclick={alleUmschalten}
                class="shrink-0 flex items-center gap-1 px-1.5 py-1 rounded text-xs
                       text-light-tx-2 dark:text-dark-tx-2
                       hover:bg-light-ui dark:hover:bg-dark-ui"
            >
                {#if alleGewaehlt}
                    <Square class="w-3.5 h-3.5" /> Keine
                {:else}
                    <CheckSquare class="w-3.5 h-3.5" /> Alle
                {/if}
            </button>
        {/if}
    </div>

    {#if !abschnitte.length}
        <p class="px-3 pb-3 text-xs text-light-tx-2 dark:text-dark-tx-2">
            Kein Baustein gefunden.
        </p>
    {:else}
        <!-- `min-h-0` ist Pflicht: Ohne es wächst ein Flex-Kind auf seine Inhaltshöhe,
             und die Höhenbegrenzung des Fensters bliebe wirkungslos. -->
        <div class="flex-1 min-h-0 overflow-y-auto px-3">
            {#each abschnitte as abschnitt (abschnitt.schluessel)}
                <section class="mb-2 last:mb-0">
                    <h3
                        class="text-xs font-medium text-light-tx dark:text-dark-tx
                               mb-1 mt-1"
                    >
                        {abschnitt.titel}
                    </h3>
                    <ul class="flex flex-col">
                        {#each abschnitt.treffer as node (node.node_id)}
                            <li>
                                <!-- Zeilenhöhe als Touch-Ziel: auf dem Telefon ist die
                                     Checkbox allein zu klein, das ganze Label schaltet. -->
                                <label
                                    class="flex items-center gap-2 cursor-pointer rounded
                                           px-1 py-2 sm:py-1 min-h-10 sm:min-h-0
                                           hover:bg-light-ui dark:hover:bg-dark-ui"
                                >
                                    <input
                                        type="checkbox"
                                        checked={gewaehlt.has(node.node_id)}
                                        onchange={() => umschalten(node.node_id)}
                                        class="shrink-0 w-4 h-4 accent-primary"
                                    />
                                    <ContextNodeLabel
                                        {node}
                                        fassung={fassungen.get(node.node_id)}
                                        titleClass="truncate text-light-tx dark:text-dark-tx"
                                    />
                                </label>
                            </li>
                        {/each}
                    </ul>
                    <p
                        class="text-xs text-light-tx-2 dark:text-dark-tx-2 px-1 mt-0.5"
                    >
                        {abschnitt.fussnote}
                        {#if abschnitt.gekuerzt}
                            —
                            <a
                                href={sucheHref}
                                class="text-light-bl dark:text-dark-bl hover:underline"
                            >
                                alle auf der Suchseite
                            </a>
                        {/if}
                    </p>
                </section>
            {/each}
        </div>
    {/if}

    <!-- Aktionsleiste: außerhalb des Scrollbereichs. Bestätigen ohne Scrollen. -->
    <div
        class="shrink-0 flex gap-2 justify-end px-3 py-2
               border-t border-light-ui-3 dark:border-dark-ui-3"
    >
        <button
            type="button"
            onclick={ondismiss}
            class="px-3 py-1.5 rounded text-xs
                   text-light-tx-2 dark:text-dark-tx-2
                   hover:bg-light-ui dark:hover:bg-dark-ui
                   border border-light-ui-3 dark:border-dark-ui-3"
        >
            Abbrechen
        </button>
        <button
            type="button"
            onclick={bestaetigen}
            disabled={gewaehlt.size === 0}
            class="px-3 py-1.5 rounded text-xs
                   bg-primary dark:bg-primary-dark text-white
                   hover:opacity-90
                   disabled:opacity-40 disabled:cursor-not-allowed"
        >
            Hinzufügen ({gewaehlt.size})
        </button>
    </div>
</div>
