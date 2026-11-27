<script>
    import ZurueckLink from "$lib/components/ZurueckLink.svelte";
    import { rueckwegAus } from "$lib/rueckweg.js";
    import { page } from "$app/stores";
    import { goto } from "$app/navigation";
    import {
        getCurriculum,
        deleteContextNode,
        exportCurriculum,
        relinkCurriculum,
    } from "$lib/api.js";
    import { curriculumStd, entwurfHinweis, quelleText, vorlageHinweis } from "$lib/curriculum.js";
    import CurriculumTable from "$lib/components/CurriculumTable.svelte";
    import CurriculumRahmen from "$lib/components/CurriculumRahmen.svelte";
    import CurriculumBandWahl from "$lib/components/CurriculumBandWahl.svelte";
    import CurriculumAssistentKnopf from "$lib/components/CurriculumAssistentKnopf.svelte";
    import LoadingBanner from "$lib/components/LoadingBanner.svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import InfoBanner from "$lib/components/InfoBanner.svelte";
    import CurriculumFreigabe from "$lib/components/CurriculumFreigabe.svelte";
    import { FileDown, Pencil, RefreshCw, Trash2, X } from "@lucide/svelte";
    import { getVerlaufsplaene } from "$lib/api.js";
    import { planVerweise } from "$lib/verlaufsplan.js";
    import { stufen as bandStufen } from "$lib/curriculum_rahmen.js";
    import { user, userHasAnyRole } from "$lib/stores/user.js";

    let curriculum = $state(null);
    const totalStd = $derived(curriculumStd(curriculum));
    let loading = $state(true);
    let error = $state(null);

    // Löschen
    let confirmDelete = $state(false);
    let deleting = $state(false);
    let deleteError = $state(null);

    // Export
    const WEITERBEARBEITEN = "Zum Weiterbearbeiten in Word oder LibreOffice. Wieder einlesen lässt sich nur YAML.";
    const EXPORTE = [
        { format: "yaml", label: "YAML" },
        { format: "pdf", label: "PDF" },
        { format: "docx", label: "DOCX", titel: WEITERBEARBEITEN },
        { format: "odt", label: "ODT", titel: WEITERBEARBEITEN },
    ];
    let exportError = $state(null);
    let exporting = $state(false);

    // Sticky-Footer: nur sichtbar, wenn die oberen Aktionen aus dem Scrollbereich sind
    let scrollEl = $state(null);
    let topActionsEl = $state(null);
    let showStickyFooter = $state(false);

    $effect(() => {
        if (!scrollEl || !topActionsEl) return;
        const obs = new IntersectionObserver(
            ([entry]) => {
                showStickyFooter = !entry.isIntersecting;
            },
            { root: scrollEl, threshold: 0 },
        );
        obs.observe(topActionsEl);
        return () => obs.disconnect();
    });

    function _exportFilename(format) {
        const meta = curriculum?.metadata ?? {};
        const fach = (meta.fach_code ?? "curriculum").replace(/\s/g, "_");
        const jg = meta.jahrgangsstufe ?? "";
        const date = new Date().toISOString().slice(0, 10);
        return `curriculum_${fach}_${jg}_${date}.${format}`;
    }

    async function handleExport(format) {
        if (exporting || !curriculum) return;
        exporting = true;
        exportError = null;
        try {
            await exportCurriculum(
                curriculum.id,
                _exportFilename(format),
                format,
            );
        } catch (e) {
            exportError = e.message || "Export fehlgeschlagen.";
        } finally {
            exporting = false;
        }
    }

    // Jahresverlaufspläne der Stufen dieses Curriculums im laufenden Schuljahr (0.59, BD Schritt 7)
    let verlaufsplaene = $state(null);
    // Nur für Lehrkräfte: Curricula lesen auch Schüler:innen, Jahresverlaufspläne nicht (BD F11).
    const lehrkraft = $derived(!!$user && userHasAnyRole($user, ["teacher", "admin"]));
    $effect(() => {
        const fach = curriculum?.subject_id;
        if (!fach || !lehrkraft) return;
        let abgebrochen = false;
        getVerlaufsplaene(fach)
            .then((a) => { if (!abgebrochen) verlaufsplaene = a; })
            .catch(() => { if (!abgebrochen) verlaufsplaene = null; }); // ohne Pläne bleibt der Link auf die Liste
        return () => { abgebrochen = true; };
    });
    const planLinks = $derived(lehrkraft && curriculum?.subject_id ? planVerweise(verlaufsplaene?.plaene, {
        fachId: curriculum.subject_id,
        stufen: bandStufen(curriculum.metadata?.jahrgangsstufe),
        aktuell: verlaufsplaene?.aktuelles_schuljahr,
    }) : []);

    $effect(() => {
        const id = $page.params.id;
        let cancelled = false;

        loading = true;
        (async () => {
            try {
                const data = await getCurriculum(id);
                if (cancelled) return;
                curriculum = data;
            } catch (e) {
                if (!cancelled) error = e.message;
            } finally {
                if (!cancelled) loading = false;
            }
        })();

        return () => {
            cancelled = true;
        };
    });

    // Sprung an ein Kapitel (`#kapitel-<id>`, etwa aus der Leitlinien-Übersicht, 0.53),
    // sobald das Curriculum gezeichnet ist.
    $effect(() => {
        const hash = $page.url.hash;
        if (loading || !curriculum || !hash.startsWith("#kapitel-")) return;
        requestAnimationFrame(() => document.getElementById(hash.slice(1))?.scrollIntoView({ block: "start" }));
    });

    // ── Auf aktuellen Bildungsplan aktualisieren (Re-Link) ────────────────────
    let relinkPreview = $state(null);   // Vorschau-Plan (mode/summary/target)
    let relinkBusy = $state(false);
    let relinkError = $state(null);

    async function handleRelinkPreview() {
        if (relinkBusy || !curriculum) return;
        relinkBusy = true;
        relinkError = null;
        try {
            relinkPreview = await relinkCurriculum(curriculum.id, false);
        } catch (e) {
            relinkError = e.message || "Vorschau fehlgeschlagen.";
        } finally {
            relinkBusy = false;
        }
    }

    async function handleRelinkApply() {
        if (relinkBusy || !curriculum || !relinkPreview) return;
        relinkBusy = true;
        relinkError = null;
        try {
            const res = await relinkCurriculum(curriculum.id, true);
            relinkPreview = null;
            const newId = res.result_curriculum_id;
            if (newId && newId !== String(curriculum.id)) {
                // Band-Split: migrierte Kopie → dorthin navigieren
                goto(`/knowledge/curriculum/${newId}`);
            } else {
                curriculum = await getCurriculum(curriculum.id); // neu laden
            }
        } catch (e) {
            relinkError = e.message || "Aktualisierung fehlgeschlagen.";
        } finally {
            relinkBusy = false;
        }
    }

    async function handleDelete() {
        if (deleting || !curriculum) return;
        deleting = true;
        deleteError = null;
        try {
            await deleteContextNode(curriculum.id);
            goto("/knowledge/curricula", { replaceState: true });
        } catch (e) {
            deleteError =
                e.status === 403
                    ? "Keine Berechtigung — du musst Mitglied der Fachschaft sein."
                    : e.message || "Curriculum konnte nicht gelöscht werden.";
            deleting = false;
        }
    }
</script>

<div class="h-full flex flex-col relative">
    <!-- Scrollbarer Inhaltsbereich -->
    <div
        bind:this={scrollEl}
        class="flex-1 overflow-y-auto p-6 pb-16 w-full"
    >
        {#if loading}
            <LoadingBanner />
        {:else if error}
            <ErrorBanner message={error} />
        {:else if curriculum}
            <!-- Kopfzeile mit Metadaten und Aktionen -->
            <div class="flex items-center justify-between gap-4 mb-6">
                <div>
                    <ZurueckLink href={rueckwegAus($page.url.searchParams) ?? "/knowledge/curricula"} label={rueckwegAus($page.url.searchParams) ? undefined : "Curricula"} />
                    <h1
                        class="text-2xl font-bold text-light-tx dark:text-dark-tx"
                    >
                        {curriculum.title}
                    </h1>
                    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
                        {curriculum.metadata?.schule} ·
                        {curriculum.metadata?.schulart} · BP {curriculum
                            .metadata?.bp_version} · Klasse {curriculum.metadata
                            ?.jahrgangsstufe}
                        {#if totalStd > 0}
                            · Gesamt: {totalStd} Std.
                        {/if}
                        {#each planLinks as l (l.href)}
                            · <a href={l.href} class="text-light-bl dark:text-dark-bl hover:underline">{l.text}</a>
                        {/each}
                    </p>
                    {#if quelleText(curriculum)}
                        <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mt-1">Quelle: {quelleText(curriculum)}</p>
                    {/if}
                </div>
                <div bind:this={topActionsEl} class="flex flex-wrap justify-end gap-2">
                    <CurriculumFreigabe
                        {curriculum}
                        onveroeffentlicht={async () => (curriculum = await getCurriculum(curriculum.id))}
                    />
                    {#if curriculum.can_edit && curriculum.status === "draft"}
                        <CurriculumAssistentKnopf {curriculum} />
                    {/if}
                    {#if curriculum.can_edit}
                        <a
                            href="/knowledge/curriculum/{curriculum.id}/edit"
                            class="inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-md bg-primary dark:bg-primary-dark
                               text-on-fill font-medium hover:opacity-90 transition-opacity"
                        >
                            <Pencil class="w-4 h-4" /> Bearbeiten
                        </a>
                        <button
                            onclick={handleRelinkPreview}
                            disabled={relinkBusy}
                            title="Prüft, ob das Curriculum auf die aktuelle Bildungsplan-Fassung aktualisiert werden kann"
                            class="inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                               text-light-tx dark:text-dark-tx font-medium
                               hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
                               disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            <RefreshCw class="w-4 h-4" /> Bildungsplan aktualisieren
                        </button>
                    {/if}
                    <!-- Löschen (0.45, E12): eigenes Recht — einen Entwurf löscht nicht jedes Mitglied. -->
                    {#if curriculum.darf_loeschen}
                        <button
                            onclick={() => {
                                deleteError = null;
                                confirmDelete = true;
                            }}
                            class="inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                               text-light-re dark:text-dark-re font-medium
                               hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                        >
                            <Trash2 class="w-4 h-4" /> Löschen
                        </button>
                    {/if}
                </div>
            </div>

            <!-- Export als eigener Block (0.46): Mit Freigabe, Assistent und Löschen standen bis zu
                 neun Knöpfe neben dem Titel. -->
            <div class="flex flex-wrap items-center justify-end gap-2 -mt-3 mb-6">
                <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">Exportieren:</span>
                {#each EXPORTE as e (e.format)}
                    <button
                        onclick={() => handleExport(e.format)}
                        disabled={exporting}
                        title={e.titel}
                        class="inline-flex items-center gap-1 px-2.5 py-1 text-xs rounded-md border border-light-ui-3 dark:border-dark-ui-3
                               text-light-tx dark:text-dark-tx font-medium
                               hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
                               disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        <FileDown class="w-3.5 h-3.5" /> {e.label}
                    </button>
                {/each}
            </div>

            {#if curriculum.status === "draft"}
                <div class="mb-4"><InfoBanner message={entwurfHinweis(curriculum)} /></div>
                {#if vorlageHinweis(curriculum)}
                    <div class="mb-4"><InfoBanner message={vorlageHinweis(curriculum)} /></div>
                {/if}
                {#if curriculum.kopie_von}
                    <p class="-mt-2 mb-4 text-xs text-light-tx-2 dark:text-dark-tx-2">
                        Beim Veröffentlichen ersetzt dieser Entwurf
                        <a href="/knowledge/curriculum/{curriculum.kopie_von.id}" class="text-light-bl dark:text-dark-bl hover:underline">„{curriculum.kopie_von.title}“</a>.
                    </p>
                {/if}
            {/if}

            {#if exportError}
                <div
                    class="mb-4 p-3 rounded-md bg-light-re/10 dark:bg-dark-re/10
                             text-light-re dark:text-dark-re text-sm"
                >
                    {exportError}
                </div>
            {/if}

            <CurriculumBandWahl curriculumId={curriculum.id} wert={curriculum.metadata?.band ?? null} />
            <CurriculumRahmen
                rahmen={curriculum.metadata?.rahmen ?? {}}
                jahrgangsstufe={curriculum.metadata?.jahrgangsstufe ?? ""}
                verplant={totalStd}
            />

            <!-- Curriculum-Tabelle -->
            <div
                class="bg-white dark:bg-dark-bg rounded-lg border border-light-ui-3 dark:border-dark-ui-3"
            >
                <CurriculumTable {curriculum} editMode={false} />
            </div>
        {:else}
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                Curriculum nicht gefunden.
            </p>
        {/if}
    </div>

    <!-- Sticky-Footer: überlagert den Inhalt, nur sichtbar wenn obere Aktionen weggescrollt -->
    {#if curriculum && showStickyFooter}
        <div
            class="absolute bottom-0 left-0 right-0 border-t border-light-ui-3 dark:border-dark-ui-3 bg-light-bg/95 dark:bg-dark-bg/95 backdrop-blur px-6 py-2 flex gap-2 justify-end"
        >
            {#if curriculum.can_edit}
                <a
                    href="/knowledge/curriculum/{curriculum.id}/edit"
                    class="inline-flex items-center gap-1.5 px-4 py-1.5 text-sm rounded-md bg-primary dark:bg-primary-dark
                           text-on-fill font-medium hover:opacity-90 transition-opacity"
                >
                    <Pencil class="w-4 h-4" /> Bearbeiten
                </a>
            {/if}
            <button
                onclick={() => handleExport("yaml")}
                disabled={exporting}
                class="inline-flex items-center gap-1.5 px-4 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                       text-light-tx dark:text-dark-tx font-medium
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
                       disabled:opacity-50 disabled:cursor-not-allowed"
            >
                <FileDown class="w-4 h-4" /> YAML
            </button>
            <button
                onclick={() => handleExport("pdf")}
                disabled={exporting}
                class="inline-flex items-center gap-1.5 px-4 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                       text-light-tx dark:text-dark-tx font-medium
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
                       disabled:opacity-50 disabled:cursor-not-allowed"
            >
                <FileDown class="w-4 h-4" /> PDF
            </button>
            <button
                onclick={() => handleExport("docx")}
                disabled={exporting}
                title="Zum Weiterbearbeiten in Word oder LibreOffice. Wieder einlesen lässt sich nur YAML."
                class="inline-flex items-center gap-1.5 px-4 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                       text-light-tx dark:text-dark-tx font-medium
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
                       disabled:opacity-50 disabled:cursor-not-allowed"
            >
                <FileDown class="w-4 h-4" /> DOCX
            </button>
            <button
                onclick={() => handleExport("odt")}
                disabled={exporting}
                title="Zum Weiterbearbeiten in Word oder LibreOffice. Wieder einlesen lässt sich nur YAML."
                class="inline-flex items-center gap-1.5 px-4 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                       text-light-tx dark:text-dark-tx font-medium
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
                       disabled:opacity-50 disabled:cursor-not-allowed"
            >
                <FileDown class="w-4 h-4" /> ODT
            </button>
        </div>
    {/if}
</div>

{#if confirmDelete && curriculum}
    <div
        class="fixed inset-0 z-50 bg-black/30 flex items-center justify-center p-4"
    >
        <div
            class="bg-white dark:bg-dark-bg-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3 p-6 max-w-md w-full"
        >
            <h3
                class="text-lg font-semibold text-light-tx dark:text-dark-tx mb-3"
            >
                Curriculum löschen
            </h3>
            <p class="text-light-tx-2 dark:text-dark-tx-2 mb-4">
                Möchtest du „{curriculum.title}" wirklich löschen? Alle
                enthaltenen Kapitel und Lernsequenzen werden mitgelöscht. Dieser
                Vorgang kann nicht rückgängig gemacht werden.
            </p>
            {#if deleteError}
                <div class="mb-4">
                    <ErrorBanner message={deleteError} />
                </div>
            {/if}
            <div class="flex gap-3 justify-end">
                <button
                    onclick={() => (confirmDelete = false)}
                    disabled={deleting}
                    class="inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                           text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                           disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    <X class="w-4 h-4" /> Abbrechen
                </button>
                <button
                    onclick={handleDelete}
                    disabled={deleting}
                    class="inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-md bg-light-re dark:bg-dark-re text-on-fill
                           hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    <Trash2 class="w-4 h-4" /> {deleting ? "Wird gelöscht…" : "Löschen"}
                </button>
            </div>
        </div>
    </div>
{/if}

{#if relinkPreview}
    <div class="fixed inset-0 z-50 bg-black/30 flex items-center justify-center p-4">
        <div class="bg-white dark:bg-dark-bg-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3 p-6 max-w-md w-full">
            <h3 class="text-lg font-semibold text-light-tx dark:text-dark-tx mb-3">
                Bildungsplan aktualisieren
            </h3>
            {#if relinkError}
                <div class="mb-4"><ErrorBanner message={relinkError} /></div>
            {/if}
            {#if relinkPreview.mode === "none"}
                <p class="text-light-tx-2 dark:text-dark-tx-2 mb-4">
                    Das Curriculum ist bereits auf der aktuellen Bildungsplan-Fassung
                    (BP {relinkPreview.current_bp_version || "—"}). Keine Aktualisierung nötig.
                </p>
                <div class="flex justify-end">
                    <button
                        onclick={() => (relinkPreview = null)}
                        class="inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                               text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
                    ><X class="w-4 h-4" /> Schließen</button>
                </div>
            {:else}
                <p class="text-light-tx-2 dark:text-dark-tx-2 mb-2">
                    {#if relinkPreview.mode === "duplicate"}
                        Der Bildungsplan gilt nur für einen Teil des Jahrgangsbandes in der neuen
                        Fassung (BP {relinkPreview.target_bp_version}). Es wird eine <strong>Kopie</strong>
                        auf die neue Fassung angelegt; das Original (BP {relinkPreview.current_bp_version || "—"})
                        bleibt erhalten.
                    {:else}
                        Das Curriculum wird auf BP {relinkPreview.target_bp_version} aktualisiert.
                    {/if}
                </p>
                <ul class="text-sm text-light-tx dark:text-dark-tx mb-4 list-disc pl-5 space-y-1">
                    <li><strong>{relinkPreview.summary.relink}</strong> Kompetenzen werden auf die neue Fassung umgelinkt.</li>
                    {#if relinkPreview.summary.outdated > 0}
                        <li><strong>{relinkPreview.summary.outdated}</strong> Kompetenzen werden als
                            <span class="text-light-re dark:text-dark-re">veraltet</span> markiert
                            (im aktuellen Bildungsplan nicht mehr enthalten oder inhaltlich geändert) — bitte danach prüfen.</li>
                    {/if}
                    {#if relinkPreview.summary.current > 0}
                        <li>{relinkPreview.summary.current} sind bereits aktuell.</li>
                    {/if}
                </ul>
                <div class="flex gap-3 justify-end">
                    <button
                        onclick={() => (relinkPreview = null)}
                        disabled={relinkBusy}
                        class="inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                               text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                               disabled:opacity-50 disabled:cursor-not-allowed"
                    ><X class="w-4 h-4" /> Abbrechen</button>
                    <button
                        onclick={handleRelinkApply}
                        disabled={relinkBusy}
                        class="inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-md bg-primary dark:bg-primary-dark text-on-fill
                               hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
                    ><RefreshCw class="w-4 h-4" /> {relinkBusy ? "Wird angewendet…" : (relinkPreview.mode === "duplicate" ? "Kopie anlegen" : "Aktualisieren")}</button>
                </div>
            {/if}
        </div>
    </div>
{/if}
