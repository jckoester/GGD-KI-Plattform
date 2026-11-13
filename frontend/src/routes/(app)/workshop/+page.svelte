<script>
    import UebergangsHinweis from "$lib/components/UebergangsHinweis.svelte";
    import { WERKSTATT_NEUIGKEIT } from "$lib/neuigkeiten.js";
    import PageBody from '$lib/components/PageBody.svelte'
    import StufenHinweis from '$lib/components/StufenHinweis.svelte'
    import { goto } from '$app/navigation';
    import { page } from '$app/stores';
    import { subjectMap } from '$lib/stores/subjects.js';
    import {
        Library, Download, FileDown, Copy, Check, Trash2, Loader2, FileText, FilePlus, FileEdit, Quote,
        Share2,
    } from 'lucide-svelte';
    import { getLibrary, deleteArtifact, createDocument, getPreferences, patchPreferences } from '$lib/api.js';
    import { subjects } from '$lib/stores/subjects.js';
    import { ladeProduktarten } from '$lib/produktarten.js';
    import ProduktAngaben from '$lib/components/ProduktAngaben.svelte';
    import { Pencil, Search, X } from 'lucide-svelte';
    import UebernahmeDialog from '$lib/components/UebernahmeDialog.svelte';
    import { triggerDownload } from '$lib/download.js';
    import {
        kindLabel, mimeExt, codeExt, formatBytes, usagePercent,
        isImageLike, isSvg, slugify,
        werkstattArten, SORTIERUNGEN, ANSICHT_SCHLUESSEL, ansichtAusEinstellungen,
        filterAusAdresse, adresseAusFilter, filterGesetzt, nachFachGruppiert,
    } from '$lib/library.js';
    import { zitiername, zitatText, zeitpunkt } from '$lib/provenance.js';
    import { branding } from '$lib/branding.js';
    import ErrorBanner from '$lib/components/ErrorBanner.svelte';
    import { BADGE } from '$lib/badges.js';

    let items = $state([]);
    let total = $state(0);
    let usedBytes = $state(0);
    let quotaBytes = $state(0);
    let loading = $state(true);
    let mehrLaedt = $state(false);
    let error = $state(null);
    // Auswahl der Filter aus dem ganzen eigenen Bestand (nicht aus dem gefilterten).
    let faecherIds = $state([]);
    let themen = $state([]);
    let arten = $state(werkstattArten([]));

    let confirmDeleteId = $state(null);
    let copiedId = $state(null);
    let busyId = $state(null);
    let bearbeiteId = $state(null);
    // Das Produkt, das gerade als Baustein in die Bibliothek übernommen wird (AP8).
    let uebernahmeItem = $state(null);

    let usage = $derived(usagePercent(usedBytes, quotaBytes));

    /** So viele Produkte je Abruf; „Mehr laden“ holt die nächsten. */
    const SEITE = 60;

    // ── Filter (Adresszeile) und Ansicht (Einstellungen, F10) ───────────────
    // Der Filter steht in der Adresse: Links wie „Produkte in Mathematik“ von der Fachseite
    // und der Zurück-Knopf tragen ihn. Sortierung und Gruppierung sind eine Gewohnheit der
    // Person und werden in ihren Einstellungen gemerkt.
    const filter = $derived(filterAusAdresse($page.url.searchParams));
    let ansicht = $state({ sort: 'updated', gruppiert: false });
    let ansichtGeladen = $state(false);

    const faecherAlle = $derived(
        [...($subjects ?? [])].sort((a, b) => a.name.localeCompare(b.name, 'de')),
    );
    const faecherImBestand = $derived(
        faecherIds.map((id) => ({ id, name: $subjectMap[id]?.name ?? 'Unbekanntes Fach' }))
            .sort((a, b) => a.name.localeCompare(b.name, 'de')),
    );
    const gruppen = $derived(nachFachGruppiert(items, $subjectMap));

    function setzeFilter(teil) {
        goto(`/workshop${adresseAusFilter({ ...filter, ...teil })}`, { keepFocus: true, noScroll: true });
    }

    // Suche: tippen, kurz warten, dann in die Adresse — ohne für jeden Buchstaben einen
    // Eintrag im Verlauf.
    // svelte-ignore state_referenced_locally
    let suchtext = $state(filter.q);
    let suchTimer;
    function suchen() {
        clearTimeout(suchTimer);
        suchTimer = setTimeout(() => {
            goto(`/workshop${adresseAusFilter({ ...filter, q: suchtext.trim() })}`,
                 { keepFocus: true, noScroll: true, replaceState: true });
        }, 300);
    }

    async function ansichtSetzen(teil) {
        ansicht = { ...ansicht, ...teil };
        try {
            await patchPreferences({ [ANSICHT_SCHLUESSEL]: ansicht });
        } catch {
            // Nicht gemerkt, aber angewandt — beim nächsten Besuch gilt wieder die alte.
        }
    }

    async function load({ anhaengen = false } = {}) {
        if (anhaengen) mehrLaedt = true; else loading = true;
        error = null;
        try {
            const data = await getLibrary({
                ...filter, sort: ansicht.sort, limit: SEITE, offset: anhaengen ? items.length : 0,
            });
            items = anhaengen ? [...items, ...(data.items ?? [])] : (data.items ?? []);
            total = data.total ?? items.length;
            usedBytes = data.used_bytes ?? 0;
            quotaBytes = data.quota_bytes ?? 0;
            faecherIds = data.faecher ?? [];
            themen = data.themen ?? [];
        } catch (err) {
            error = err.message ?? 'Werkstatt konnte nicht geladen werden.';
        } finally {
            loading = false;
            mehrLaedt = false;
        }
    }

    $effect(() => {
        getPreferences().then((p) => {
            ansicht = ansichtAusEinstellungen(p);
            ansichtGeladen = true;
        });
        ladeProduktarten().then((p) => (arten = werkstattArten(p)));
    });

    // Neu laden, wenn sich Filter oder Sortierung ändern — erst, wenn die gemerkte Ansicht
    // da ist, sonst käme die erste Liste in der falschen Reihenfolge.
    $effect(() => {
        filter;
        ansicht.sort;
        if (ansichtGeladen) load();
    });

    const CHIP = 'px-2.5 py-1 rounded-full border transition-colors';
    const chip = (aktiv) => aktiv
        ? `${CHIP} border-light-ui-3 dark:border-dark-ui-3 bg-light-ui-2 dark:bg-dark-ui-2 text-light-tx dark:text-dark-tx font-medium`
        : `${CHIP} border-light-ui-2 dark:border-dark-ui-2 text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2`;

    function angabenGespeichert(neu) {
        items = items.map((i) => (i.id === neu.id ? { ...i, ...neu } : i));
        bearbeiteId = null;
        load();   // Filter, Fächer und Themen können sich verschoben haben
    }

    let creatingDoc = $state(false);
    async function newDocument() {
        if (creatingDoc) return;
        creatingDoc = true;
        error = null;
        try {
            const doc = await createDocument('Neues Dokument', '');
            await goto(`/workshop/${doc.id}`);
        } catch (err) {
            creatingDoc = false;
            error = err.message ?? 'Dokument konnte nicht angelegt werden.';
        }
    }

    function fmtDate(iso) {
        try {
            return new Date(iso).toLocaleDateString('de-DE', {
                day: '2-digit', month: '2-digit', year: 'numeric',
            });
        } catch {
            return '';
        }
    }

    function downloadOriginal(item) {
        // Direkter, authentifizierter Download über das Serving-Endpoint.
        const a = document.createElement('a');
        a.href = `/api/artifacts/${item.id}`;
        a.download = `${slugify(item.title)}.${mimeExt(item.mime_type)}`;
        document.body.appendChild(a);
        a.click();
        a.remove();
    }

    function parseSize(svgText) {
        const doc = new DOMParser().parseFromString(svgText, 'image/svg+xml');
        const svg = doc.documentElement;
        let w = parseFloat(svg.getAttribute('width'));
        let h = parseFloat(svg.getAttribute('height'));
        if (!w || !h) {
            const vb = (svg.getAttribute('viewBox') || '').split(/[\s,]+/).map(Number);
            if (vb.length === 4) { w = w || vb[2]; h = h || vb[3]; }
        }
        return { w: w || 1200, h: h || 800 };
    }

    // SVG → PNG rein im Browser (weißer Hintergrund, 2× für Schärfe). Self-contained SVGs
    // (matplotlib/mermaid/circuit) verunreinigen die Canvas nicht → toBlob funktioniert.
    async function downloadPng(item) {
        busyId = item.id;
        try {
            const res = await fetch(`/api/artifacts/${item.id}`, { credentials: 'include' });
            const svgText = await res.text();
            const { w, h } = parseSize(svgText);
            const scale = 2;
            const dataUrl = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svgText);
            const img = new Image();
            await new Promise((resolve, reject) => {
                img.onload = resolve;
                img.onerror = () => reject(new Error('SVG konnte nicht geladen werden'));
                img.src = dataUrl;
            });
            const canvas = document.createElement('canvas');
            canvas.width = Math.round(w * scale);
            canvas.height = Math.round(h * scale);
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = '#ffffff';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            await new Promise((resolve) => {
                canvas.toBlob((blob) => {
                    if (blob) triggerDownload(blob, `${slugify(item.title)}.png`);
                    resolve();
                }, 'image/png');
            });
        } catch (err) {
            error = err.message ?? 'PNG-Export fehlgeschlagen.';
        } finally {
            busyId = null;
        }
    }

    // Quellenangabe zum Kopieren. Bei einem **Bild** ist `source` der Bild-Prompt und
    // gehört als solcher ins Zitat; bei Dokumenten und Diagrammen ist `source` der Inhalt
    // selbst — ihn als „Eingabe" auszugeben wäre eine Falschangabe.
    let zitatKopiertId = $state(null);
    async function copyZitat(item) {
        const text = zitatText({
            werkzeug: branding.name,
            modell: zitiername(item.provider_model),
            zeitpunkt: zeitpunkt(item.created_at),
            bilder: item.kind === 'image'
                ? [{ modell: zitiername(item.provider_model), prompt: item.source }]
                : [],
        });
        try {
            await navigator.clipboard.writeText(text);
            zitatKopiertId = item.id;
            setTimeout(() => { if (zitatKopiertId === item.id) zitatKopiertId = null; }, 1800);
        } catch {
            error = 'Kopieren in die Zwischenablage fehlgeschlagen.';
        }
    }

    async function copyCode(item) {
        try {
            await navigator.clipboard.writeText(item.source ?? '');
            copiedId = item.id;
            setTimeout(() => { if (copiedId === item.id) copiedId = null; }, 1500);
        } catch {
            error = 'Kopieren in die Zwischenablage fehlgeschlagen.';
        }
    }

    function downloadCode(item) {
        const blob = new Blob([item.source ?? ''], { type: 'text/plain;charset=utf-8' });
        triggerDownload(blob, `${slugify(item.title)}.${codeExt(item.kind)}`);
    }

    async function exportLoeschen(dokument, ex) {
        busyId = ex.id;
        try {
            await deleteArtifact(ex.id);
            items = items.map((i) => (i.id === dokument.id
                ? { ...i, exporte: i.exporte.filter((e) => e.id !== ex.id) }
                : i));
            usedBytes = Math.max(0, usedBytes - ex.byte_size);
        } catch (err) {
            error = err.message ?? 'Löschen fehlgeschlagen.';
        } finally {
            busyId = null;
        }
    }

    async function confirmDelete(item) {
        busyId = item.id;
        try {
            await deleteArtifact(item.id);
            items = items.filter((i) => i.id !== item.id);
            total = Math.max(0, total - 1);
            const exporte = (item.exporte ?? []).reduce((summe, e) => summe + e.byte_size, 0);
            usedBytes = Math.max(0, usedBytes - item.byte_size - exporte);
            confirmDeleteId = null;
        } catch (err) {
            error = err.message ?? 'Löschen fehlgeschlagen.';
        } finally {
            busyId = null;
        }
    }
</script>

{#snippet karte(item)}
        <div class="flex flex-col bg-light-bg-2 dark:bg-dark-bg-2
                    border border-light-ui-3 dark:border-dark-ui-3 rounded-lg overflow-hidden">
            <!-- Vorschau: führt wie der Titel in die Ansicht (Dokument: der Editor). Für
                 Tastatur und Vorleser genügt der Titel-Link, daher hier aus der Reihenfolge. -->
            <a href="/workshop/{item.id}" tabindex="-1" aria-hidden="true"
               class="flex items-center justify-center bg-white h-40 overflow-hidden hover:opacity-90 transition-opacity">
                {#if isImageLike(item.mime_type)}
                    <img
                        src="/api/artifacts/{item.id}"
                        alt={item.title}
                        loading="lazy"
                        class="max-h-40 max-w-full object-contain"
                    />
                {:else}
                    <FileText class="w-10 h-10 text-light-tx-3" />
                {/if}
            </a>

            <div class="flex flex-col flex-1 p-3">
                <div class="flex items-center gap-2 flex-wrap mb-1">
                    <span class="text-xs px-1.5 py-0.5 rounded-full
                                 bg-light-ui-3 dark:bg-dark-ui-3
                                 text-light-tx-2 dark:text-dark-tx-2">
                        {kindLabel(item.kind)}
                    </span>
                    <span class="text-xs text-light-tx-3 dark:text-dark-tx-3">
                        {formatBytes(item.byte_size)}
                    </span>
                </div>
                {#if bearbeiteId === item.id}
                    <ProduktAngaben
                        {item}
                        faecher={faecherAlle}
                        onGespeichert={angabenGespeichert}
                        onAbbrechen={() => (bearbeiteId = null)}
                    />
                {:else}
                    <div class="flex items-start gap-1">
                        <!-- Jedes Produkt hat seine Ansicht (0.41, Schritt 8). -->
                        <a href="/workshop/{item.id}" title={item.title}
                           class="flex-1 font-medium text-light-tx dark:text-dark-tx truncate hover:underline">
                            {item.title}
                        </a>
                        <button
                            type="button"
                            onclick={() => (bearbeiteId = item.id)}
                            aria-label="Titel, Fach und Thema bearbeiten"
                            title="Titel, Fach und Thema bearbeiten"
                            class="shrink-0 p-1 rounded text-light-tx-3 dark:text-dark-tx-3
                                   hover:text-light-tx dark:hover:text-dark-tx
                                   hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
                        >
                            <Pencil class="w-3.5 h-3.5" />
                        </button>
                    </div>
                    {#if item.subject_id != null || item.topic}
                        <p class="flex flex-wrap gap-1 mt-1">
                            {#if item.subject_id != null}
                                <span class={BADGE}>{$subjectMap[item.subject_id]?.name ?? 'Fach'}</span>
                            {/if}
                            {#if item.topic}
                                <span class={BADGE}>{item.topic}</span>
                            {/if}
                        </p>
                    {/if}
                {/if}
                <p class="text-xs text-light-tx-3 dark:text-dark-tx-3 mt-0.5">
                    Bearbeitet {fmtDate(item.updated_at ?? item.created_at)} · gültig bis {fmtDate(item.expires_at)}
                </p>
                <!-- Die Verknüpfung in die Gegenrichtung (AP8): Von hier
                     aus sieht man, dass aus dem Artefakt schon ein Baustein
                     geworden ist — und kommt hin. Ohne das wäre die
                     Übernahme eine Einbahnstraße, und beim zweiten Mal
                     wüsste niemand, ob es sie schon gab. -->
                {#if item.baustein_id}
                    <a
                        href="/knowledge/{item.baustein_id}"
                        title="Zum Baustein „{item.baustein_titel}“"
                        class="mt-1 inline-flex items-center gap-1 self-start max-w-full
                               text-xs px-1.5 py-0.5 rounded-full
                               border border-light-ui-3 dark:border-dark-ui-3
                               text-light-bl dark:text-dark-bl
                               hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                    >
                        <Share2 class="w-3 h-3 shrink-0" />
                        <span class="truncate">als Baustein übernommen →</span>
                    </a>
                {/if}
                <!-- Hier dauerhaft sichtbar, anders als im Chat: Die Bibliothek
                     ist der Ort, an dem man nachsieht, was man zitieren muss. -->
                {#if zitiername(item.provider_model)}
                    <p class="text-xs text-light-tx-3 dark:text-dark-tx-3">
                        Erzeugt mit <span class="font-mono">{zitiername(item.provider_model)}</span>
                    </p>
                {/if}

                <!-- Exporte am Dokument (0.41, F5): eingeklappt, nicht als eigene Karten. -->
        {#if item.exporte?.length}
            <details class="mt-2 text-xs text-light-tx-2 dark:text-dark-tx-2">
                <summary class="cursor-pointer select-none">
                    {item.exporte.length} {item.exporte.length === 1 ? 'Export' : 'Exporte'}
                </summary>
                <ul class="mt-1 space-y-1">
                    {#each item.exporte as ex (ex.id)}
                        <li class="flex items-center gap-2">
                            <span class={BADGE}>{kindLabel(ex.kind)}</span>
                            <span class="flex-1 truncate">{fmtDate(ex.created_at)} · {formatBytes(ex.byte_size)}</span>
                            <a
                                href="/api/artifacts/{ex.id}"
                                download="{slugify(ex.title)}.{mimeExt(ex.mime_type)}"
                                aria-label="Export herunterladen"
                                title="Herunterladen"
                                class="p-1 rounded hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
                            >
                                <Download class="w-3.5 h-3.5" />
                            </a>
                            <button
                                type="button"
                                onclick={() => exportLoeschen(item, ex)}
                                disabled={busyId === ex.id}
                                aria-label="Export löschen"
                                title="Export löschen"
                                class="p-1 rounded hover:text-light-re dark:hover:text-dark-re
                                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 disabled:opacity-50"
                            >
                                <Trash2 class="w-3.5 h-3.5" />
                            </button>
                        </li>
                    {/each}
                </ul>
            </details>
        {/if}

        <!-- Aktionen -->
                <div class="flex flex-wrap items-center gap-1 mt-3 pt-2
                            border-t border-light-ui-3 dark:border-dark-ui-3">
                    {#if zitiername(item.provider_model)}
                        <button
                            type="button"
                            onclick={() => copyZitat(item)}
                            title="Plattform, Modell und Datum als Textbaustein"
                            class="inline-flex items-center gap-1 text-xs px-2 py-1 rounded
                                   text-light-tx-2 dark:text-dark-tx-2
                                   hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                        >
                            {#if zitatKopiertId === item.id}
                                <Check class="w-3.5 h-3.5" /> Kopiert
                            {:else}
                                <Quote class="w-3.5 h-3.5" /> Zitieren
                            {/if}
                        </button>
                    {/if}
                    {#if item.kind === 'document'}
                        <a
                            href="/workshop/{item.id}"
                            class="inline-flex items-center gap-1 text-xs px-2 py-1 rounded
                                   text-light-tx-2 dark:text-dark-tx-2
                                   hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                        >
                            <FileEdit class="w-3.5 h-3.5" /> Bearbeiten
                        </a>
                    {/if}
                    <!-- Ob das geht, sagt der Server (`uebernehmbar`) — sonst
                         zeigte der Knopf irgendwann etwas anderes an, als der
                         Endpunkt erlaubt. -->
                    {#if item.uebernehmbar}
                        <button
                            type="button"
                            onclick={() => (uebernahmeItem = item)}
                            title="Als Baustein in die Bibliothek übernehmen"
                            class="inline-flex items-center gap-1 text-xs px-2 py-1 rounded
                                   text-light-tx-2 dark:text-dark-tx-2
                                   hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                        >
                            <Share2 class="w-3.5 h-3.5" /> Als Baustein
                        </button>
                    {/if}
                    <button
                        type="button"
                        onclick={() => downloadOriginal(item)}
                        class="inline-flex items-center gap-1 text-xs px-2 py-1 rounded
                               text-light-tx-2 dark:text-dark-tx-2
                               hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                    >
                        <Download class="w-3.5 h-3.5" /> Herunterladen
                    </button>

                    {#if isSvg(item.mime_type)}
                        <button
                            type="button"
                            onclick={() => downloadPng(item)}
                            disabled={busyId === item.id}
                            class="inline-flex items-center gap-1 text-xs px-2 py-1 rounded
                                   text-light-tx-2 dark:text-dark-tx-2
                                   hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
                                   disabled:opacity-50"
                        >
                            <FileDown class="w-3.5 h-3.5" /> PNG
                        </button>
                    {/if}

                    {#if item.kind === 'plot'}
                        <a
                            href="/api/artifacts/{item.id}/ggb"
                            download="{slugify(item.title)}.ggb"
                            class="inline-flex items-center gap-1 text-xs px-2 py-1 rounded
                                   text-light-tx-2 dark:text-dark-tx-2
                                   hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                        >
                            <FileDown class="w-3.5 h-3.5" /> GeoGebra
                        </a>
                    {/if}

                    {#if item.source}
                        <button
                            type="button"
                            onclick={() => copyCode(item)}
                            class="inline-flex items-center gap-1 text-xs px-2 py-1 rounded
                                   text-light-tx-2 dark:text-dark-tx-2
                                   hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                        >
                            {#if copiedId === item.id}
                                <Check class="w-3.5 h-3.5" /> Kopiert
                            {:else}
                                <Copy class="w-3.5 h-3.5" /> Code
                            {/if}
                        </button>
                        <button
                            type="button"
                            onclick={() => downloadCode(item)}
                            aria-label="Code herunterladen"
                            title="Code herunterladen"
                            class="inline-flex items-center gap-1 text-xs px-2 py-1 rounded
                                   text-light-tx-2 dark:text-dark-tx-2
                                   hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                        >
                            <FileDown class="w-3.5 h-3.5" /> .{codeExt(item.kind)}
                        </button>
                    {/if}

                    <div class="ml-auto">
                        {#if confirmDeleteId === item.id}
                            <span class="inline-flex items-center gap-1">
                                <button
                                    type="button"
                                    onclick={() => confirmDelete(item)}
                                    disabled={busyId === item.id}
                                    class="text-xs px-2 py-1 rounded
                                           text-light-re dark:text-dark-re
                                           hover:bg-light-re-bg dark:hover:bg-dark-re-bg/20
                                           disabled:opacity-50"
                                >
                                    {item.exporte?.length
                                        ? `Samt ${item.exporte.length} ${item.exporte.length === 1 ? 'Export' : 'Exporten'} löschen?`
                                        : 'Löschen?'}
                                </button>
                                <button
                                    type="button"
                                    onclick={() => (confirmDeleteId = null)}
                                    class="text-xs px-2 py-1 rounded
                                           text-light-tx-2 dark:text-dark-tx-2
                                           hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
                                >
                                    Abbrechen
                                </button>
                            </span>
                        {:else}
                            <button
                                type="button"
                                onclick={() => (confirmDeleteId = item.id)}
                                aria-label="Löschen"
                                title="Löschen"
                                class="inline-flex items-center p-1 rounded
                                       text-light-tx-3 dark:text-dark-tx-3
                                       hover:text-light-re dark:hover:text-dark-re
                                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                            >
                                <Trash2 class="w-3.5 h-3.5" />
                            </button>
                        {/if}
                    </div>
                </div>
            </div>
        </div>
{/snippet}

<PageBody breit>
  <StufenHinweis eintrag="workshop" />
    <div class="max-w-5xl mx-auto">
        <UebergangsHinweis
            neuigkeitId={WERKSTATT_NEUIGKEIT}
            message="Hier liegen jetzt deine gespeicherten Bilder, Diagramme und Dokumente — bisher hieß dieser Bereich „Bibliothek“."
        />
        <div class="flex items-center justify-between gap-2 mb-2">
            <div class="flex items-center gap-2 text-light-tx dark:text-dark-tx">
                <Library class="w-6 h-6" />
                <h1 class="text-2xl font-semibold">Werkstatt</h1>
            </div>
            <button
                type="button"
                onclick={newDocument}
                disabled={creatingDoc}
                class="inline-flex items-center gap-1 text-sm px-3 py-1.5 rounded-lg shrink-0
                       bg-primary dark:bg-primary-dark text-white
                       hover:opacity-90 transition-opacity disabled:opacity-50"
            >
                <FilePlus class="w-4 h-4" /> Neues Dokument
            </button>
        </div>
        <p class="mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2">
            Deine gespeicherten Bilder, Diagramme und Dokumente. Sie bleiben unabhängig vom Chat
            erhalten, bis du sie löschst oder die Aufbewahrungsfrist abläuft.
        </p>

        {#if !loading && quotaBytes > 0}
            <div class="mb-4">
                <div class="flex justify-between text-xs text-light-tx-2 dark:text-dark-tx-2 mb-1">
                    <span>Belegt</span>
                    <span>{formatBytes(usedBytes)} von {formatBytes(quotaBytes)}</span>
                </div>
                <div class="h-2 rounded-full bg-light-ui-2 dark:bg-dark-ui-2 overflow-hidden">
                    <div
                        class="h-full rounded-full bg-primary dark:bg-primary-dark transition-all"
                        style="width: {usage}%"
                    ></div>
                </div>
            </div>
        {/if}

        <!-- Suche, Filter, Ansicht (0.41) -->
        <div class="mb-4 flex flex-col gap-2">
            <div class="flex flex-wrap items-center gap-2">
                <label class="relative flex-1 min-w-48">
                    <span class="sr-only">In der Werkstatt suchen</span>
                    <Search class="w-4 h-4 absolute left-2 top-1/2 -translate-y-1/2 text-light-tx-3 dark:text-dark-tx-3" />
                    <input
                        type="search"
                        bind:value={suchtext}
                        oninput={suchen}
                        placeholder="Titel oder Inhalt suchen"
                        class="w-full pl-8 pr-2 py-1.5 text-sm rounded-lg
                               border border-light-ui-3 dark:border-dark-ui-3
                               bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
                    />
                </label>
                <label class="text-sm text-light-tx-2 dark:text-dark-tx-2 flex items-center gap-1">
                    Sortieren
                    <select
                        value={ansicht.sort}
                        onchange={(e) => ansichtSetzen({ sort: e.currentTarget.value })}
                        class="px-2 py-1.5 text-sm rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                               bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
                    >
                        {#each SORTIERUNGEN as s (s.id)}
                            <option value={s.id}>{s.label}</option>
                        {/each}
                    </select>
                </label>
                <label class="text-sm text-light-tx-2 dark:text-dark-tx-2 flex items-center gap-1 cursor-pointer">
                    <input
                        type="checkbox"
                        checked={ansicht.gruppiert}
                        onchange={(e) => ansichtSetzen({ gruppiert: e.currentTarget.checked })}
                        class="rounded border-light-ui-3 dark:border-dark-ui-3"
                    />
                    nach Fach gruppiert
                </label>
            </div>
            <div class="flex flex-wrap items-center gap-2 text-sm">
                <button type="button" onclick={() => setzeFilter({ art: null })} class={chip(!filter.art)}
                        aria-pressed={!filter.art}>Alle</button>
                {#each arten as a (a.id)}
                    <button type="button" onclick={() => setzeFilter({ art: a.id })} class={chip(filter.art === a.id)}
                            aria-pressed={filter.art === a.id}>{a.label}</button>
                {/each}
                {#if faecherImBestand.length}
                    <select
                        value={filter.subjectId == null ? '' : String(filter.subjectId)}
                        onchange={(e) => setzeFilter({ subjectId: e.currentTarget.value === '' ? null : Number(e.currentTarget.value) })}
                        aria-label="Fach"
                        class="px-2 py-1 rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                               bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
                    >
                        <option value="">Alle Fächer</option>
                        {#each faecherImBestand as f (f.id)}
                            <option value={String(f.id)}>{f.name}</option>
                        {/each}
                    </select>
                {/if}
                {#if themen.length}
                    <select
                        value={filter.topic ?? ''}
                        onchange={(e) => setzeFilter({ topic: e.currentTarget.value || null })}
                        aria-label="Thema"
                        class="px-2 py-1 rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                               bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
                    >
                        <option value="">Alle Themen</option>
                        {#each themen as t (t)}
                            <option value={t}>{t}</option>
                        {/each}
                    </select>
                {/if}
                <button type="button" onclick={() => setzeFilter({ baldAblaufend: !filter.baldAblaufend })}
                        class={chip(filter.baldAblaufend)} aria-pressed={filter.baldAblaufend}>läuft bald ab</button>
                <button type="button" onclick={() => setzeFilter({ alsBaustein: !filter.alsBaustein })}
                        class={chip(filter.alsBaustein)} aria-pressed={filter.alsBaustein}>als Baustein übernommen</button>
            </div>
            {#if filterGesetzt(filter) && !loading}
                <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 flex items-center gap-2">
                    {total} {total === 1 ? 'Produkt' : 'Produkte'} gefunden
                    <a href="/workshop" class="inline-flex items-center gap-0.5 text-light-bl dark:text-dark-bl hover:underline">
                        <X class="w-3 h-3" /> Filter zurücksetzen
                    </a>
                </p>
            {/if}
        </div>

        {#if error}
            <div class="mb-4"><ErrorBanner message={error} /></div>
        {/if}

        {#if loading}
            <div class="flex items-center justify-center py-12">
                <div class="flex flex-col items-center gap-2 text-light-tx-2 dark:text-dark-tx-2">
                    <Loader2 class="w-6 h-6 animate-spin" />
                    <p>Werkstatt wird geladen…</p>
                </div>
            </div>
        {:else if items.length === 0}
            <div class="text-center py-12 text-light-tx-3 dark:text-dark-tx-3">
                {#if filterGesetzt(filter)}
                    <!-- Nicht „deine Werkstatt ist leer“ sagen, wenn nur der Filter nichts
                         findet — das wäre eine falsche Auskunft über den Bestand. -->
                    <p class="text-lg">Dazu ist nichts in deiner Werkstatt.</p>
                    <p class="text-sm mt-1">
                        <a href="/workshop" class="text-light-bl dark:text-dark-bl hover:underline">
                            Alle Produkte anzeigen
                        </a>
                    </p>
                {:else}
                    <p class="text-lg">Deine Werkstatt ist noch leer.</p>
                    <p class="text-sm mt-1">
                        Speichere Bilder oder Diagramme aus dem Chat über
                        „In der Werkstatt speichern“.
                    </p>
                {/if}
            </div>
        {:else if ansicht.gruppiert}
            {#each gruppen as g (g.subjectId ?? 'ohne')}
                <h2 class="text-base font-semibold text-light-tx-2 dark:text-dark-tx-2 mb-3 mt-6 first:mt-0">
                    {g.name}
                </h2>
                <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {#each g.items as item (item.id)}
                        {@render karte(item)}
                    {/each}
                </div>
            {/each}
        {:else}
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {#each items as item (item.id)}
                    {@render karte(item)}
                {/each}
            </div>
        {/if}

        {#if !loading && items.length < total}
            <div class="flex justify-center mt-6">
                <button
                    type="button"
                    onclick={() => load({ anhaengen: true })}
                    disabled={mehrLaedt}
                    class="text-sm px-4 py-1.5 rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                           text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                           disabled:opacity-50"
                >
                    {mehrLaedt ? 'Lädt…' : `Mehr laden (${items.length} von ${total})`}
                </button>
            </div>
        {/if}
    </div>
</PageBody>

{#if uebernahmeItem}
    <UebernahmeDialog
        artefakt={uebernahmeItem}
        onclose={() => (uebernahmeItem = null)}
        ongespeichert={load}
    />
{/if}
