<script>
    import { onMount } from 'svelte';
    import { page } from '$app/stores';
    import { ArrowLeft, Save, Loader2, Download } from 'lucide-svelte';
    import {
        getDocument, updateDocument, getDocumentExportBlob, saveDocumentExport,
    } from '$lib/api.js';
    import { triggerDownload } from '$lib/download.js';
    import { slugify } from '$lib/library.js';
    import { renderMarkdown } from '$lib/markdown.js';
    import { renderDiagrams } from '$lib/diagrams.js';
    import { renderServerBlocks } from '$lib/serverRender.js';
    import ErrorBanner from '$lib/components/ErrorBanner.svelte';

    const EXPORT_FORMATS = [
        { fmt: 'pdf', label: 'PDF' },
        { fmt: 'docx', label: 'Word' },
        { fmt: 'odt', label: 'ODT' },
    ];

    let id = $derived($page.params.id);

    let title = $state('');
    let markdown = $state('');
    let savedTitle = $state('');
    let savedMarkdown = $state('');

    let loading = $state(true);
    let saving = $state(false);
    let error = $state(null);

    let dirty = $derived(title !== savedTitle || markdown !== savedMarkdown);
    let preview = $derived(renderMarkdown(markdown));

    async function load() {
        loading = true;
        error = null;
        try {
            const doc = await getDocument(id);
            title = doc.title ?? '';
            markdown = doc.source ?? '';
            savedTitle = title;
            savedMarkdown = markdown;
        } catch (err) {
            error = err.message ?? 'Dokument konnte nicht geladen werden.';
        } finally {
            loading = false;
        }
    }

    onMount(load);

    async function save() {
        if (saving || !dirty) return;
        saving = true;
        error = null;
        try {
            await updateDocument(id, title, markdown);
            savedTitle = title;
            savedMarkdown = markdown;
        } catch (err) {
            error = err.message ?? 'Speichern fehlgeschlagen.';
        } finally {
            saving = false;
        }
    }

    // Export (PDF/DOCX/ODT). Der Server exportiert die gespeicherte Fassung — darum
    // ungespeicherte Änderungen zuvor sichern, damit der Export dem Editor entspricht.
    let keepInLibrary = $state(false);
    let exportingFmt = $state(null);
    let exportMsg = $state(null);
    async function doExport(fmt) {
        if (exportingFmt) return;
        exportMsg = null;
        error = null;
        if (dirty) {
            await save();
            if (error) return;   // Speichern fehlgeschlagen → nicht exportieren
        }
        exportingFmt = fmt;
        try {
            if (keepInLibrary) {
                await saveDocumentExport(id, fmt);
                exportMsg = `${fmt.toUpperCase()} in der Bibliothek gespeichert.`;
            } else {
                const blob = await getDocumentExportBlob(id, fmt);
                triggerDownload(blob, `${slugify(title)}.${fmt}`);
            }
        } catch (err) {
            error = err?.status === 503
                ? 'Office-Export ist auf diesem Server nicht verfügbar.'
                : (err.message ?? 'Export fehlgeschlagen.');
        } finally {
            exportingFmt = null;
        }
    }
</script>

<div class="flex flex-col h-full">
    <!-- Kopfleiste -->
    <div class="flex items-center gap-3 px-4 py-2 border-b border-light-ui-3 dark:border-dark-ui-3">
        <a
            href="/library"
            aria-label="Zurück zur Bibliothek"
            class="p-1.5 rounded-lg text-light-tx-2 dark:text-dark-tx-2
                   hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors shrink-0"
        >
            <ArrowLeft class="w-4 h-4" />
        </a>
        <input
            type="text"
            bind:value={title}
            placeholder="Titel"
            aria-label="Titel"
            class="flex-1 min-w-0 bg-transparent text-light-tx dark:text-dark-tx
                   font-medium px-2 py-1 rounded
                   border border-transparent hover:border-light-ui-3 dark:hover:border-dark-ui-3
                   focus:border-primary dark:focus:border-primary-dark focus:outline-none"
        />
        <span class="text-xs text-light-tx-2 dark:text-dark-tx-2 shrink-0">
            {#if saving}Speichert…{:else if dirty}Ungespeicherte Änderungen{:else}Gespeichert{/if}
        </span>
        <button
            type="button"
            onclick={save}
            disabled={saving || !dirty}
            class="inline-flex items-center gap-1 text-sm px-3 py-1.5 rounded-lg shrink-0
                   bg-primary dark:bg-primary-dark text-white
                   hover:opacity-90 transition-opacity disabled:opacity-40"
        >
            <Save class="w-4 h-4" /> Speichern
        </button>
    </div>

    <!-- Export-Leiste -->
    <div class="flex items-center flex-wrap gap-2 px-4 py-1.5 text-xs
                border-b border-light-ui-3 dark:border-dark-ui-3
                text-light-tx-2 dark:text-dark-tx-2">
        <span class="flex items-center gap-1"><Download class="w-3.5 h-3.5" /> Export:</span>
        {#each EXPORT_FORMATS as f}
            <button
                type="button"
                onclick={() => doExport(f.fmt)}
                disabled={exportingFmt !== null}
                class="px-2 py-1 rounded hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                       transition-colors disabled:opacity-50"
            >
                {exportingFmt === f.fmt ? '…' : f.label}
            </button>
        {/each}
        <label class="flex items-center gap-1 ml-1 cursor-pointer select-none">
            <input type="checkbox" bind:checked={keepInLibrary} class="accent-primary" />
            In Bibliothek behalten
        </label>
        {#if exportMsg}
            <span class="text-light-tx-2 dark:text-dark-tx-2">{exportMsg}</span>
        {/if}
    </div>

    {#if error}
        <div class="px-4 pt-2"><ErrorBanner message={error} /></div>
    {/if}

    {#if loading}
        <div class="flex-1 flex items-center justify-center text-light-tx-2 dark:text-dark-tx-2">
            <Loader2 class="w-6 h-6 animate-spin" />
        </div>
    {:else}
        <!-- Editor + Vorschau -->
        <div class="flex-1 grid grid-cols-1 md:grid-cols-2 min-h-0">
            <textarea
                bind:value={markdown}
                spellcheck="false"
                aria-label="Markdown-Quelltext"
                class="w-full h-full resize-none p-4 font-mono text-sm leading-relaxed
                       bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                       border-b md:border-b-0 md:border-r border-light-ui-3 dark:border-dark-ui-3
                       focus:outline-none"
            ></textarea>
            <div class="w-full h-full overflow-y-auto p-4 bg-light-bg-2 dark:bg-dark-bg-2">
                <div class="prose dark:prose-invert max-w-none
                            prose-p:text-light-tx dark:prose-p:text-dark-tx
                            prose-headings:text-light-tx dark:prose-headings:text-dark-tx
                            prose-strong:text-light-tx dark:prose-strong:text-dark-tx
                            prose-a:text-light-bl dark:prose-a:text-dark-bl
                            prose-code:text-light-tx dark:prose-code:text-dark-tx"
                     use:renderDiagrams use:renderServerBlocks>
                    {@html preview}
                </div>
            </div>
        </div>
    {/if}
</div>
