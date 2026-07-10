<script>
    import { AlertCircle, BookmarkPlus, Check, Download, FileText, FileEdit, Image } from 'lucide-svelte';
    import { goto } from '$app/navigation';
    import { renderMarkdown } from '$lib/markdown.js';
    import { renderDiagrams } from '$lib/diagrams.js';
    import { renderServerBlocks } from '$lib/serverRender.js';
    import { saveImageToLibrary, saveDiagramToLibrary, getPlotGgbBlob, createDocument } from '$lib/api.js';
    import { deriveDocTitle } from '$lib/workshop.js';
    import { triggerDownload } from '$lib/download.js';
    import HelpResourcesBanner from '$lib/components/HelpResourcesBanner.svelte';

    let { message, isStreaming = false, costEur = null } = $props();

    let renderedContent = $derived(
        message.role === 'assistant' ? renderMarkdown(message.content) : ''
    );

    // Generierte Bilder (Phase 16): fehlgeschlagene Ladevorgänge je image_id merken.
    let failedImages = $state(new Set());
    function onImageError(id) {
        failedImages = new Set(failedImages).add(id);
    }

    // „In Bibliothek speichern" (Phase 18): Status je Bild — idle | saving | saved | exists | full | error.
    let imageSaveState = $state({});
    async function saveImage(imageId) {
        if (imageSaveState[imageId] === 'saving') return;
        imageSaveState = { ...imageSaveState, [imageId]: 'saving' };
        try {
            const r = await saveImageToLibrary(imageId);
            imageSaveState = { ...imageSaveState, [imageId]: r.created ? 'saved' : 'exists' };
        } catch (e) {
            imageSaveState = { ...imageSaveState, [imageId]: e?.status === 409 ? 'full' : 'error' };
        }
        setTimeout(() => {
            imageSaveState = { ...imageSaveState, [imageId]: 'idle' };
        }, 2500);
    }
    function imageSaveTitle(state) {
        return {
            saving: 'Wird gespeichert…',
            saved: 'In Bibliothek gespeichert',
            exists: 'Bereits in der Bibliothek',
            full: 'Bibliothek voll',
            error: 'Speichern fehlgeschlagen',
        }[state] ?? 'In Bibliothek speichern';
    }

    // Server-/Client-gerenderte Diagramme (circuit/plot/mermaid) bekommen einen
    // „In Bibliothek speichern"-Knopf, sobald sie erfolgreich zu SVG gerendert wurden.
    // Die Rohquelle liegt in `data-source` (von serverRender.js/diagrams.js gestasht).
    const DIAGRAM_KIND = { 'circuit-block': 'circuit', 'plot-block': 'plot', 'mermaid-block': 'mermaid' };
    function libraryButtons(node) {
        function attach() {
            node.querySelectorAll('.circuit-block, .plot-block, .mermaid-block').forEach((block) => {
                if (block.hasAttribute('data-lib-attached')) return;
                if (!block.dataset.source) return;        // Rohquelle noch nicht gestasht
                if (!block.querySelector('svg')) return;   // noch nicht erfolgreich gerendert
                const cls = [...block.classList].find((c) => DIAGRAM_KIND[c]);
                const kind = cls && DIAGRAM_KIND[cls];
                if (!kind) return;

                block.setAttribute('data-lib-attached', '');
                block.style.position = 'relative';
                block.classList.add('group');

                const bar = document.createElement('div');
                bar.className = [
                    'absolute top-1.5 right-1.5 flex gap-1',
                    'opacity-0 group-hover:opacity-100 transition-opacity',
                ].join(' ');

                const btnClass = [
                    'px-1.5 py-0.5 rounded text-xs',
                    'bg-light-bg-2/80 dark:bg-dark-bg-2/80',
                    'text-light-tx-2 dark:text-dark-tx-2',
                    'hover:bg-light-ui-3 dark:hover:bg-dark-ui-3',
                ].join(' ');

                const saveBtn = document.createElement('button');
                saveBtn.type = 'button';
                saveBtn.setAttribute('aria-label', 'In Bibliothek speichern');
                saveBtn.title = 'In Bibliothek speichern';
                saveBtn.className = btnClass;
                saveBtn.textContent = 'In Bibliothek';
                saveBtn.addEventListener('click', async () => {
                    if (saveBtn.disabled) return;
                    saveBtn.disabled = true;
                    const src = block.dataset.source ?? '';
                    const svg = kind === 'mermaid' ? block.querySelector('svg')?.outerHTML ?? null : null;
                    try {
                        const r = await saveDiagramToLibrary(kind, src, { svg });
                        saveBtn.textContent = r.created ? '✓ Gespeichert' : '✓ Vorhanden';
                    } catch (e) {
                        saveBtn.textContent = e?.status === 409 ? 'Voll' : 'Fehler';
                    }
                    setTimeout(() => { saveBtn.textContent = 'In Bibliothek'; saveBtn.disabled = false; }, 2200);
                });
                bar.appendChild(saveBtn);

                // Funktionsgraphen zusätzlich als GeoGebra-Datei (.ggb) herunterladbar.
                if (kind === 'plot') {
                    const ggbBtn = document.createElement('button');
                    ggbBtn.type = 'button';
                    ggbBtn.setAttribute('aria-label', 'Als GeoGebra-Datei herunterladen');
                    ggbBtn.title = 'Als GeoGebra-Datei (.ggb) herunterladen';
                    ggbBtn.className = btnClass;
                    ggbBtn.textContent = 'GeoGebra';
                    ggbBtn.addEventListener('click', async () => {
                        if (ggbBtn.disabled) return;
                        ggbBtn.disabled = true;
                        try {
                            const blob = await getPlotGgbBlob(block.dataset.source ?? '');
                            triggerDownload(blob, 'funktionsgraph.ggb');
                            ggbBtn.textContent = '✓ .ggb';
                        } catch {
                            ggbBtn.textContent = 'Fehler';
                        }
                        setTimeout(() => { ggbBtn.textContent = 'GeoGebra'; ggbBtn.disabled = false; }, 2200);
                    });
                    bar.appendChild(ggbBtn);
                }

                block.appendChild(bar);
            });
        }

        attach();
        const observer = new MutationObserver(attach);
        observer.observe(node, { childList: true, subtree: true });
        return { destroy() { observer.disconnect(); } };
    }

    // Svelte-Action: Copy-Buttons in code-block-Containern einbinden
    function copyButtons(node) {
        function attachButtons() {
            node.querySelectorAll('.code-block:not([data-copy-attached])').forEach(block => {
                block.setAttribute('data-copy-attached', '');

                const btn = document.createElement('button');
                btn.setAttribute('aria-label', 'Code kopieren');
                btn.className = [
                    'copy-btn',
                    'absolute top-1.5 right-1.5',
                    'px-1.5 py-0.5 rounded text-xs',
                    'bg-light-ui-2 dark:bg-dark-ui-2',
                    'text-light-tx-2 dark:text-dark-tx-2',
                    'hover:bg-light-ui-3 dark:hover:bg-dark-ui-3',
                    'transition-colors',
                ].join(' ');
                btn.textContent = 'Kopieren';

                btn.addEventListener('click', async () => {
                    const code = block.querySelector('code')?.textContent ?? '';
                    try {
                        await navigator.clipboard.writeText(code);
                        btn.textContent = '\u2713';
                        setTimeout(() => { btn.textContent = 'Kopieren'; }, 1500);
                    } catch {
                        btn.textContent = 'Fehler';
                        setTimeout(() => { btn.textContent = 'Kopieren'; }, 1500);
                    }
                });

                block.appendChild(btn);
            });
        }

        attachButtons();

        // Re-trigger wenn Inhalt sich ändert (Streaming: neue Code-Blöcke erscheinen)
        const observer = new MutationObserver(attachButtons);
        observer.observe(node, { childList: true, subtree: true });

        return {
            destroy() { observer.disconnect(); }
        };
    }

    // „In Werkstatt öffnen" (Phase 19): den Antworttext als Markdown-Dokument ablegen
    // und in den Editor springen.
    let openingWorkshop = $state(false);
    let workshopError = $state(null);
    async function openInWorkshop() {
        if (openingWorkshop) return;
        openingWorkshop = true;
        workshopError = null;
        try {
            const doc = await createDocument(deriveDocTitle(message.content), message.content ?? '');
            await goto(`/library/${doc.id}/edit`);
        } catch (e) {
            openingWorkshop = false;
            workshopError = e?.status === 409
                ? 'Bibliothek voll — bitte zuerst aufräumen.'
                : 'Konnte nicht in die Werkstatt übernommen werden.';
        }
    }
</script>

{#if message.role === 'user'}
    <div class="flex justify-end">
        <div class="bg-primary dark:bg-primary-dark text-white rounded-xl rounded-br-none px-4 py-2 max-w-[80%]">
            {#if message.content}
                <p class="whitespace-pre-wrap">{message.content}</p>
            {/if}
            {#if message.uploadedAttachments?.length}
                <div class="flex flex-wrap gap-1 {message.content ? 'mt-2' : ''}">
                    {#each message.uploadedAttachments as att}
                        <span class="inline-flex items-center gap-1 text-xs
                                     bg-white/20 rounded-full px-2 py-0.5">
                            {#if att.result.type === 'image'}
                                <Image class="w-3 h-3 shrink-0" />
                            {:else}
                                <FileText class="w-3 h-3 shrink-0" />
                            {/if}
                            <span class="max-w-[100px] truncate">{att.filename}</span>
                        </span>
                    {/each}
                </div>
            {/if}
        </div>
    </div>

{:else if message.role === 'assistant'}
    <div class="flex flex-col items-start">
        {#if message.content || isStreaming}
        <div class="bg-light-secondary dark:bg-dark-secondary rounded-xl rounded-bl-none px-4 py-3 max-w-[80%]">
            <div class="prose dark:prose-invert max-w-none
                        prose-p:my-1 prose-headings:mt-3 prose-headings:mb-1
                        prose-pre:p-0 prose-pre:bg-transparent prose-pre:rounded-none prose-pre:my-0
                        prose-code:bg-transparent prose-code:before:content-none prose-code:after:content-none
                        prose-p:text-light-tx dark:prose-p:text-dark-tx
                        prose-headings:text-light-tx dark:prose-headings:text-dark-tx
                        prose-strong:text-light-tx dark:prose-strong:text-dark-tx
                        prose-a:text-light-bl dark:prose-a:text-dark-bl
                        prose-code:text-light-tx dark:prose-code:text-dark-tx
                        prose-blockquote:text-light-tx-2 dark:prose-blockquote:text-dark-tx-2"
                 use:copyButtons use:renderDiagrams use:renderServerBlocks use:libraryButtons>
                {@html renderedContent}
            </div>
            {#if isStreaming}
                <span class="animate-pulse cursor-default text-light-tx-2 dark:text-dark-tx-2 text-sm ml-0.5">|</span>
            {/if}
            {#if costEur !== null}
                <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mt-2 pt-1
                           border-t border-light-ui-3 dark:border-dark-ui-3">
                    {costEur} €
                </p>
            {/if}
        </div>
        {/if}
        {#if message.content && !isStreaming}
            <div class="mt-1 max-w-[80%]">
                <button
                    type="button"
                    onclick={openInWorkshop}
                    disabled={openingWorkshop}
                    class="inline-flex items-center gap-1 text-xs px-2 py-1 rounded
                           text-light-tx-2 dark:text-dark-tx-2
                           hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
                           disabled:opacity-50"
                >
                    <FileEdit class="w-3.5 h-3.5" />
                    {openingWorkshop ? 'Wird geöffnet…' : 'In Werkstatt öffnen'}
                </button>
                {#if workshopError}
                    <p class="text-xs text-light-re dark:text-dark-re mt-0.5">{workshopError}</p>
                {/if}
            </div>
        {/if}
        {#if message.images?.length}
            <div class="flex flex-col gap-2 mt-2 max-w-[80%]">
                {#each message.images as img (img.image_id)}
                    {#if failedImages.has(img.image_id)}
                        <div class="flex items-center gap-2 text-sm text-light-tx-2 dark:text-dark-tx-2
                                    border border-light-ui-3 dark:border-dark-ui-3 rounded-xl px-4 py-3">
                            <AlertCircle class="w-4 h-4 shrink-0" />
                            Bild konnte nicht geladen werden.
                        </div>
                    {:else}
                        <div class="group relative inline-block">
                            <img
                                src="/api/images/{img.image_id}"
                                alt="Generiertes Bild"
                                loading="lazy"
                                class="rounded-xl max-w-full h-auto border border-light-ui-3 dark:border-dark-ui-3"
                                onerror={() => onImageError(img.image_id)}
                            />
                            <div class="absolute top-1.5 right-1.5 flex gap-1
                                        opacity-0 group-hover:opacity-100 transition-opacity">
                                <button
                                    type="button"
                                    onclick={() => saveImage(img.image_id)}
                                    disabled={imageSaveState[img.image_id] === 'saving'}
                                    aria-label={imageSaveTitle(imageSaveState[img.image_id])}
                                    title={imageSaveTitle(imageSaveState[img.image_id])}
                                    class="p-1.5 rounded-lg
                                           bg-light-bg-2/80 dark:bg-dark-bg-2/80
                                           text-light-tx-2 dark:text-dark-tx-2
                                           hover:bg-light-ui-3 dark:hover:bg-dark-ui-3"
                                >
                                    {#if imageSaveState[img.image_id] === 'saved' || imageSaveState[img.image_id] === 'exists'}
                                        <Check class="w-4 h-4" />
                                    {:else if imageSaveState[img.image_id] === 'full' || imageSaveState[img.image_id] === 'error'}
                                        <AlertCircle class="w-4 h-4" />
                                    {:else}
                                        <BookmarkPlus class="w-4 h-4" />
                                    {/if}
                                </button>
                                <a
                                    href="/api/images/{img.image_id}"
                                    download="bild-{img.image_id}.png"
                                    aria-label="Bild herunterladen"
                                    class="p-1.5 rounded-lg
                                           bg-light-bg-2/80 dark:bg-dark-bg-2/80
                                           text-light-tx-2 dark:text-dark-tx-2
                                           hover:bg-light-ui-3 dark:hover:bg-dark-ui-3"
                                >
                                    <Download class="w-4 h-4" />
                                </a>
                            </div>
                        </div>
                    {/if}
                {/each}
                <!-- Jugendschutz-/Qualitätshinweis zu KI-Bildern (Phase 16 Schritt 9) -->
                <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                    KI-erzeugte Bilder können fehlerhaft sein und eignen sich nicht
                    zur Darstellung realer Personen.
                </p>
            </div>
        {/if}
        {#if message.crisis}
            <div class="max-w-[80%] w-full">
                <HelpResourcesBanner topic={message.crisis} />
            </div>
        {/if}
    </div>

{:else if message.role === 'error'}
    <div class="w-full">
        <div class="flex items-start gap-2 bg-light-re-bg dark:bg-dark-re-bg/20
                    border border-red-200 dark:border-red-900
                    rounded-lg px-4 py-3 text-light-re dark:text-dark-re">
            <AlertCircle class="w-4 h-4 mt-0.5 shrink-0" />
            <p class="text-sm whitespace-pre-wrap">{message.content}</p>
        </div>
    </div>
{:else if message.role === 'change'}
    <div class="w-full">
        <div class="flex items-center gap-2 my-1 text-xs text-light-tx-2 dark:text-dark-tx-2">
            <span class="flex-1 border-t border-light-ui-3 dark:border-dark-ui-3"></span>
            <span class="shrink-0 px-1">
                {#if message.model}Modell: {message.model}{/if}{#if message.model && message.assistantName} · {/if}{#if message.assistantName}Assistent: {message.assistantName}{/if}
            </span>
            <span class="flex-1 border-t border-light-ui-3 dark:border-dark-ui-3"></span>
        </div>
    </div>
{/if}
