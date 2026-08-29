<script>
    import { User, Sun, Moon, Monitor, Save, ArrowLeft, BookOpen, ChevronRight, Eye } from "lucide-svelte";
    import { themePref } from "$lib/stores/theme.js";
    import { user } from "$lib/stores/user.js";
    import { budget } from "$lib/stores/budget.js";
    import { myGroups, refreshMyGroups } from "$lib/stores/myGroups.js";
    import { subjectMap } from "$lib/stores/subjects.js";
    import { goto } from "$app/navigation";
    import { patchPreferences, getPreferences, getCalendarTeachers } from "$lib/api.js";
    import { onMount } from "svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import SuccessBanner from "$lib/components/SuccessBanner.svelte";
    import WarningBanner from "$lib/components/WarningBanner.svelte";
    import TimetableSyncButton from "$lib/components/TimetableSyncButton.svelte";

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

    // ── WebUntis-Kürzel (UP-8 Schritt 3) ──────────────────────────────────
    // Auswahl aus der geladenen Liste statt Freitext: Ein Tippfehler führte sonst zu einem
    // stillen Nicht-Abruf, den später niemand zuordnet.
    let kuerzelListe = $state({ configured: false, teachers: [], error: null });
    let kuerzelFehler = $state("");
    let kuerzelGespeichert = $state(false);

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
        // Bewusst ohne Rollenprüfung: Der Nutzer-Store ist beim Einhängen nicht
        // zwangsläufig schon befüllt — eine Abfrage von `roles` an dieser Stelle ist ein
        // Wettlauf, der sich als „Feld fehlt" äußert. Der Server entscheidet (403 für
        // Schüler:innen), die Antwort trägt das Ergebnis in `allowed`.
        kuerzelListe = await getCalendarTeachers();
    });

    async function updateKuerzel(event) {
        const wert = event.target.value;
        kuerzelFehler = "";
        kuerzelGespeichert = false;
        try {
            await updatePreference("webuntis_kuerzel", wert);
            kuerzelGespeichert = true;
        } catch (err) {
            kuerzelFehler = err.message;
            // Anzeige auf den gespeicherten Stand zurücksetzen — sonst zeigt das Feld
            // eine Auswahl, die der Server abgelehnt hat.
            event.target.value = preferences?.webuntis_kuerzel ?? "";
        }
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
    }

    async function updateSidebarLimit(event) {
        const value = parseInt(event.target.value);
        await updatePreference("sidebar_recent_chats_limit", value);
    }

    async function updateContextSearchLimit(event) {
        const value = parseInt(event.target.value);
        await updatePreference("context_search_limit", value);
    }

    function doSave() {
        goto("/");
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
</script>

<button
    onclick={() => history.back()}
    class="flex items-center gap-1 mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx transition-colors"
>
    <ArrowLeft class="w-4 h-4" /> Zurück
</button>

<div class="h-full overflow-y-auto">
    <div class="max-w-2xl mx-auto p-6">
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
                    Dein Guthaben wächst in jeder Unterrichtswoche. Was du nicht
                    verbrauchst, bleibt dir für spätere Wochen erhalten.
                </div>
            {:else}
                <div class="text-sm mb-2 text-light-tx-2 dark:text-dark-tx-2">
                    Budgetdaten können derzeit nicht angezeigt werden.
                </div>
            {/if}
        </section>

        <!-- Lehrkraft-Verwaltungslinks (nur für Lehrkräfte) -->
        {#if $user?.roles?.includes('teacher')}
        <section class="mb-8 flex flex-col gap-2">
            <a
                href="/profile/teaching-groups"
                class="flex items-center gap-2 px-4 py-3 rounded-lg
                       bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
            >
                <BookOpen class="w-4 h-4" />
                <span>Unterrichtsgruppen verwalten</span>
                <ChevronRight class="w-4 h-4 ml-auto" />
            </a>
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

        {#if kuerzelListe.allowed && kuerzelListe.error && !kuerzelListe.configured}
        <!-- Sichtbar scheitern statt lautlos verschwinden: Ohne diesen Hinweis sieht ein
             Serverfehler genauso aus wie „diese Schule nutzt kein WebUntis". -->
        <section class="mb-8">
            <h2 class="text-base font-semibold mb-3 text-light-tx-2 dark:text-dark-tx-2">
                Stundenplan
            </h2>
            <WarningBanner message={kuerzelListe.error} />
        </section>
        {/if}

        {#if kuerzelListe.configured}
        <section class="mb-8">
            <h2 class="text-base font-semibold mb-3 text-light-tx-2 dark:text-dark-tx-2">
                Stundenplan
            </h2>
            {#if kuerzelListe.error}
                <div class="mb-3"><WarningBanner message={kuerzelListe.error} /></div>
            {/if}
            <label
                for="webuntis-kuerzel"
                class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-2"
            >
                Ihr Kürzel im Stundenplan
            </label>
            <select
                id="webuntis-kuerzel"
                value={preferences?.webuntis_kuerzel ?? ""}
                onchange={updateKuerzel}
                class="w-full max-w-40 px-3 py-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx
                       focus:outline-none focus:ring-2 focus:ring-primary"
                disabled={loading}
            >
                <option value="">— nicht zugeordnet —</option>
                {#each kuerzelListe.teachers as k}
                    <option value={k}>{k}</option>
                {/each}
            </select>

            <p class="mt-3 text-sm text-light-tx-2 dark:text-dark-tx-2 max-w-prose">
                Ihr Kürzel wird ausschließlich verwendet, um Ihren Stundenplan abzurufen
                (Wochenmuster, Ausfälle, Vertretungen). Es wird <strong>nicht</strong> an
                KI-Modelle übermittelt und erscheint in keinem Chat, keinem
                Assistenten-Kontext und keinem Wissensknoten. Sie können es jederzeit
                entfernen; dann entfällt die Stundenplan-Übernahme.
            </p>

            {#if kuerzelFehler}
                <div class="mt-3"><ErrorBanner message={kuerzelFehler} /></div>
            {:else if kuerzelGespeichert}
                <div class="mt-3"><SuccessBanner message="Kürzel gespeichert." /></div>
            {/if}

            <!-- Handabgleich und Status. Der Hauptweg ist der Knopf im Jahresplan —
                 hier steht er, weil hier auch der Zustand hingehört: wann zuletzt
                 abgeglichen wurde und ob der nächtliche Lauf scheitert. -->
            {#if preferences?.webuntis_kuerzel}
                <div class="mt-6 pt-4 border-t border-light-ui-3 dark:border-dark-ui-3">
                    <h3 class="text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-3">
                        Abgleich
                    </h3>
                    <TimetableSyncButton />
                    <p class="mt-3 text-sm text-light-tx-2 dark:text-dark-tx-2 max-w-prose">
                        Ausfälle und Vertretungen werden nachts automatisch übernommen.
                        Wer von einer kurzfristigen Änderung weiß — etwa einer verlegten
                        Stunde —, gleicht hier oder im Jahresplan von Hand ab.
                    </p>
                </div>
            {/if}
        </section>
        {/if}
        {/if}

        <section class="mb-8">
            <h2
                class="text-base font-semibold mb-3 text-light-tx-2 dark:text-dark-tx-2"
            >
                Darstellungsmodus
            </h2>
            <div class="flex gap-2">
                {#each themeOptions as { value, label, Icon }}
                    <button
                        class="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors
                        {$themePref === value
                            ? 'bg-primary text-white'
                            : 'bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
                        onclick={() => themePref.set(value)}
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
            </h2>
            <div>
                <label
                    class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-2"
                >
                    Maximale Trefferzahl beim Kontext-Lookup
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

        <section class="mb-8">
            <button
                class="px-4 py-2 rounded-md text-sm font-medium bg-light-gr-2 dark:bg-dark-gr-2 text-white hover:bg-light-gr dark:hover:bg-dark-gr transition-colors"
                onclick={doSave}
            >
                <Save class="w-4 h-4 inline-block mr-1 mb-1" /> Speichern
            </button>
        </section>
    </div>
</div>
