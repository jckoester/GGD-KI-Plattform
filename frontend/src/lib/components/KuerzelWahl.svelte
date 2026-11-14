<script>
    /**
     * Auswahl des eigenen Stundenplan-Kürzels samt dem Satz, was damit geschieht.
     *
     * Aus der Seite „Unterricht“ gezogen (0.43, Plan Schritt 2), damit die Einrichtung dieselbe
     * Auswahl zeigt — kein zweites Eingabefeld für dieselbe Einstellung. Abschnitt, Überschrift
     * und Abgleich bleiben bei der Seite.
     *
     * Auswahl aus der geladenen Liste statt Freitext: Ein Tippfehler führte sonst zu einem
     * stillen Nicht-Abruf, den später niemand zuordnet.
     *
     * Props: `teachers` (Kürzel aus `getCalendarTeachers`), `kuerzel` (bindbar, gespeicherter
     * Wert), `disabled`.
     */
    import { patchPreferences } from "$lib/api.js";
    import { user } from "$lib/stores/user.js";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import SuccessBanner from "$lib/components/SuccessBanner.svelte";

    // ⚠️ `$bindable()` OHNE Vorgabe: Die Seite „Unterricht“ bindet `preferences.webuntis_kuerzel`,
    // und das ist bei Konten ohne Kürzel `undefined`. Mit Vorgabe bricht Svelte dann ab
    // (`props_invalid_value`) — das Feld fehlte (0.43, Schritt 2).
    let { teachers = [], kuerzel = $bindable(), disabled = false } = $props();

    let fehler = $state("");
    let gespeichert = $state(false);

    async function aendern(event) {
        const wert = event.target.value;
        fehler = "";
        gespeichert = false;
        try {
            await patchPreferences({ webuntis_kuerzel: wert });
            user.update((u) => ({
                ...u,
                preferences: { ...u?.preferences, webuntis_kuerzel: wert },
            }));
            kuerzel = wert;
            gespeichert = true;
        } catch (err) {
            fehler = err.message;
            // Anzeige auf den gespeicherten Stand zurücksetzen — sonst zeigt das Feld
            // eine Auswahl, die der Server abgelehnt hat.
            event.target.value = kuerzel ?? "";
        }
    }
</script>

<label
    for="webuntis-kuerzel"
    class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-2"
>
    Dein Kürzel im Stundenplan
</label>
<select
    id="webuntis-kuerzel"
    value={kuerzel ?? ""}
    onchange={aendern}
    class="w-full max-w-40 px-3 py-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3
           bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx
           focus:outline-none focus:ring-2 focus:ring-primary"
    {disabled}
>
    <option value="">— nicht zugeordnet —</option>
    {#each teachers as k (k)}
        <option value={k}>{k}</option>
    {/each}
</select>

<p class="mt-3 text-sm text-light-tx-2 dark:text-dark-tx-2 max-w-prose">
    Dein Kürzel wird ausschließlich verwendet, um deinen Stundenplan abzurufen
    (Wochenmuster, Ausfälle, Vertretungen). Es wird <strong>nicht</strong> an
    KI-Modelle übermittelt und erscheint in keinem Chat, keinem
    Assistenten-Kontext und keinem Wissensknoten. Reichst du einen Assistenten zur
    Freigabe ein, sehen die Admins dort dein Kürzel, damit sie wissen, wen sie fragen
    können. Du kannst es jederzeit entfernen; dann entfällt die Stundenplan-Übernahme.
</p>

{#if fehler}
    <div class="mt-3"><ErrorBanner message={fehler} /></div>
{:else if gespeichert}
    <div class="mt-3"><SuccessBanner message="Kürzel gespeichert." /></div>
{/if}
