<script>
    import { onMount } from 'svelte';
    import { ArrowLeft, FileText, Upload, Trash2, Loader2 } from 'lucide-svelte';
    import {
        getExportTemplates, updateExportCss, uploadExportReference, deleteExportReference,
    } from '$lib/api.js';
    import ErrorBanner from '$lib/components/ErrorBanner.svelte';
    import SuccessBanner from '$lib/components/SuccessBanner.svelte';
    import InfoBanner from '$lib/components/InfoBanner.svelte';

    let css = $state('');
    let savedCss = $state('');
    let hasDocx = $state(false);
    let hasOdt = $state(false);
    let loading = $state(true);
    let saving = $state(false);
    let error = $state(null);
    let success = $state(null);

    let cssDirty = $derived(css !== savedCss);

    function apply(s) {
        css = s.css ?? '';
        savedCss = css;
        hasDocx = s.has_docx_reference;
        hasOdt = s.has_odt_reference;
    }
    function flash(msg) {
        success = msg;
        setTimeout(() => { if (success === msg) success = null; }, 3000);
    }

    onMount(async () => {
        try { apply(await getExportTemplates()); }
        catch (e) { error = e.message ?? 'Konnte nicht geladen werden.'; }
        finally { loading = false; }
    });

    async function saveCss() {
        if (saving || !cssDirty) return;
        saving = true; error = null; success = null;
        try { apply(await updateExportCss(css)); flash('CSS gespeichert.'); }
        catch (e) { error = e.message; }
        finally { saving = false; }
    }

    async function upload(fmt, ev) {
        const file = ev.target.files?.[0];
        ev.target.value = '';
        if (!file) return;
        error = null; success = null;
        try { apply(await uploadExportReference(fmt, file)); flash(`${fmt.toUpperCase()}-Vorlage hochgeladen.`); }
        catch (e) { error = e.message; }
    }

    async function removeRef(fmt) {
        error = null; success = null;
        try { apply(await deleteExportReference(fmt)); flash(`${fmt.toUpperCase()}-Vorlage entfernt.`); }
        catch (e) { error = e.message; }
    }

    const REFS = [
        { fmt: 'docx', label: 'Word (DOCX)', accept: '.docx' },
        { fmt: 'odt', label: 'OpenDocument (ODT)', accept: '.odt' },
    ];
</script>

<div class="max-w-2xl mx-auto py-8 px-4">
    <a
        href="/settings"
        class="flex items-center gap-1 mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2
               hover:text-light-tx dark:hover:text-dark-tx transition-colors"
    >
        <ArrowLeft class="w-4 h-4" /> Zurück
    </a>

    <div class="flex items-center gap-2 mb-2 text-light-tx dark:text-dark-tx">
        <FileText class="w-6 h-6" />
        <h1 class="text-2xl font-semibold">Export-Vorlagen</h1>
    </div>
    <p class="mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2">
        Schulweites Layout für exportierte Dokumente der Material-Werkstatt. Fehlt eine Vorlage,
        greift die eingebaute Standard-Optik.
    </p>

    <InfoBanner message="PDF-Exporte werden über CSS gestaltet; Word/ODT über ein hochgeladenes Referenzdokument (dessen Formatvorlagen Pandoc übernimmt). PDF- und Word-Layout lassen sich nicht exakt angleichen." />

    {#if error}<div class="mt-4"><ErrorBanner message={error} /></div>{/if}
    {#if success}<div class="mt-4"><SuccessBanner message={success} /></div>{/if}

    {#if loading}
        <div class="flex justify-center py-12 text-light-tx-2 dark:text-dark-tx-2">
            <Loader2 class="w-6 h-6 animate-spin" />
        </div>
    {:else}
        <!-- PDF-CSS -->
        <section class="mt-6">
            <h2 class="font-medium text-light-tx dark:text-dark-tx mb-1">PDF: eigenes CSS</h2>
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-2">
                Ergänzt/überschreibt die Standard-Vorlage (z. B. Schriftart, Farben, Kopf-/Fußzeile).
            </p>
            <textarea
                bind:value={css}
                spellcheck="false"
                placeholder="/* z. B. */&#10;body &#123; font-family: Georgia, serif; &#125;"
                class="w-full h-56 resize-y p-3 font-mono text-sm rounded-lg
                       bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                       border border-light-ui-3 dark:border-dark-ui-3 focus:outline-none
                       focus:border-primary dark:focus:border-primary-dark"
            ></textarea>
            <div class="mt-2">
                <button
                    type="button"
                    onclick={saveCss}
                    disabled={saving || !cssDirty}
                    class="inline-flex items-center gap-1 text-sm px-3 py-1.5 rounded-lg
                           bg-primary dark:bg-primary-dark text-white
                           hover:opacity-90 transition-opacity disabled:opacity-40"
                >
                    CSS speichern
                </button>
            </div>
        </section>

        <!-- Referenzdokumente -->
        <section class="mt-8">
            <h2 class="font-medium text-light-tx dark:text-dark-tx mb-1">Word/ODT: Referenzdokument</h2>
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-3">
                Ein Dokument im jeweiligen Format, dessen Formatvorlagen (Schriften, Überschriften,
                Ränder) übernommen werden.
            </p>
            <div class="space-y-2">
                {#each REFS as r}
                    {@const present = r.fmt === 'docx' ? hasDocx : hasOdt}
                    <div class="flex items-center gap-3 flex-wrap p-3 rounded-lg
                                bg-light-bg-2 dark:bg-dark-bg-2
                                border border-light-ui-3 dark:border-dark-ui-3">
                        <span class="font-medium text-light-tx dark:text-dark-tx w-40">{r.label}</span>
                        <span class="text-sm {present ? 'text-light-gr dark:text-dark-gr' : 'text-light-tx-3 dark:text-dark-tx-3'}">
                            {present ? 'hochgeladen' : 'Standard-Optik'}
                        </span>
                        <label class="ml-auto inline-flex items-center gap-1 text-sm px-2 py-1 rounded cursor-pointer
                                      text-light-tx-2 dark:text-dark-tx-2
                                      hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors">
                            <Upload class="w-4 h-4" /> {present ? 'Ersetzen' : 'Hochladen'}
                            <input type="file" accept={r.accept} class="hidden" onchange={(e) => upload(r.fmt, e)} />
                        </label>
                        {#if present}
                            <button
                                type="button"
                                onclick={() => removeRef(r.fmt)}
                                aria-label="Entfernen"
                                class="inline-flex items-center p-1 rounded
                                       text-light-tx-3 dark:text-dark-tx-3
                                       hover:text-light-re dark:hover:text-dark-re
                                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                            >
                                <Trash2 class="w-4 h-4" />
                            </button>
                        {/if}
                    </div>
                {/each}
            </div>
        </section>
    {/if}
</div>
