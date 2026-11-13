<script>
    // Eine Ansicht für jedes Produkt (0.41, Schritt 8): Rahmen mit Titel, Art, Fach, Thema,
    // Herkunft und Frist; darunter je Art der Inhalt — Dokument: der Editor; Diagramm: ansehen
    // mit Zoom und Quelltext (bearbeiten kommt mit Päckchen L, F7); Bild: Bild und Prompt;
    // Datei: Verweis auf ihr Dokument. Bis 0.41 hatten nur Dokumente eine eigene Ansicht.
    import { goto } from '$app/navigation';
    import { page } from '$app/stores';
    import { ArrowLeft, Download, Copy, Check, Share2, Trash2, Loader2, Files, Pencil } from 'lucide-svelte';
    import { getProduktInfo, produktKopieren, deleteArtifact } from '$lib/api.js';
    import { subjects, subjectMap } from '$lib/stores/subjects.js';
    import { kindLabel, mimeExt, slugify, formatBytes } from '$lib/library.js';
    import { sanitizeSvg } from '$lib/serverRender.js';
    import { zitiername } from '$lib/provenance.js';
    import { BADGE } from '$lib/badges.js';
    import ErrorBanner from '$lib/components/ErrorBanner.svelte';
    import PageBody from '$lib/components/PageBody.svelte';
    import ProduktAngaben from '$lib/components/ProduktAngaben.svelte';
    import DokumentEditor from '$lib/components/DokumentEditor.svelte';
    import ZoomFlaeche from '$lib/components/ZoomFlaeche.svelte';
    import UebernahmeDialog from '$lib/components/UebernahmeDialog.svelte';

    const DIAGRAMM_ARTEN = new Set(['circuit', 'plot', 'smiles', 'mermaid']);

    let id = $derived($page.params.id);
    let info = $state(null);
    let svg = $state(null);
    let loading = $state(true);
    let error = $state(null);
    let angabenOffen = $state(false);
    let loeschenFragen = $state(false);
    let beschaeftigt = $state(false);
    let kopiert = $state(false);
    let uebernahmeOffen = $state(false);

    const faecherAlle = $derived(
        [...($subjects ?? [])].sort((a, b) => a.name.localeCompare(b.name, 'de')),
    );

    async function laden() {
        loading = true;
        error = null;
        try {
            info = await getProduktInfo(id);
            svg = null;
            if (DIAGRAMM_ARTEN.has(info.kind)) {
                const res = await fetch(`/api/artifacts/${id}`, { credentials: 'include' });
                svg = sanitizeSvg(await res.text());
            }
        } catch (err) {
            error = err?.status === 404 ? 'Dieses Produkt gibt es nicht (mehr).' : (err.message ?? 'Produkt konnte nicht geladen werden.');
        } finally {
            loading = false;
        }
    }

    $effect(() => {
        id;
        laden();
    });

    function datum(iso) {
        return iso ? new Date(iso).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' }) : '';
    }

    async function quelleKopieren() {
        await navigator.clipboard.writeText(info.source ?? '');
        kopiert = true;
        setTimeout(() => (kopiert = false), 1500);
    }

    async function alsKopie() {
        beschaeftigt = true;
        error = null;
        try {
            const kopie = await produktKopieren(id);
            await goto(`/workshop/${kopie.id}`);
        } catch (err) {
            error = err.message ?? 'Kopie konnte nicht angelegt werden.';
        } finally {
            beschaeftigt = false;
        }
    }

    async function loeschen() {
        beschaeftigt = true;
        try {
            await deleteArtifact(id);
            await goto('/workshop');
        } catch (err) {
            error = err.message ?? 'Löschen fehlgeschlagen.';
            beschaeftigt = false;
        }
    }

    const knopf = 'inline-flex items-center gap-1 text-sm px-2.5 py-1 rounded-lg text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors disabled:opacity-50';
</script>

<PageBody breit>
    <div class="max-w-6xl mx-auto flex flex-col gap-4">
        <a href="/workshop" class="self-start inline-flex items-center gap-1 text-sm text-light-bl dark:text-dark-bl hover:underline">
            <ArrowLeft class="w-4 h-4" /> Werkstatt
        </a>

        {#if error}<ErrorBanner message={error} />{/if}

        {#if loading && !info}
            <div class="flex justify-center py-12 text-light-tx-2 dark:text-dark-tx-2">
                <Loader2 class="w-6 h-6 animate-spin" />
            </div>
        {:else if info}
            <!-- Rahmen -->
            <header class="flex flex-col gap-2">
                {#if angabenOffen}
                    <div class="max-w-md">
                        <ProduktAngaben
                            item={info}
                            faecher={faecherAlle}
                            onGespeichert={() => { angabenOffen = false; laden(); }}
                            onAbbrechen={() => (angabenOffen = false)}
                        />
                    </div>
                {:else}
                    <div class="flex items-start gap-2">
                        <h1 class="flex-1 text-2xl font-semibold text-light-tx dark:text-dark-tx break-words">{info.title}</h1>
                        <button type="button" onclick={() => (angabenOffen = true)} class={knopf}
                                title="Titel, Fach und Thema bearbeiten">
                            <Pencil class="w-4 h-4" /> Angaben
                        </button>
                    </div>
                    <p class="flex flex-wrap items-center gap-1.5 text-sm">
                        <span class={BADGE}>{kindLabel(info.kind)}</span>
                        {#if info.subject_id != null}<span class={BADGE}>{$subjectMap[info.subject_id]?.name ?? 'Fach'}</span>{/if}
                        {#if info.topic}<span class={BADGE}>{info.topic}</span>{/if}
                    </p>
                {/if}
                <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                    <!-- Herkunft: Assistent und Modell bleiben am Produkt, auch wenn der Chat weg ist (F12). -->
                    {#if info.assistant_name || zitiername(info.provider_model)}
                        Aus einem Chat
                        {#if info.assistant_name}mit „{info.assistant_name}“{/if}
                        {#if zitiername(info.provider_model)}· Modell <span class="font-mono">{zitiername(info.provider_model)}</span>{/if}
                        {#if info.chat_vorhanden}
                            · <a href="/chat?id={info.origin_conversation_id}" class="text-light-bl dark:text-dark-bl hover:underline">zum Chat</a>
                        {/if}
                        ·
                    {/if}
                    Angelegt {datum(info.created_at)} · bearbeitet {datum(info.updated_at ?? info.created_at)} ·
                    gültig bis {datum(info.expires_at)} · {formatBytes(info.byte_size)}
                </p>
                {#if info.baustein_id}
                    <a href="/knowledge/{info.baustein_id}" class="self-start text-xs text-light-bl dark:text-dark-bl hover:underline">
                        als Baustein übernommen: „{info.baustein_titel}“ →
                    </a>
                {/if}

                <!-- Aktionen -->
                <div class="flex flex-wrap items-center gap-1 border-y border-light-ui-3 dark:border-dark-ui-3 py-1">
                    <a href="/api/artifacts/{info.id}" download="{slugify(info.title)}.{mimeExt(info.mime_type)}" class={knopf}>
                        <Download class="w-4 h-4" /> Herunterladen
                    </a>
                    {#if info.uebernehmbar}
                        <button type="button" onclick={() => (uebernahmeOffen = true)} class={knopf}>
                            <Share2 class="w-4 h-4" /> {info.baustein_id ? 'Baustein aktualisieren' : 'Als Baustein übernehmen'}
                        </button>
                    {/if}
                    {#if info.kind === 'document'}
                        <button type="button" onclick={alsKopie} disabled={beschaeftigt} class={knopf}>
                            <Files class="w-4 h-4" /> Als Kopie speichern
                        </button>
                    {/if}
                    <span class="ml-auto">
                        {#if loeschenFragen}
                            <button type="button" onclick={loeschen} disabled={beschaeftigt}
                                    class="text-sm px-2.5 py-1 rounded-lg text-light-re dark:text-dark-re hover:bg-light-ui-2 dark:hover:bg-dark-ui-2">
                                {info.exporte?.length
                                    ? `Samt ${info.exporte.length} ${info.exporte.length === 1 ? 'Export' : 'Exporten'} löschen?`
                                    : 'Wirklich löschen?'}
                            </button>
                            <button type="button" onclick={() => (loeschenFragen = false)} class={knopf}>Abbrechen</button>
                        {:else}
                            <button type="button" onclick={() => (loeschenFragen = true)} class={knopf}>
                                <Trash2 class="w-4 h-4" /> Löschen
                            </button>
                        {/if}
                    </span>
                </div>
            </header>

            <!-- Inhalt je Art -->
            {#if info.kind === 'document'}
                <div class="h-[75vh] rounded-lg border border-light-ui-3 dark:border-dark-ui-3 overflow-hidden">
                    <DokumentEditor id={info.id} titel={info.title} onGespeichert={laden} />
                </div>
                {#if info.exporte?.length}
                    <section class="text-sm">
                        <h2 class="font-medium text-light-tx dark:text-dark-tx mb-1">Exporte</h2>
                        <ul class="space-y-1">
                            {#each info.exporte as ex (ex.id)}
                                <li class="flex items-center gap-2 text-light-tx-2 dark:text-dark-tx-2">
                                    <span class={BADGE}>{kindLabel(ex.kind)}</span>
                                    {datum(ex.created_at)} · {formatBytes(ex.byte_size)}
                                    <a href="/api/artifacts/{ex.id}" download="{slugify(ex.title)}.{mimeExt(ex.mime_type)}"
                                       class="text-light-bl dark:text-dark-bl hover:underline">herunterladen</a>
                                </li>
                            {/each}
                        </ul>
                    </section>
                {/if}
            {:else if DIAGRAMM_ARTEN.has(info.kind)}
                {#if svg}
                    <ZoomFlaeche {svg} titel={info.title} />
                {/if}
                {#if info.source}
                    <section class="flex flex-col gap-1">
                        <div class="flex items-center gap-2">
                            <h2 class="text-sm font-medium text-light-tx dark:text-dark-tx">Quelltext</h2>
                            <button type="button" onclick={quelleKopieren} class={knopf}>
                                {#if kopiert}<Check class="w-4 h-4" /> Kopiert{:else}<Copy class="w-4 h-4" /> Kopieren{/if}
                            </button>
                        </div>
                        <pre class="text-xs p-3 rounded-lg overflow-x-auto bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx">{info.source}</pre>
                        <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                            Bearbeiten lässt sich ein Diagramm hier noch nicht — frag im Chat nach einer neuen Fassung.
                        </p>
                    </section>
                {/if}
            {:else if info.kind === 'image'}
                <img src="/api/artifacts/{info.id}" alt={info.title}
                     class="max-w-full max-h-[75vh] object-contain self-start rounded-lg border border-light-ui-3 dark:border-dark-ui-3" />
                {#if info.source}
                    <section class="text-sm">
                        <h2 class="font-medium text-light-tx dark:text-dark-tx">Bildbeschreibung</h2>
                        <p class="text-light-tx-2 dark:text-dark-tx-2 whitespace-pre-wrap">{info.source}</p>
                        <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mt-1">Vom Sprachmodell formuliert, nicht von dir.</p>
                    </section>
                {/if}
            {:else}
                <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                    {#if info.derived_from}
                        Export des Dokuments
                        <a href="/workshop/{info.derived_from}" class="text-light-bl dark:text-dark-bl hover:underline">„{info.derived_from_title}“</a>.
                    {:else}
                        Eine Datei — herunterladen und im passenden Programm öffnen.
                    {/if}
                </p>
            {/if}
        {/if}
    </div>
</PageBody>

{#if uebernahmeOffen && info}
    <UebernahmeDialog artefakt={info} onclose={() => (uebernahmeOffen = false)} ongespeichert={laden} />
{/if}
