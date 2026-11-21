<script>
    /**
     * Bevorzugte Modelle der Lehrkraft (0.51, Päckchen AV Schritt 7) — Abschnitt im Profil.
     *
     * Zwei Vorlieben: für freie Chats und für Planungs-Assistenten. Sie gelten für **neue**
     * Chats; im Chat lässt sich weiter umstellen. Der Vorgabe-Eintrag entfernt die Vorliebe.
     * Für Planungs-Assistenten nur Modelle mit Funktionen (⚙) — der Server prüft das beim
     * Speichern auch (`pruefe_bevorzugtes_modell`).
     *
     * Gestaltung wie die übrigen Abschnitte des Profils (Überschrift, Beschriftung, Auswahlfeld,
     * Hinweis) — nicht `ModellWahl`, dessen volle Fassung zum Assistenten-Editor gehört.
     *
     * Props:
     *   preferences — die geladenen Einstellungen
     *   loading     — noch nicht geladen
     *   speichern   — (schluessel, wert) => Promise; quittiert selbst
     *   quittung, quittungFehler — Schlüssel der letzten Rückmeldung
     */
    import { onMount } from "svelte";
    import { getModels } from "$lib/api.js";
    import { budget } from "$lib/stores/budget.js";
    import { eintragsText } from "$lib/modellangaben.js";

    let { preferences = {}, loading = false, speichern, quittung = null, quittungFehler = null } = $props();

    let modelle = $state([]);
    let fehler = $state(null);

    onMount(async () => {
        try {
            modelle = (await getModels()).models ?? [];
        } catch (e) {
            fehler = e?.message ?? "Modelle konnten nicht geladen werden.";
        }
    });

    const FELDER = $derived([
        {
            schluessel: "modell_frei",
            label: "Für freie Chats",
            vorgabe: "Vorgabe der Schule",
            modelle,
            hinweis: "Neue Chats ohne Assistenten beginnen mit diesem Modell.",
        },
        {
            schluessel: "modell_planung",
            label: "Für Planungs-Assistenten",
            vorgabe: "Modell des Assistenten",
            modelle: modelle.filter((m) => m.supports_function_calling !== false),
            hinweis: "Neue Chats mit Jahres-, Stunden- oder Curriculumplanung. Nur Modelle mit ⚙ — sie können die Planung lesen und schreiben.",
        },
    ]);
</script>

<section class="mb-8">
    <h2 class="text-base font-semibold mb-3 text-light-tx-2 dark:text-dark-tx-2">
        Bevorzugte Modelle
    </h2>
    {#if fehler}
        <p class="text-sm text-light-re dark:text-dark-re mb-2">{fehler}</p>
    {/if}
    <div class="space-y-4">
        {#each FELDER as f (f.schluessel)}
            <div>
                <label
                    for="vorliebe-{f.schluessel}"
                    class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-2"
                >
                    {f.label}
                    {#if quittung === f.schluessel}<span class="ml-2 text-xs font-medium text-light-gr dark:text-dark-gr" aria-live="polite">✓ Gespeichert</span>{:else if quittungFehler === f.schluessel}<span class="ml-2 text-xs font-medium text-light-re dark:text-dark-re" aria-live="polite">Nicht gespeichert</span>{/if}
                </label>
                <select
                    id="vorliebe-{f.schluessel}"
                    value={preferences?.[f.schluessel] ?? ""}
                    onchange={(e) => speichern(f.schluessel, e.target.value || null)}
                    class="w-full max-w-sm px-3 py-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx
                       focus:outline-none focus:ring-2 focus:ring-primary"
                    disabled={loading}
                >
                    <option value="">{f.vorgabe}</option>
                    {#each f.modelle as m (m.id)}
                        <option value={m.id}>{eintragsText(m, $budget?.eur_usd_rate, $budget?.einheiten_je_euro)}</option>
                    {/each}
                </select>
                <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mt-2 max-w-prose">{f.hinweis}</p>
            </div>
        {/each}
        <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 max-w-prose">
            Im Chat kannst du jederzeit umstellen; die Wahl dort gilt für die eine Unterhaltung.
        </p>
    </div>
</section>
