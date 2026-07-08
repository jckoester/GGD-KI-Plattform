<script>
    import { onMount } from 'svelte';
    import {
        Library, Download, FileDown, Copy, Check, Trash2, Loader2, FileText,
    } from 'lucide-svelte';
    import { getLibrary, deleteArtifact } from '$lib/api.js';
    import {
        kindLabel, mimeExt, codeExt, formatBytes, usagePercent,
        isImageLike, isSvg, slugify,
    } from '$lib/library.js';
    import ErrorBanner from '$lib/components/ErrorBanner.svelte';

    let items = $state([]);
    let usedBytes = $state(0);
    let quotaBytes = $state(0);
    let loading = $state(true);
    let error = $state(null);

    let confirmDeleteId = $state(null);
    let copiedId = $state(null);
    let busyId = $state(null);

    let usage = $derived(usagePercent(usedBytes, quotaBytes));

    async function load() {
        loading = true;
        error = null;
        try {
            const data = await getLibrary();
            items = data.items ?? [];
            usedBytes = data.used_bytes ?? 0;
            quotaBytes = data.quota_bytes ?? 0;
        } catch (err) {
            error = err.message ?? 'Bibliothek konnte nicht geladen werden.';
        } finally {
            loading = false;
        }
    }

    onMount(load);

    function fmtDate(iso) {
        try {
            return new Date(iso).toLocaleDateString('de-DE', {
                day: '2-digit', month: '2-digit', year: 'numeric',
            });
        } catch {
            return '';
        }
    }

    function triggerDownload(blob, filename) {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
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

<div class="h-full overflow-y-auto p-6">
    <div class="max-w-5xl mx-auto">
        <div class="flex items-center gap-2 mb-2 text-light-tx dark:text-dark-tx">
            <Library class="w-6 h-6" />
            <h1 class="text-2xl font-semibold">Bibliothek</h1>
        </div>
        <p class="mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2">
            Deine gespeicherten Bilder und Diagramme. Sie bleiben unabhängig vom Chat erhalten,
            bis du sie löschst oder die Aufbewahrungsfrist abläuft.
        </p>

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
                <p class="text-lg">Deine Bibliothek ist noch leer.</p>
                <p class="text-sm mt-1">
                    Speichere Bilder oder Diagramme aus dem Chat über
                    „In Bibliothek speichern“.
                </p>
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

                            <!-- Aktionen -->
                            <div class="flex flex-wrap items-center gap-1 mt-3 pt-2
                                        border-t border-light-ui-3 dark:border-dark-ui-3">
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
</div>
