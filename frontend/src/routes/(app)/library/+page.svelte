<script>
    import PageBody from '$lib/components/PageBody.svelte'
    import { goto } from '$app/navigation';
    import { page } from '$app/stores';
    import { subjectMap } from '$lib/stores/subjects.js';
    import {
        Library, Download, FileDown, Copy, Check, Trash2, Loader2, FileText, FilePlus, FileEdit, Quote,
        Share2,
    } from 'lucide-svelte';
    import { getLibrary, deleteArtifact, createDocument } from '$lib/api.js';
    import UebernahmeDialog from '$lib/components/UebernahmeDialog.svelte';
    import { triggerDownload } from '$lib/download.js';
    import {
        kindLabel, mimeExt, codeExt, formatBytes, usagePercent,
        isImageLike, isSvg, slugify,
    } from '$lib/library.js';
    import { zitiername, zitatText, zeitpunkt } from '$lib/provenance.js';
    import { branding } from '$lib/branding.js';
    import ErrorBanner from '$lib/components/ErrorBanner.svelte';

    let items = $state([]);
    let usedBytes = $state(0);
    let quotaBytes = $state(0);
    let loading = $state(true);
    let error = $state(null);

    let confirmDeleteId = $state(null);
    let copiedId = $state(null);
    let busyId = $state(null);
    // Das Artefakt, das gerade in den Wissensgraphen übernommen wird (AP8).
    let uebernahmeItem = $state(null);

    let usage = $derived(usagePercent(usedBytes, quotaBytes));

    // ── Fachfilter ────────────────────────────────────────────────────────────
    // Einstieg von der Fach-/Gruppenseite: „alle Artefakte in Mathematik". Der
    // Bezug kommt aus dem Chat, in dem das Artefakt entstand — ein Artefakt ohne
    // Herkunfts-Chat erscheint deshalb nur in der vollen Liste. Das steht als
    // Hinweis am gefilterten Zustand, sonst wirkt die Lücke wie ein Fehler.
    const filterSubjectId = $derived.by(() => {
        const roh = $page.url.searchParams.get('subject_id');
        const zahl = roh == null ? NaN : Number(roh);
        return Number.isInteger(zahl) ? zahl : null;
    });
    const filterFach = $derived(
        filterSubjectId == null ? null : ($subjectMap[filterSubjectId] ?? null),
    );

    async function load() {
        loading = true;
        error = null;
        try {
            const data = await getLibrary({ subjectId: filterSubjectId });
            items = data.items ?? [];
            usedBytes = data.used_bytes ?? 0;
            quotaBytes = data.quota_bytes ?? 0;
        } catch (err) {
            error = err.message ?? 'Bibliothek konnte nicht geladen werden.';
        } finally {
            loading = false;
        }
    }

    // Kein `onMount`: Der Filter steht in der Adresszeile, und ein Wechsel
    // zwischen „alle" und einem Fach ist eine Navigation ohne Neuaufbau der Seite.
    $effect(() => {
        filterSubjectId;
        load();
    });

    let creatingDoc = $state(false);
    async function newDocument() {
        if (creatingDoc) return;
        creatingDoc = true;
        error = null;
        try {
            const doc = await createDocument('Neues Dokument', '');
            await goto(`/library/${doc.id}/edit`);
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

    async function confirmDelete(item) {
        busyId = item.id;
        try {
            await deleteArtifact(item.id);
            items = items.filter((i) => i.id !== item.id);
            usedBytes = Math.max(0, usedBytes - item.byte_size);
            confirmDeleteId = null;
        } catch (err) {
            error = err.message ?? 'Löschen fehlgeschlagen.';
        } finally {
            busyId = null;
        }
    }
</script>

<PageBody breit>
    <div class="max-w-5xl mx-auto">
        <div class="flex items-center justify-between gap-2 mb-2">
            <div class="flex items-center gap-2 text-light-tx dark:text-dark-tx">
                <Library class="w-6 h-6" />
                <h1 class="text-2xl font-semibold">Bibliothek</h1>
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
        {#if filterSubjectId != null}
            <div class="mb-4 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                    Nur Artefakte aus Chats
                    {#if filterFach}
                        im Fach <span class="font-medium text-light-tx dark:text-dark-tx">{filterFach.name}</span>.
                    {:else}
                        eines Fachs.
                    {/if}
                    Was ohne Chat entstanden ist, steht nur in der vollen Liste.
                </p>
                <a href="/library" class="text-sm text-light-bl dark:text-dark-bl hover:underline">
                    alle anzeigen
                </a>
            </div>
        {:else}
            <p class="mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2">
                Deine gespeicherten Bilder, Diagramme und Dokumente. Sie bleiben unabhängig vom Chat
                erhalten, bis du sie löschst oder die Aufbewahrungsfrist abläuft.
            </p>
        {/if}

        {#if !loading && quotaBytes > 0}
            <div class="mb-6">
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

        {#if error}
            <div class="mb-4"><ErrorBanner message={error} /></div>
        {/if}

        {#if loading}
            <div class="flex items-center justify-center py-12">
                <div class="flex flex-col items-center gap-2 text-light-tx-2 dark:text-dark-tx-2">
                    <Loader2 class="w-6 h-6 animate-spin" />
                    <p>Bibliothek wird geladen…</p>
                </div>
            </div>
        {:else if items.length === 0}
            <div class="text-center py-12 text-light-tx-3 dark:text-dark-tx-3">
                {#if filterSubjectId != null}
                    <!-- Nicht „deine Bibliothek ist leer" sagen, wenn nur der Auszug
                         leer ist — das wäre eine falsche Auskunft über den Bestand. -->
                    <p class="text-lg">
                        Hier ist noch nichts{filterFach ? ` aus ${filterFach.name}` : ''}.
                    </p>
                    <p class="text-sm mt-1">
                        <a href="/library" class="text-light-bl dark:text-dark-bl hover:underline">
                            Alle Artefakte anzeigen
                        </a>
                    </p>
                {:else}
                    <p class="text-lg">Deine Bibliothek ist noch leer.</p>
                    <p class="text-sm mt-1">
                        Speichere Bilder oder Diagramme aus dem Chat über
                        „In Bibliothek speichern“.
                    </p>
                {/if}
            </div>
        {:else}
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {#each items as item (item.id)}
                    <div class="flex flex-col bg-light-bg-2 dark:bg-dark-bg-2
                                border border-light-ui-3 dark:border-dark-ui-3 rounded-lg overflow-hidden">
                        <!-- Vorschau -->
                        <div class="flex items-center justify-center bg-white h-40 overflow-hidden">
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
                        </div>

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
                            <p class="font-medium text-light-tx dark:text-dark-tx truncate" title={item.title}>
                                {item.title}
                            </p>
                            <p class="text-xs text-light-tx-3 dark:text-dark-tx-3 mt-0.5">
                                Gespeichert {fmtDate(item.created_at)} · gültig bis {fmtDate(item.expires_at)}
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

                            <!-- Aktionen -->
                            <div class="flex flex-wrap items-center gap-1 mt-3 pt-2
                                        border-t border-light-ui-3 dark:border-dark-ui-3">
                                {#if zitiername(item.provider_model)}
                                    <button
                                        type="button"
                                        onclick={() => copyZitat(item)}
                                        title="Werkzeug, Modell und Datum als Textbaustein"
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
                                        href="/library/{item.id}/edit"
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
                                        title="Als Baustein in den Wissensgraphen übernehmen"
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
                                                Löschen?
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
                {/each}
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
