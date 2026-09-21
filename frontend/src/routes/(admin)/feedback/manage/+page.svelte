<script>
    /**
     * Sichtung der Rückmeldungen (ADR-020, AP4).
     *
     * **Der Weg zu GitHub ist Handarbeit, und das ist der Punkt.** Die sichtende
     * Person entscheidet, was echte Arbeit ist, fasst Doppelmeldungen unter derselben
     * Issue-Referenz zusammen und hält Schülertexte aus dem öffentlichen Tracker
     * heraus. Diese Seite unterstützt den Schritt, sie ersetzt ihn nicht.
     *
     * **Der angehängte Chat wird erst beim Aufklappen geladen.** In der Liste stünde
     * sonst bei fünfzig Meldungen ein Vielfaches an Chatinhalt, das niemand
     * angefordert hat.
     */
    import { onMount } from "svelte";
    import { ChevronDown, ChevronRight, Loader2 } from "lucide-svelte";
    import {
        getAdminFeedback,
        getAdminFeedbackDetail,
        patchAdminFeedback,
    } from "$lib/api.js";
    import { feedbackFehlertext, kategorieText, statusFarbe } from "$lib/feedback.js";
    import { refreshFeedbackAlerts } from "$lib/stores/feedbackAlerts.js";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import InfoBanner from "$lib/components/InfoBanner.svelte";

    const STATI = [
        { wert: "open", label: "Offen" },
        { wert: "in_progress", label: "In Bearbeitung" },
        { wert: "done", label: "Erledigt" },
        { wert: "declined", label: "Nicht umgesetzt" },
        { wert: "spam", label: "Spam" },
    ];
    // Die Zustände, in denen die Sichtung fertig ist — dann fallen Kontakt und Anhang.
    const ABGESCHLOSSEN = ["done", "declined", "spam"];

    let eintraege = $state([]);
    let zaehler = $state({});
    let gesamt = $state(0);
    let laedt = $state(true);
    let fehler = $state(null);

    let gewaehlteStati = $state(["open", "in_progress"]);
    let kategorie = $state("");
    let rolle = $state("");
    let version = $state("");

    let offenerEintrag = $state(null);
    let detail = $state(null);
    let detailLaedt = $state(false);

    // Formularwerte des offenen Eintrags
    let neuerStatus = $state("");
    let antwort = $state("");
    let erledigtIn = $state("");
    let issueRef = $state("");
    let anhangBehalten = $state(false);
    let speichert = $state(false);

    const schliesstAb = $derived(ABGESCHLOSSEN.includes(neuerStatus));
    const brauchtBegruendung = $derived(neuerStatus === "declined" && !antwort.trim());

    async function laden() {
        laedt = true;
        try {
            const daten = await getAdminFeedback({
                status: gewaehlteStati,
                category: kategorie || null,
                role: rolle || null,
                appVersion: version || null,
                limit: 100,
            });
            eintraege = daten.items;
            zaehler = daten.counts ?? {};
            gesamt = daten.total;
            fehler = null;
        } catch (err) {
            fehler = feedbackFehlertext(err);
        } finally {
            laedt = false;
        }
    }

    onMount(laden);

    function statusUmschalten(wert) {
        gewaehlteStati = gewaehlteStati.includes(wert)
            ? gewaehlteStati.filter((s) => s !== wert)
            : [...gewaehlteStati, wert];
        // Ohne Auswahl liefert der Server seine Vorgabe (offen + in Bearbeitung) —
        // das ist hier die bessere Antwort als eine leere Liste.
        laden();
    }

    async function aufklappen(eintrag) {
        if (offenerEintrag === eintrag.id) {
            offenerEintrag = null;
            detail = null;
            return;
        }
        offenerEintrag = eintrag.id;
        detail = null;
        neuerStatus = eintrag.status;
        antwort = eintrag.admin_reply ?? "";
        erledigtIn = eintrag.resolved_in_version ?? "";
        issueRef = eintrag.issue_ref ?? "";
        anhangBehalten = false;
        if (!eintrag.has_snapshot) return;
        detailLaedt = true;
        try {
            detail = await getAdminFeedbackDetail(eintrag.id);
        } catch (err) {
            fehler = feedbackFehlertext(err);
        } finally {
            detailLaedt = false;
        }
    }

    async function speichern(eintrag) {
        speichert = true;
        try {
            await patchAdminFeedback(eintrag.id, {
                status: neuerStatus,
                admin_reply: antwort,
                resolved_in_version: erledigtIn,
                issue_ref: issueRef,
                keep_snapshot: anhangBehalten,
            });
            fehler = null;
            offenerEintrag = null;
            detail = null;
            await laden();
            refreshFeedbackAlerts();
        } catch (err) {
            fehler = feedbackFehlertext(err);
        } finally {
            speichert = false;
        }
    }

    const zeitpunkt = (wert) =>
        new Date(wert).toLocaleString("de-DE", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
</script>

<div class="max-w-4xl mx-auto">
    {#if fehler}
        <ErrorBanner message={fehler} />
    {/if}

    <!-- Filter -->
    <div class="flex flex-wrap items-center gap-2">
        {#each STATI as s (s.wert)}
            <button
                onclick={() => statusUmschalten(s.wert)}
                aria-pressed={gewaehlteStati.includes(s.wert)}
                class="px-2.5 py-1 text-sm rounded-full border transition-colors
                       text-light-tx dark:text-dark-tx
                       {gewaehlteStati.includes(s.wert)
                           ? statusFarbe(s.wert)
                           : 'border-light-ui-3 dark:border-dark-ui-3 opacity-60'}"
            >
                {s.label}
                <span class="text-xs">({zaehler[s.wert] ?? 0})</span>
            </button>
        {/each}
    </div>

    <div class="mt-3 flex flex-wrap gap-2">
        <select
            bind:value={kategorie}
            onchange={laden}
            aria-label="Kategorie"
            class="rounded-lg border px-2 py-1 text-sm
                   bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                   border-light-ui-3 dark:border-dark-ui-3"
        >
            <option value="">Alle Kategorien</option>
            <option value="bug">Fehler</option>
            <option value="suggestion">Verbesserungsvorschlag</option>
            <option value="other">Sonstiges</option>
        </select>
        <select
            bind:value={rolle}
            onchange={laden}
            aria-label="Rolle"
            class="rounded-lg border px-2 py-1 text-sm
                   bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                   border-light-ui-3 dark:border-dark-ui-3"
        >
            <option value="">Alle Rollen</option>
            <option value="student">Schüler:innen</option>
            <option value="teacher">Lehrkräfte</option>
        </select>
        <input
            bind:value={version}
            onchange={laden}
            placeholder="Version"
            aria-label="Version"
            class="w-28 rounded-lg border px-2 py-1 text-sm
                   bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                   border-light-ui-3 dark:border-dark-ui-3"
        />
    </div>

    {#if laedt}
        <div class="flex items-center gap-2 py-12 text-light-tx-2 dark:text-dark-tx-2">
            <Loader2 class="w-4 h-4 animate-spin" /> Lädt…
        </div>
    {:else if eintraege.length === 0}
        <div class="mt-6">
            <InfoBanner message="Keine Meldungen in dieser Auswahl." />
        </div>
    {:else}
        <p class="mt-4 text-xs text-light-tx-2 dark:text-dark-tx-2">
            {gesamt}
            {gesamt === 1 ? "Meldung" : "Meldungen"}
        </p>
        <ul class="mt-2 space-y-2">
            {#each eintraege as e (e.id)}
                <li
                    class="rounded-lg border
                           bg-light-bg dark:bg-dark-bg
                           border-light-ui-3 dark:border-dark-ui-3"
                >
                    <button
                        onclick={() => aufklappen(e)}
                        class="w-full flex items-start gap-2 p-3 text-left
                               hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 rounded-lg"
                    >
                        {#if offenerEintrag === e.id}
                            <ChevronDown class="w-4 h-4 mt-0.5 shrink-0" />
                        {:else}
                            <ChevronRight class="w-4 h-4 mt-0.5 shrink-0" />
                        {/if}
                        <span class="min-w-0 flex-1">
                            <span class="flex flex-wrap items-center gap-2">
                                <span
                                    class="text-xs px-2 py-0.5 rounded-full border
                                           text-light-tx dark:text-dark-tx {statusFarbe(e.status)}"
                                >
                                    {STATI.find((s) => s.wert === e.status)?.label ?? e.status}
                                </span>
                                <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                                    {kategorieText(e.category)} · {e.role} · {e.app_version}
                                    · {zeitpunkt(e.created_at)}
                                    {#if e.has_snapshot}· mit Chat{/if}
                                    {#if e.issue_ref}· {e.issue_ref}{/if}
                                </span>
                            </span>
                            <span
                                class="mt-1 block truncate text-sm text-light-tx dark:text-dark-tx"
                            >
                                {e.content}
                            </span>
                        </span>
                    </button>

                    {#if offenerEintrag === e.id}
                        <div
                            class="border-t p-4 space-y-4
                                   border-light-ui-3 dark:border-dark-ui-3"
                        >
                            <p class="whitespace-pre-wrap text-sm text-light-tx dark:text-dark-tx">
                                {e.content}
                            </p>

                            <dl class="text-xs text-light-tx-2 dark:text-dark-tx-2 space-y-0.5">
                                <div><dt class="inline">Pseudonym:</dt> <dd class="inline">{e.pseudonym ?? "—"}</dd></div>
                                <div><dt class="inline">Seite:</dt> <dd class="inline">{e.route ?? "—"}</dd></div>
                                <div><dt class="inline">Assistent:</dt> <dd class="inline">{e.assistant_id ?? "—"}</dd></div>
                                <div><dt class="inline">Browser:</dt> <dd class="inline">{e.user_agent ?? "—"}</dd></div>
                                <div><dt class="inline">Fenster:</dt> <dd class="inline">{e.viewport ?? "—"}</dd></div>
                            </dl>

                            {#if e.contact}
                                <div
                                    class="rounded border p-3
                                           bg-light-ye-bg dark:bg-dark-ye-bg
                                           border-light-ye dark:border-dark-ye"
                                >
                                    <p class="text-sm text-light-tx dark:text-dark-tx">
                                        Kontakt: {e.contact}
                                    </p>
                                    <p class="mt-1 text-xs text-light-tx dark:text-dark-tx">
                                        Freiwillig angegeben, nur für Rückfragen zu dieser
                                        Meldung. Beim Abschluss wird die Angabe gelöscht.
                                    </p>
                                </div>
                            {/if}

                            {#if e.has_snapshot}
                                <div>
                                    <p class="text-xs font-medium text-light-tx dark:text-dark-tx">
                                        Angehängter Chat
                                    </p>
                                    {#if detailLaedt}
                                        <div class="flex items-center gap-2 py-2 text-light-tx-2 dark:text-dark-tx-2">
                                            <Loader2 class="w-4 h-4 animate-spin" /> Lädt…
                                        </div>
                                    {:else if detail?.conversation_snapshot}
                                        <ul
                                            class="mt-1 max-h-64 overflow-y-auto rounded border p-2 space-y-2
                                                   border-light-ui-3 dark:border-dark-ui-3"
                                        >
                                            {#each detail.conversation_snapshot.messages ?? [] as n, i (i)}
                                                <li class="text-xs">
                                                    <span class="font-medium text-light-tx-2 dark:text-dark-tx-2">
                                                        {n.role === "user" ? "Nutzer:in" : "Assistent"}:
                                                    </span>
                                                    <span class="whitespace-pre-wrap text-light-tx dark:text-dark-tx">
                                                        {n.content}
                                                    </span>
                                                </li>
                                            {/each}
                                        </ul>
                                    {/if}
                                </div>
                            {/if}

                            <!-- Statuswechsel -->
                            <div class="space-y-2 border-t pt-3 border-light-ui-3 dark:border-dark-ui-3">
                                <div class="flex flex-wrap gap-2">
                                    <select
                                        bind:value={neuerStatus}
                                        aria-label="Status"
                                        class="rounded-lg border px-2 py-1 text-sm
                                               bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                                               border-light-ui-3 dark:border-dark-ui-3"
                                    >
                                        {#each STATI as s (s.wert)}
                                            <option value={s.wert}>{s.label}</option>
                                        {/each}
                                    </select>
                                    <input
                                        bind:value={erledigtIn}
                                        placeholder="Erledigt in Version"
                                        aria-label="Erledigt in Version"
                                        class="w-40 rounded-lg border px-2 py-1 text-sm
                                               bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                                               border-light-ui-3 dark:border-dark-ui-3"
                                    />
                                    <input
                                        bind:value={issueRef}
                                        placeholder="Issue (#142)"
                                        aria-label="Issue-Referenz"
                                        class="w-40 rounded-lg border px-2 py-1 text-sm
                                               bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                                               border-light-ui-3 dark:border-dark-ui-3"
                                    />
                                </div>

                                <textarea
                                    bind:value={antwort}
                                    rows="2"
                                    placeholder="Antwort an die meldende Person (bei „Nicht umgesetzt“ erforderlich)"
                                    aria-label="Antwort"
                                    class="w-full rounded-lg border p-2 text-sm
                                           bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                                           border-light-ui-3 dark:border-dark-ui-3"
                                ></textarea>

                                {#if schliesstAb && e.has_snapshot}
                                    <label class="flex items-start gap-2">
                                        <input
                                            type="checkbox"
                                            bind:checked={anhangBehalten}
                                            class="mt-0.5 accent-primary"
                                        />
                                        <span class="text-sm text-light-tx dark:text-dark-tx">
                                            Angehängten Chat behalten
                                            <span class="block text-xs text-light-tx-2 dark:text-dark-tx-2">
                                                Sonst wird er beim Abschluss gelöscht. Die
                                                Kontaktangabe fällt in jedem Fall.
                                            </span>
                                        </span>
                                    </label>
                                {/if}

                                <div class="flex items-center justify-end gap-2">
                                    {#if brauchtBegruendung}
                                        <span class="text-xs text-light-tx dark:text-dark-tx">
                                            Für „Nicht umgesetzt“ fehlt noch eine Begründung.
                                        </span>
                                    {/if}
                                    <button
                                        onclick={() => speichern(e)}
                                        disabled={speichert || brauchtBegruendung}
                                        class="px-3 py-1.5 text-sm rounded-lg inline-flex items-center gap-2
                                               bg-primary dark:bg-primary-dark text-white
                                               disabled:opacity-50 disabled:cursor-not-allowed"
                                    >
                                        {#if speichert}<Loader2 class="w-4 h-4 animate-spin" />{/if}
                                        Speichern
                                    </button>
                                </div>
                            </div>
                        </div>
                    {/if}
                </li>
            {/each}
        </ul>
    {/if}
</div>
