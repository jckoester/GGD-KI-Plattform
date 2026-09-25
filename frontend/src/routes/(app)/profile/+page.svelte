<script>
    import PageBody from '$lib/components/PageBody.svelte'
    import { User, Sun, Moon, Monitor, ArrowLeft, Check, ChevronRight, Eye } from "lucide-svelte";
    import { themePref } from "$lib/stores/theme.js";
    import { user } from "$lib/stores/user.js";
    import { budget } from "$lib/stores/budget.js";
    import { zuwachsText, uebertragText } from "$lib/budget_text.js";
    import { myGroups, refreshMyGroups } from "$lib/stores/myGroups.js";
    import { subjectMap } from "$lib/stores/subjects.js";
    import {
        setzeStufe,
        stufenRegistry,
        uiStufe,
    } from "$lib/stores/uiLevel.js";
    import { patchPreferences, getPreferences } from "$lib/api.js";
    import { onMount } from "svelte";
    import Zugangstoken from "$lib/components/Zugangstoken.svelte";
    import { KACHELN, schalteKachel, zeigtKachel } from "$lib/stores/startkacheln.js";

    // Aufgelöste Plattform-Mitgliedschaften für die SSO-Diagnose, nach Typ gruppiert.
    const membershipGroups = $derived([
        { type: "subject_department", label: "Fachschaften" },
        { type: "teaching_group", label: "Unterrichtsgruppen" },
        { type: "school_class", label: "Klassen" },
    ].map((g) => ({
        ...g,
        items: ($myGroups ?? []).filter((m) => m.type === g.type),
    })));


    const themeOptions = [
        { value: "light", label: "Hell", Icon: Sun },
        { value: "dark", label: "Dunkel", Icon: Moon },
        { value: "system", label: "System", Icon: Monitor },
    ];

    const sidebarLimitOptions = [5, 10, 15, 20, 25];
    const contextSearchLimitOptions = [5, 8, 10, 15, 20, 30];
    const costGranularityOptions = [
        { value: "none", label: "Gar nicht" },
        { value: "conversation", label: "Pro Konversation" },
        { value: "message", label: "Pro Nachricht" },
        { value: "both", label: "Beides" },
    ];

    // User-Präferenzen laden
    let preferences = $state({});
    let loading = $state(true);

    // Formatierung: 2 Dezimalstellen, Komma als Trennzeichen
    function fmt(v) {
        if (v == null) return "–";
        return v.toLocaleString("de-DE", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }


    onMount(async () => {
        try {
            preferences = await getPreferences();
        } catch (err) {
            console.error("Fehler beim Laden der Präferenzen:", err);
        } finally {
            loading = false;
        }
        // Aufgelöste Mitgliedschaften für die Diagnose frisch laden
        refreshMyGroups();
    });

    // ── Eine Quittung je Feld ────────────────────────────────────────────────
    //
    // ⚠️ **Die Seite meldete nicht mehr, dass gespeichert wurde.** Mit dem
    // „Speichern"-Knopf verschwand am 21.09.2026 die letzte Rückmeldung — er war zwar
    // eine falsche (er navigierte nur), aber danach quittierte nur noch das
    // WebUntis-Kürzel. Alle Felder hier schreiben bei Änderung; wer nichts sieht, drückt
    // ein zweites Mal oder traut der Seite nicht.
    //
    // Ein **Seiten**banner wäre falsch: Bei sechs Einstellungen untereinander sagt es
    // nicht, welche gemeint ist. Die Quittung steht deshalb am Feld und verschwindet
    // wieder.
    let quittung = $state(null);
    let quittungTimer = null;

    function quittiere(key) {
        quittung = key;
        clearTimeout(quittungTimer);
        quittungTimer = setTimeout(() => (quittung = null), 2500);
    }

    async function updatePreference(key, value) {
        await patchPreferences({ [key]: value });
        // User-Store aktualisieren
        user.update((u) => ({
            ...u,
            preferences: {
                ...u?.preferences,
                [key]: value,
            },
        }));
        // Lokale Präferenzen aktualisieren
        preferences = { ...preferences, [key]: value };
        quittiere(key);
    }

    async function updateSidebarLimit(event) {
        const value = parseInt(event.target.value);
        await updatePreference("sidebar_recent_chats_limit", value);
    }

    async function updateContextSearchLimit(event) {
        const value = parseInt(event.target.value);
        await updatePreference("context_search_limit", value);
    }

    let pct = $derived(
        $budget?.max_budget_eur && $budget?.spend_eur != null
            ? Math.min(
                  100,
                  Math.round(
                      ($budget.spend_eur / $budget.max_budget_eur) * 100,
                  ),
              )
            : null,
    );

    // „Wann kommt wieder etwas dazu?" — ohne die Antwort wirkt ein leeres Budget
    // endgültig, obwohl am Montag wieder Guthaben da ist.
    let zuwachs = $derived(zuwachsText($budget));
    // Wie viel sich höchstens ansammelt — aus `vorsprung_wochen`, nicht geschätzt.
    let uebertrag = $derived(uebertragText($budget));
</script>

<button
    onclick={() => history.back()}
    class="flex items-center gap-1 mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx transition-colors"
>
    <ArrowLeft class="w-4 h-4" /> Zurück
</button>

<PageBody>
        <div
            class="flex items-center gap-2 mb-6 text-light-tx dark:text-dark-tx"
        >
            <User class="w-6 h-6 " />
            <h1 class="text-2xl font-semibold">Profil</h1>
        </div>

        <!-- Budget-Abschnitt -->
        <section class="mb-8">
            <h2
                class="text-base font-semibold mb-3 text-light-tx-2 dark:text-dark-tx-2"
            >
                Budget
            </h2>
            {#if $budget && $budget.max_budget_eur != null}
                <div>
                    {#if pct != null}
                        <div
                            class="w-full h-1 rounded bg-light-ui-3 dark:bg-dark-ui-3 mb-3"
                        >
                            <div
                                class="h-1 rounded transition-all {pct >= 80
                                    ? 'bg-red-500'
                                    : 'bg-primary'}"
                                style="width: {100 - pct}%"
                            ></div>
                        </div>
                    {/if}
                </div>

                <div class="flex items-center text-sm mb-2">
                    <span class="text-light-tx-2 dark:text-dark-tx-2">
                        Noch {fmt($budget?.remaining_eur)} € von {fmt(
                            $budget?.max_budget_eur,
                        )} € verfügbar.
                    </span>
                    {#if pct != null}
                        <span
                            class="ml-auto text-sm text-light-tx-2 dark:text-dark-tx-2"
                            >{100 - pct} %</span
                        >
                    {/if}
                </div>
                <div class="text-sm mb-2 text-light-tx-2 dark:text-dark-tx-2">
                    {#if zuwachs}
                        <p>{zuwachs}</p>
                    {/if}
                    {#if uebertrag}
                        <p>{uebertrag}</p>
                    {/if}
                    <p>In den Ferien kommt nichts dazu.</p>
                </div>
            {:else}
                <div class="text-sm mb-2 text-light-tx-2 dark:text-dark-tx-2">
                    Budgetdaten können derzeit nicht angezeigt werden.
                </div>
            {/if}
        </section>


        <!-- ── Darstellung ──────────────────────────────────────────────────────
             Fünf Einstellungen, die alle dasselbe tun: bestimmen, was und wie viel auf
             dem Bildschirm steht. Sie standen verstreut zwischen Budget, Kürzel und
             Diagnose; die Überschrift fasst sie zusammen, ohne sie zu verändern. -->
        <h2 class="text-lg font-semibold mb-4 text-light-tx dark:text-dark-tx">
            Darstellung
        </h2>

        <!-- Umfang der Oberfläche (Darstellungsstufen).
             Bewusst NICHT „Darstellungsstufen" überschrieben: Direkt darunter steht
             „Darstellungsmodus" für hell/dunkel — zwei fast gleiche Wörter für zwei ganz
             verschiedene Dinge. Die Überschrift sagt hier, was die Einstellung bewirkt.

             ⚠️ Anzeige-Filter, keine Berechtigung: Zurückschalten nimmt nichts weg, es
             blendet nur aus. Der Satz darunter sagt das, weil sonst niemand es wagt. -->
        {#if $stufenRegistry?.stufen?.length}
            <section class="mb-8">
                <h2
                    class="text-base font-semibold mb-1 text-light-tx-2 dark:text-dark-tx-2"
                >
                    Umfang der Oberfläche
                {#if quittung === "ui_stufe"}<span class="ml-2 text-xs text-light-gr dark:text-dark-gr" aria-live="polite">Gespeichert</span>{/if}
                </h2>
                <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-3">
                    Wähle, wie viel du sehen möchtest. Jede Stufe enthält die vorherigen.
                    Zurückschalten blendet nur aus — deine Chats, Bausteine und Planungen
                    bleiben erhalten und sind wieder da, sobald du erhöhst.
                </p>
                <div class="space-y-2">
                    {#each $stufenRegistry.stufen as s (s.stufe)}
                        {@const aktiv = $uiStufe === s.stufe}
                        <button
                            onclick={() => { setzeStufe(s.stufe); quittiere('ui_stufe'); }}
                            aria-pressed={aktiv}
                            class="w-full text-left p-3 rounded-lg border transition-colors
                                   {aktiv
                                ? 'border-primary dark:border-primary-dark bg-light-bl-bg dark:bg-dark-bl-bg'
                                : 'border-light-ui-3 dark:border-dark-ui-3 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
                        >
                            <span
                                class="flex items-center gap-2 text-sm font-medium text-light-tx dark:text-dark-tx"
                            >
                                {#if aktiv}
                                    <Check
                                        size={15}
                                        class="shrink-0 text-light-bl dark:text-dark-bl"
                                    />
                                {/if}
                                Stufe {s.stufe}: {s.name}
                            </span>
                            <span
                                class="block mt-1 text-xs text-light-tx-2 dark:text-dark-tx-2"
                            >
                                {s.beschreibung}
                            </span>
                            {#if s.aufwand}
                                <span
                                    class="block mt-1 text-xs italic text-light-tx-2 dark:text-dark-tx-2"
                                >
                                    {s.aufwand}
                                </span>
                            {/if}
                        </button>
                    {/each}
                </div>
            </section>
        {/if}

        <section class="mb-8">
            <h2
                class="text-base font-semibold mb-3 text-light-tx-2 dark:text-dark-tx-2"
            >
                Darstellungsmodus
            {#if quittung === "theme"}<span class="ml-2 text-xs text-light-gr dark:text-dark-gr" aria-live="polite">Gespeichert</span>{/if}
            </h2>
            <div class="flex gap-2">
                {#each themeOptions as { value, label, Icon }}
                    <button
                        class="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors
                        {$themePref === value
                            ? 'bg-primary text-white'
                            : 'bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
                        onclick={() => { themePref.set(value); quittiere('theme'); }}
                    >
                        <Icon class="w-4 h-4" />
                        {label}
                    </button>
                {/each}
            </div>
        </section>

        <section class="mb-8">
            <h2
                class="text-base font-semibold mb-3 text-light-tx-2 dark:text-dark-tx-2"
            >
                Kostenanzeige
            {#if quittung === "cost_granularity"}<span class="ml-2 text-xs text-light-gr dark:text-dark-gr" aria-live="polite">Gespeichert</span>{/if}
            </h2>
            <div>
                <label
                    class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-2"
                >
                    Kosten im Chat anzeigen
                </label>
                <select
                    onchange={(e) =>
                        updatePreference("cost_granularity", e.target.value)}
                    value={preferences?.cost_granularity ?? "none"}
                    class="w-full max-w-56 px-3 py-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx
                       focus:outline-none focus:ring-2 focus:ring-primary"
                    disabled={loading}
                >
                    {#each costGranularityOptions as { value, label }}
                        <option {value}>{label}</option>
                    {/each}
                </select>
            </div>
        </section>

        <section class="mb-8">
            <h2
                class="text-base font-semibold mb-3 text-light-tx-2 dark:text-dark-tx-2"
            >
                Chat-Sidebar
            {#if quittung === "sidebar_recent_chats_limit"}<span class="ml-2 text-xs text-light-gr dark:text-dark-gr" aria-live="polite">Gespeichert</span>{/if}
            </h2>
            <div class="space-y-4">
                <div>
                    <label
                        class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-2"
                    >
                        Anzahl zuletzt angezeigter Chats
                    </label>
                    <select
                        value={preferences?.sidebar_recent_chats_limit ?? 10}
                        onchange={updateSidebarLimit}
                        class="w-full max-w-40 px-3 py-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                           bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx
                           focus:outline-none focus:ring-2 focus:ring-primary"
                        disabled={loading}
                    >
                        {#each sidebarLimitOptions as opt}
                            <option value={opt}>{opt}</option>
                        {/each}
                    </select>
                </div>
            </div>
        </section>

        <section class="mb-8">
            <h2
                class="text-base font-semibold mb-3 text-light-tx-2 dark:text-dark-tx-2"
            >
                Kontext-Suche
            {#if quittung === "context_search_limit"}<span class="ml-2 text-xs text-light-gr dark:text-dark-gr" aria-live="polite">Gespeichert</span>{/if}
            </h2>
            <div>
                <label
                    class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-2"
                >
                    Angezeigte Treffer im Vorschlagsfenster
                </label>
                <select
                    value={preferences?.context_search_limit ?? 8}
                    onchange={updateContextSearchLimit}
                    class="w-full max-w-40 px-3 py-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                           bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx
                           focus:outline-none focus:ring-2 focus:ring-primary"
                    disabled={loading}
                >
                    {#each contextSearchLimitOptions as opt}
                        <option value={opt}>{opt}</option>
                    {/each}
                </select>
            </div>
        </section>

        <!-- ⚠️ **Ein Verweis, kein Ausklappbereich** (Jan, 25.09.2026). Hier standen zwei
             Zeilen mit Chevron über der ganzen Seite — sie sahen nach aufklappbaren
             Abschnitten aus und waren doch nur Links. „Unterricht" ist jetzt im
             Nutzermenü; die Fächerauswahl gehört hierher, weil sie eine
             Anzeige-Einstellung ist. -->
        {#if $user?.roles?.includes('teacher')}
        <section class="mb-8">
            <a
                href="/profile/subjects"
                class="flex items-center gap-2 px-4 py-3 rounded-lg
                       bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
            >
                <Eye class="w-4 h-4" />
                <span>Fächer in der Seitenleiste</span>
                <ChevronRight class="w-4 h-4 ml-auto" />
            </a>
        </section>
        {/if}

        <!-- Startseiten-Kacheln.
             ⚠️ **Umgezogen am 25.09.2026** (Jan, Paket 7 AP6). Die Wahl stand auf der
             Startseite selbst, mit der Begründung: „Wer eine Kachel weghaben will, denkt
             das beim Ansehen — nicht zwei Seiten später." Dagegen stand, dass die
             Startseite dadurch ihre eigene Einstellungsseite wurde. Jetzt steht sie bei
             den übrigen Anzeige-Einstellungen; die Startseite verweist darauf. -->
        {#if $user?.roles?.includes('teacher')}
        <section class="mb-8">
            <h2 class="text-base font-semibold mb-1 text-light-tx-2 dark:text-dark-tx-2">
                Kacheln der Startseite
            {#if quittung === "startkacheln"}<span class="ml-2 text-xs text-light-gr dark:text-dark-gr" aria-live="polite">Gespeichert</span>{/if}
            </h2>
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-3 max-w-prose">
                Was auf der Startseite steht. Eine abgewählte Kachel verschwindet nur aus
                der Ansicht — die Daten dahinter bleiben, und neue Kacheln erscheinen von
                selbst.
            </p>
            <div class="flex flex-col gap-2">
                {#each KACHELN as k (k.id)}
                    <label class="flex items-center gap-2 text-sm text-light-tx dark:text-dark-tx">
                        <input
                            type="checkbox"
                            checked={$zeigtKachel(k.id)}
                            onchange={(e) => { schalteKachel(k.id, e.currentTarget.checked); quittiere('startkacheln'); }}
                            class="accent-primary"
                        />
                        {k.name}
                    </label>
                {/each}
            </div>
        </section>
        {/if}

        {#if $user?.roles?.includes('teacher')}
        <section class="mb-8">
            <Zugangstoken />
        </section>
        {/if}

        <!-- SSO-Diagnose: rohe Gruppen/Rollen vom Anmeldedienst, für alle sichtbar -->
        <section class="mb-8">
            <details
                class="rounded-lg border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg-2 dark:bg-dark-bg-2"
            >
                <summary
                    class="cursor-pointer select-none px-4 py-3 text-sm font-medium text-light-tx dark:text-dark-tx"
                >
                    SSO-Mitgliedschaften (Diagnose)
                </summary>
                <div class="px-4 pb-4 pt-1 space-y-4 text-sm">
                    <p class="text-light-tx-2 dark:text-dark-tx-2">
                        Diese Angaben kommen unverändert vom Anmeldedienst (SSO) und
                        dienen der Fehlersuche bei der Rollen- und Fächer-Zuordnung.
                        Stimmt deine Rolle nicht, gib diese Liste an die Administration
                        weiter.
                    </p>

                    <div>
                        <h3
                            class="font-medium text-light-tx dark:text-dark-tx mb-1"
                        >
                            Plattform-Rollen
                        </h3>
                        <div class="flex flex-wrap gap-1.5">
                            {#each $user?.roles ?? [] as r}
                                <span
                                    class="px-2 py-0.5 rounded-full bg-primary/10 dark:bg-primary-dark/10 text-primary dark:text-primary-dark text-xs"
                                    >{r}</span
                                >
                            {/each}
                        </div>
                    </div>

                    <div>
                        <h3
                            class="font-medium text-light-tx dark:text-dark-tx mb-1"
                        >
                            SSO-Rollen
                        </h3>
                        {#if ($user?.sso_roles ?? []).length > 0}
                            <div class="flex flex-wrap gap-1.5">
                                {#each $user.sso_roles as g}
                                    <span
                                        class="px-2 py-0.5 rounded-full bg-light-ui-3 dark:bg-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2 text-xs font-mono"
                                        >{g}</span
                                    >
                                {/each}
                            </div>
                        {:else}
                            <p class="text-light-tx-2 dark:text-dark-tx-2">— keine —</p>
                        {/if}
                    </div>

                    <div>
                        <h3
                            class="font-medium text-light-tx dark:text-dark-tx mb-1"
                        >
                            SSO-Gruppen
                        </h3>
                        {#if ($user?.sso_groups ?? []).length > 0}
                            <div class="flex flex-wrap gap-1.5">
                                {#each $user.sso_groups as g}
                                    <span
                                        class="px-2 py-0.5 rounded-full bg-light-ui-3 dark:bg-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2 text-xs font-mono"
                                        >{g}</span
                                    >
                                {/each}
                            </div>
                        {:else}
                            <p class="text-light-tx-2 dark:text-dark-tx-2">— keine —</p>
                        {/if}
                    </div>

                    {#if ($user?.sso_groups ?? []).length === 0 && ($user?.sso_roles ?? []).length === 0}
                        <p class="text-light-tx-2 dark:text-dark-tx-2">
                            Keine SSO-Daten vorhanden. Melde dich neu an, damit aktuelle
                            Gruppen- und Rollen-Informationen geladen werden.
                        </p>
                    {/if}

                    <!-- Aufgelöste Plattform-Mitgliedschaften: was das System aus den
                         SSO-Gruppen tatsächlich abgeleitet hat (Soll/Ist-Abgleich). -->
                    <div class="border-t border-light-ui-3 dark:border-dark-ui-3 pt-4">
                        <h3 class="font-medium text-light-tx dark:text-dark-tx mb-1">
                            Aufgelöste Mitgliedschaften
                        </h3>
                        <p class="text-light-tx-2 dark:text-dark-tx-2 mb-3">
                            So hat die Plattform deine SSO-Gruppen umgesetzt. Fehlt hier
                            eine Fachschaft, obwohl die passende <code class="font-mono">fs.*</code>-Gruppe
                            oben steht, ist die Zuordnung fehlerhaft — diese Liste an die
                            Administration weitergeben.
                        </p>
                        {#if ($myGroups ?? []).length > 0}
                            <div class="space-y-3">
                                {#each membershipGroups as grp}
                                    {#if grp.items.length > 0}
                                        <div>
                                            <p class="text-xs uppercase tracking-wide text-light-tx-2 dark:text-dark-tx-2 mb-1">
                                                {grp.label}
                                            </p>
                                            <div class="flex flex-wrap gap-1.5">
                                                {#each grp.items as m (m.id)}
                                                    <span
                                                        class="px-2 py-0.5 rounded-full bg-light-ui-3 dark:bg-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2 text-xs"
                                                    >
                                                        {m.name}{#if m.subject_id != null && $subjectMap[m.subject_id]}
                                                            <span class="opacity-70"> · {$subjectMap[m.subject_id].name}</span>
                                                        {/if}
                                                    </span>
                                                {/each}
                                            </div>
                                        </div>
                                    {/if}
                                {/each}
                            </div>
                        {:else}
                            <p class="text-light-tx-2 dark:text-dark-tx-2">
                                — keine Mitgliedschaften aufgelöst —
                            </p>
                        {/if}
                    </div>
                </div>
            </details>
        </section>

    
</PageBody>
