<script>
    import { AlertCircle, BookOpen, Check, FileText, Image, Info, Copy, Pencil, ThumbsUp, ThumbsDown } from 'lucide-svelte';
    import { goto } from '$app/navigation';
    import { renderInlineMath, renderMarkdown } from '$lib/markdown.js';
    import { renderDiagrams } from '$lib/diagrams.js';
    import { diagrammQuelleKopieren, diagrammSvgHerunterladen, formelKnopf } from '$lib/kopieren.js';
    import { mount, unmount } from 'svelte';
    import ProduktLeiste from '$lib/components/ProduktLeiste.svelte';
    import { textDateiname } from '$lib/produktleiste.js';
    import { renderServerBlocks } from '$lib/serverRender.js';
    import { saveImageToLibrary, saveDiagramToLibrary, getPlotGgbBlob, createDocument, variiereBild, rateMessage } from '$lib/api.js';
    import { DAUMEN, alsAnzeige, naechsteBewertung, zeigeDaumen } from '$lib/bewertung.js';
    import { user } from '$lib/stores/user.js';
    import { zitiername, zitatText, zeitpunkt } from '$lib/provenance.js';
    import { branding } from '$lib/branding.js';
    import { deriveDocTitle } from '$lib/workshop.js';
    import { triggerDownload } from '$lib/download.js';
    import HelpResourcesBanner from '$lib/components/HelpResourcesBanner.svelte';
    import UebernahmeDialog from '$lib/components/UebernahmeDialog.svelte';

    import { istLeereAntwort, leereAntwortText } from '$lib/chat_errors.js';
    import { kostenAnzeige, kostenErklaerung } from '$lib/budget_text.js';
    import { nurTextHinweis } from '$lib/workshop.js';
    import WarningBanner from './WarningBanner.svelte';
    import KontextListe from './KontextListe.svelte';
    import { kontextEintraege } from '$lib/kontext_anzeige.js';
    import { zoomAnhaengen } from '$lib/zoom.js';
    // `userPrompt`: die vorangegangene Nutzernachricht — sie gehört als eigene
    // Eingabe in die Quellenangabe, steht aber in einer anderen Nachricht.
    let {
        message,
        isStreaming = false,
        costEur = null,
        userPrompt = null,
        // Zeigt diese Nutzer:in Kosten je Nachricht? `costEur === null` allein
        // taugt als Antwort nicht: Es heißt sowohl „abgeschaltet" als auch „noch
        // nicht ermittelt" — und im zweiten Fall gehört ein Hinweis hin, im ersten
        // nicht.
        kostenSichtbar = true,
        // `aus` | `kurz` | `ausfuehrlich` (Profileinstellung `kontext_anzeige`). Vorgabe
        // `aus`: Außerhalb des Chats (Testchat im Editor, Einsicht) gibt es keine Zeile.
        kontextStufe = 'aus',
        // Wohin „Zurück“ aus einem Baustein der Kontextliste führt (`/chat?id=…`).
        kontextZurueck = null,
        // Nur an der letzten eigenen Nachricht gesetzt (0.19): öffnet das Bearbeiten.
        onBearbeiten = null,
        // Antwort eines Schüler-Assistenten: Fettdruck erscheint als einfacher Text (0.26, B1).
        ohneFett = false,
        // Daumen an der Antwort (0.31)? Nur der Chat setzt das — Editor-Testchat und
        // Krisen-Einsicht bleiben bei der Vorgabe. Ob der Chat bewertbar ist, sagt der Server.
        bewertbar = false,
    } = $props();

    // ── Antwortbewertung (0.31, ADR-020) ────────────────────────────────────
    // Sofort anzeigen, beim Fehlschlag zurücknehmen: Ein Daumen, der eine Sekunde auf den
    // Server wartet, fühlt sich kaputt an.
    //
    // ⚠️ **Je Nachrichten-ID gemerkt, nicht als einfacher Zustand.** Der Chat legt die
    // Blasen ohne Schlüssel an und verwendet sie je Position weiter; ein `$state` mit dem
    // Anfangswert behielte beim Wechsel in einen anderen Chat den Daumen der vorigen Antwort.
    let geklickt = $state({});
    // Kennung der Antwort, deren Bewertung zuletzt scheiterte — aus demselben Grund je ID.
    let fehlerBei = $state(null);
    const bewertung = $derived(
        message.id && message.id in geklickt ? geklickt[message.id] : alsAnzeige(message.rating),
    );
    const daumen = $derived(zeigeDaumen({ bewertbar, message, isStreaming }));

    async function bewerten(wert) {
        const id = message.id;
        const vorher = bewertung;
        const ziel = naechsteBewertung(vorher, wert);
        geklickt = { ...geklickt, [id]: alsAnzeige(ziel) };
        fehlerBei = null;
        try {
            const antwort = await rateMessage(id, ziel);
            geklickt = { ...geklickt, [id]: alsAnzeige(antwort.rating) };
        } catch {
            geklickt = { ...geklickt, [id]: vorher };
            fehlerBei = id;
        }
    }

    // Beide Übernahmen legen ein Markdown-Dokument an und nehmen nur `content` mit.
    // Ist ein Bild dabei, bliebe es wortlos zurück — der Hinweis sagt es.
    const textHinweis = $derived(nurTextHinweis(message));

    // Was unter der Blase steht — Betrag, Untergrenze oder Hinweis.
    // Während des Streams gar nichts: Da steht noch nicht einmal die Antwort.
    const kosten = $derived(
        !kostenSichtbar || isStreaming
            ? null
            : kostenAnzeige(costEur, message.cost_status),
    );

    let renderedContent = $derived(
        message.role === 'assistant' ? renderMarkdown(message.content, { ohneFett }) : ''
    );

    // Die verwendete Bildart interessiert Lehrkräfte (greift das Routing sinnvoll?);
    // für Schüler:innen wäre sie nur Rauschen — sie wählen ohnehin nichts aus.
    let zeigeBildart = $derived(!!$user?.roles?.includes('teacher'));

    // „Als Baustein speichern“ nur für Lehrkräfte (0.41, Schritt 9): Schüler-Arbeit bleibt
    // ein Produkt in der Werkstatt. In der Vorschau sind die Rollen simuliert — passt.
    let darfUebernehmen = $derived(
        !!($user?.roles?.includes('teacher') || $user?.roles?.includes('admin')),
    );

    // ── Herkunft (Modell-Transparenz) ────────────────────────────────────────
    // Standardmäßig verborgen, per Klick einblendbar: Zum Arbeiten braucht die Angabe
    // niemand, für eine Quellenangabe in GFS oder Facharbeit ist sie nötig — und dann
    // von jedem erreichbar, nicht nur von Lehrkräften.
    let herkunftOffen = $state(false);
    let antwortModell = $derived(zitiername(message.provider_model));
    // Auch Bilder haben eine eigene Herkunft; sie kann von der der Antwort abweichen.
    let bildHerkuenfte = $derived(
        (message.images ?? [])
            .map((b) => ({ ...b, modell: zitiername(b.provider_model) }))
            .filter((b) => b.modell),
    );
    let hatHerkunftsangaben = $derived(!!antwortModell || bildHerkuenfte.length > 0);
    let erzeugtAm = $derived(zeitpunkt(message.created_at));

    // ── Kontext (0.14): die Bausteine, die beim Antworten vorlagen ───────────
    // Eingeklappt wie die Herkunft — ein Nachweis, keine Aufforderung (ADR-017).
    let kontextOffen = $state(false);
    let kontext = $derived(kontextEintraege(message, kontextStufe, isStreaming, kontextZurueck));

    let zitat = $derived(
        zitatText({
            werkzeug: branding.name,
            modell: antwortModell,
            zeitpunkt: erzeugtAm,
            eingabe: userPrompt,
            bilder: bildHerkuenfte.map((b) => ({ modell: b.modell, prompt: b.prompt })),
        }),
    );
    let zitatKopiert = $state(false);
    async function zitatKopieren() {
        try {
            await navigator.clipboard.writeText(zitat);
            zitatKopiert = true;
            setTimeout(() => (zitatKopiert = false), 2200);
        } catch {
            zitatKopiert = false;
        }
    }

    // „Variieren": derselbe Prompt, dieselbe Bildart, neuer Wurf. Läuft ohne Chat-Modell —
    // es geht nicht darum, den Wunsch neu zu formulieren.
    let variiereStatus = $state({});   // image_id → 'laeuft' | Fehlertext
    async function variiere(imageId) {
        if (variiereStatus[imageId] === 'laeuft') return;
        variiereStatus = { ...variiereStatus, [imageId]: 'laeuft' };
        try {
            const neu = await variiereBild(imageId);
            message.images = [...(message.images ?? []), neu];
            variiereStatus = { ...variiereStatus, [imageId]: null };
        } catch (e) {
            variiereStatus = {
                ...variiereStatus,
                [imageId]: e?.message || 'Variieren fehlgeschlagen.',
            };
        }
    }

    // Generierte Bilder (Phase 16): fehlgeschlagene Ladevorgänge je image_id merken.
    let failedImages = $state(new Set());
    function onImageError(id) {
        failedImages = new Set(failedImages).add(id);
    }

    // Gespeicherte Bilder (Phase 18): Nach dem Speichern bleibt der Link „In der Werkstatt ✓“
    // unter dem Bild stehen (0.40, F11) — die Leiste darüber erscheint nur beim Überfahren.
    let imageSaveState = $state({});
    /** Link „In der Werkstatt ✓“ unter einem gespeicherten Bild oder Diagramm (0.40, F11). */
    const WERKSTATT_LINK_KLASSE = 'mt-1 inline-block text-xs text-light-bl dark:text-dark-bl hover:underline';
    // Server-/Client-gerenderte Diagramme (circuit/plot/mermaid) bekommen einen
    // „In der Werkstatt speichern"-Knopf, sobald sie erfolgreich zu SVG gerendert wurden.
    // Die Rohquelle liegt in `data-source` (von serverRender.js/diagrams.js gestasht).
    const DIAGRAM_KIND = {
        'circuit-block': 'circuit', 'plot-block': 'plot', 'smiles-block': 'smiles', 'mermaid-block': 'mermaid',
    };
    function libraryButtons(node) {
        function attach() {
            node.querySelectorAll('.circuit-block, .plot-block, .smiles-block, .mermaid-block').forEach((block) => {
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
                    // focus-within: Wer mit der Tastatur kommt, sieht die Leiste auch.
                    'opacity-0 group-hover:opacity-100 group-focus-within:opacity-100',
                    'transition-opacity',
                ].join(' ');

                // Dieselbe Leiste wie an Bild und Text (0.41, Schritt 7). Svelte-Komponente in
                // gerendertem HTML: `mount`, beim Abbau `unmount` (siehe `destroy`).
                const quelle = () => block.dataset.source ?? '';
                const extras = [{
                    id: 'code', label: 'Code kopieren', titel: 'Quelltext des Diagramms kopieren',
                    aktion: () => diagrammQuelleKopieren(block),
                }];
                if (kind === 'plot') {
                    // Funktionsgraphen zusätzlich als GeoGebra-Datei (.ggb).
                    extras.push({
                        id: 'ggb', label: 'GeoGebra', titel: 'Als GeoGebra-Datei (.ggb) herunterladen',
                        aktion: async () => {
                            triggerDownload(await getPlotGgbBlob(quelle()), 'funktionsgraph.ggb');
                            return '✓ .ggb';
                        },
                    });
                }
                eingehaengt.push(mount(ProduktLeiste, {
                    target: bar,
                    props: {
                        variante: 'overlay',
                        speichern: () => saveDiagramToLibrary(kind, quelle(), { messageId: message.id ?? null }),
                        herunterladen: () => diagrammSvgHerunterladen(block, kind),
                        extras,
                        // Bleibender Link unter dem Diagramm — die Leiste erscheint nur beim Überfahren.
                        onGespeichert: () => {
                            if (block.querySelector(':scope > a[data-werkstatt-link]')) return;
                            const link = document.createElement('a');
                            link.href = '/workshop';
                            link.dataset.werkstattLink = '';
                            link.className = WERKSTATT_LINK_KLASSE;
                            link.textContent = 'In der Werkstatt ✓';
                            block.appendChild(link);
                        },
                    },
                }));

                block.appendChild(bar);

                // Zoom nur, wenn das Diagramm verkleinert dargestellt wird (0.41, Schritt 8).
                // Die Knöpfe unten rechts — oben rechts liegt die Produktleiste.
                block.style.setProperty('--pele-zoom-top', 'auto');
                block.style.setProperty('--pele-zoom-bottom', '8px');
                zoomAnhaengen(block)
                    .then((z) => { if (abgebaut) z.destroy(); else zooms.push(z); })
                    .catch(() => {}); // ohne Zoom bleibt das Diagramm, wie es war
            });
        }

        const eingehaengt = [];
        const zooms = [];
        let abgebaut = false;
        attach();
        const observer = new MutationObserver(attach);
        observer.observe(node, { childList: true, subtree: true });
        return {
            destroy() {
                abgebaut = true;
                observer.disconnect();
                eingehaengt.forEach((k) => unmount(k));
                zooms.forEach((z) => z.destroy());
            },
        };
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

            // Abgesetzte Formeln (0.12, AP6c) — Inline-Formeln kopiert copy-tex beim Markieren.
            node.querySelectorAll('.katex-display:not([data-copy-attached])').forEach(formel => {
                if (formelKnopf(formel)) formel.setAttribute('data-copy-attached', '');
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

    // „Als Dokument bearbeiten" (Phase 19; Knopftext seit 0.12, F5): den Antworttext als
    // Markdown-Dokument ablegen und in die Werkstatt springen. Der Knopf nennt die
    // Tätigkeit, „Werkstatt" bleibt der Name der Ansicht.
    async function textAlsDokument() {
        return createDocument(deriveDocTitle(message.content), message.content ?? '', {
            messageId: message.id ?? null,
        });
    }

    // Speichern: Das Dokument liegt danach in der Werkstatt, der Chat bleibt offen (0.41).
    // `createDocument` ist über die Nachricht idempotent — dreimal klicken, ein Dokument.
    async function textSpeichern() {
        return textAlsDokument();
    }

    async function openInWorkshop() {
        const doc = await textAlsDokument();
        await goto(`/workshop/${doc.id}`);
    }

    async function textHerunterladen() {
        const blob = new Blob([message.content ?? ''], { type: 'text/markdown;charset=utf-8' });
        triggerDownload(blob, textDateiname(deriveDocTitle(message.content)));
        return '✓ .md';
    }

    // „Als Baustein speichern" (AP8): derselbe Redaktionsakt wie in der Bibliothek,
    // nur im Moment der Antwort. Der Weg führt über die Bibliothek, weil ein Baustein
    // seine Herkunft trägt (`metadata.source_artifact_id`) — es muss also erst ein
    // Artefakt geben. Sichtbar ist davon nur ein Knopf und derselbe Dialog.
    //
    // Das angelegte Dokument wird gemerkt — das spart beim zweiten Klick eine Anfrage.
    // Auf die Merknotiz kommt es aber nicht mehr an: `createDocument` ist seit dem
    // 18.09.2026 über `message:<id>` idempotent, ein zweiter Klick liefert dasselbe
    // Dokument. Vorher legte er ein zweites an — und damit einen Zweitknoten statt
    // einer neuen Fassung, auch schon nach einem simplen Neuladen der Seite.
    let bausteinArtefakt = $state(null);
    let bausteinDialogOffen = $state(false);

    async function alsBausteinSpeichern() {
        if (!bausteinArtefakt) bausteinArtefakt = await textAlsDokument();
        bausteinDialogOffen = true;
    }
</script>

{#if message.role === 'user'}
    <div class="flex justify-end">
        <div class="bg-primary dark:bg-primary-dark text-white rounded-xl rounded-br-none px-4 py-2 max-w-[80%]">
            {#if message.content}
                <!-- Nur Formeln gerendert (0.38), der übrige Text bleibt Text: renderInlineMath escapt ihn -->
                <!-- eslint-disable-next-line svelte/no-at-html-tags -->
                <p class="whitespace-pre-wrap">{@html renderInlineMath(message.content)}</p>
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
    {#if onBearbeiten}
        <div class="flex justify-end -mt-2">
            <button
                onclick={onBearbeiten}
                class="inline-flex items-center gap-1 text-xs text-light-tx-2 dark:text-dark-tx-2
                       hover:text-light-bl dark:hover:text-dark-bl px-1 py-0.5"
                title="Nachricht bearbeiten und neu senden — die bisherige Antwort wird ersetzt"
            >
                <Pencil class="w-3 h-3" /> Bearbeiten
            </button>
        </div>
    {/if}
    <!-- Das Hilfe-Banner (ADR-008) folgt der Nachricht, die es ausgelöst hat:
         **unter** der eigenen Eingabe, **über** der Modellantwort. Vorher hing es
         an der Antwort und war bei langem Text erst nach dem Scrollen zu sehen. -->
    {#if message.crisis}
        <div class="w-full">
            <HelpResourcesBanner topic={message.crisis} />
        </div>
    {/if}

{:else if message.role === 'assistant'}
    <div class="flex flex-col items-start">
        {#if message.abgebrochen && !message.content && !message.images?.length && !isStreaming}
            <!-- Gestoppt, bevor ein Wort kam: kein „leere Antwort"-Fehler, sondern das. -->
            <p class="text-sm italic text-light-tx-2 dark:text-dark-tx-2">Abgebrochen, bevor eine Antwort kam.</p>
        {:else if istLeereAntwort(message, isStreaming)}
            <!-- Antwort ohne Inhalt: Bis 09/2026 rendert die Blase hier gar nichts —
                 die Frage verschwand scheinbar spurlos, das Budget war gebucht.
                 Die Regel dazu (inklusive „Bilder sind eine Antwort") steht in
                 `$lib/chat_errors.js`, wo sie sich prüfen lässt. -->
            <div class="max-w-[80%]">
                <WarningBanner message={leereAntwortText(costEur)} />
            </div>
        {:else if message.content || isStreaming || message.images?.length}
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
            {:else if message.abgebrochen}
                <p class="text-xs italic text-light-tx-2 dark:text-dark-tx-2 mt-1">— abgebrochen</p>
            {/if}
            <!-- Bild und Aktionen gehören **in** die Blase: Sie sind Teil
                 derselben Antwort. Außerhalb wirkten sie wie eigene Beiträge,
                 und die Kostenzeile darunter bezog sich sichtbar auf etwas
                 anderes als das, was darüber stand. -->
            {#if message.images?.length}
                <div class="flex flex-col gap-2 mt-3">
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
                                <div class="absolute top-1.5 right-1.5
                                            opacity-0 group-hover:opacity-100 group-focus-within:opacity-100
                                            transition-opacity">
                                    <ProduktLeiste
                                        variante="overlay"
                                        speichern={() => saveImageToLibrary(img.image_id)}
                                        herunterladen={{ href: `/api/images/${img.image_id}`, dateiname: `bild-${img.image_id}.png` }}
                                        extras={img.bildart ? [{
                                            id: 'neu', label: 'Neu erzeugen',
                                            titel: 'Noch einmal erzeugen — gleiche Beschreibung, neues Bild',
                                            aktion: () => variiere(img.image_id),
                                        }] : []}
                                        onGespeichert={() => (imageSaveState = { ...imageSaveState, [img.image_id]: 'saved' })}
                                    />
                                </div>
                                {#if variiereStatus[img.image_id] === 'laeuft'}
                                    <p class="mt-0.5 text-xs text-light-tx-2 dark:text-dark-tx-2">Wird neu erzeugt…</p>
                                {/if}
                                {#if imageSaveState[img.image_id] === 'saved' || imageSaveState[img.image_id] === 'exists'}
                                    <a href="/workshop" class="block {WERKSTATT_LINK_KLASSE}">In der Werkstatt ✓</a>
                                {/if}
                                {#if variiereStatus[img.image_id] && variiereStatus[img.image_id] !== 'laeuft'}
                                    <p class="mt-0.5 text-xs text-light-re dark:text-dark-re">
                                        {variiereStatus[img.image_id]}
                                    </p>
                                {/if}
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
            {#if message.content && !isStreaming}
                <div class="mt-3">
                    <ProduktLeiste
                        variante="zeile"
                        speichern={textSpeichern}
                        bearbeiten={openInWorkshop}
                        herunterladen={textHerunterladen}
                        alsBaustein={darfUebernehmen ? alsBausteinSpeichern : null}
                        hinweis={textHinweis}
                    />
                </div>
            {/if}
            {#if kosten !== null || (hatHerkunftsangaben && !isStreaming) || kontext || daumen}
                <div class="flex items-center gap-3 text-xs text-light-tx-2 dark:text-dark-tx-2
                            mt-2 pt-1 border-t border-light-ui-3 dark:border-dark-ui-3">
                    {#if kosten !== null}
                        <!-- „Kosten werden ermittelt" statt Schweigen: Der Betrag
                             kommt seit 09/2026 im Hintergrund nach, und eine leere
                             Zeile wäre von „hat nichts gekostet" nicht zu
                             unterscheiden. -->
                        <span
                            class={kosten.unsicher ? 'italic' : ''}
                            title={kostenErklaerung(message.cost_status) ?? undefined}
                        >{kosten.text}</span>
                    {/if}
                    {#if hatHerkunftsangaben && !isStreaming}
                        <button
                            type="button"
                            onclick={() => (herkunftOffen = !herkunftOffen)}
                            aria-expanded={herkunftOffen}
                            title="Womit wurde diese Antwort erzeugt?"
                            class="inline-flex items-center gap-1 hover:text-light-tx dark:hover:text-dark-tx"
                        >
                            <Info class="w-3.5 h-3.5" />
                            Herkunft
                        </button>
                    {/if}
                    {#if kontext}
                        <button
                            type="button"
                            onclick={() => (kontextOffen = !kontextOffen)}
                            aria-expanded={kontextOffen}
                            title="Welche Bausteine lagen beim Antworten vor?"
                            class="inline-flex items-center gap-1 hover:text-light-tx dark:hover:text-dark-tx"
                        >
                            <BookOpen class="w-3.5 h-3.5" />
                            Kontext ({kontext.length})
                        </button>
                    {/if}
                    {#if daumen}
                        <span class="ml-auto inline-flex items-center gap-1">
                            {#if fehlerBei === message.id}
                                <span class="text-light-re dark:text-dark-re">Bewertung nicht gespeichert</span>
                            {/if}
                            {#each DAUMEN as d (d.wert)}
                                <button
                                    type="button"
                                    onclick={() => bewerten(d.wert)}
                                    aria-label={d.label}
                                    aria-pressed={bewertung === d.wert}
                                    title={d.label}
                                    class="p-1 rounded hover:text-light-tx dark:hover:text-dark-tx
                                           hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                                           {bewertung === d.wert ? 'text-light-tx dark:text-dark-tx' : ''}"
                                >
                                    {#if d.wert === 1}
                                        <ThumbsUp class="w-3.5 h-3.5 {bewertung === 1 ? 'fill-current' : ''}" />
                                    {:else}
                                        <ThumbsDown class="w-3.5 h-3.5 {bewertung === -1 ? 'fill-current' : ''}" />
                                    {/if}
                                </button>
                            {/each}
                        </span>
                    {/if}
                </div>
                {#if herkunftOffen}
                    <div class="mt-1 text-xs text-light-tx-2 dark:text-dark-tx-2 space-y-0.5">
                        {#if antwortModell}
                            <p>Text: <span class="font-mono">{antwortModell}</span></p>
                        {/if}
                        {#each bildHerkuenfte as bild (bild.image_id)}
                            <p>
                                Bild: <span class="font-mono">{bild.modell}</span>
                                {#if zeigeBildart && bild.bildart}
                                    <span class="text-light-tx-3 dark:text-dark-tx-3">
                                        (Bildart: {bild.bildart})
                                    </span>
                                {/if}
                            </p>
                        {/each}
                        {#if erzeugtAm}
                            <p>Erzeugt am {erzeugtAm}</p>
                        {/if}
                        <button
                            type="button"
                            onclick={zitatKopieren}
                            class="mt-1 inline-flex items-center gap-1 px-1.5 py-0.5 rounded
                                   bg-light-ui-2 dark:bg-dark-ui-2
                                   hover:bg-light-ui-3 dark:hover:bg-dark-ui-3"
                        >
                            {#if zitatKopiert}
                                <Check class="w-3.5 h-3.5" /> Kopiert
                            {:else}
                                <Copy class="w-3.5 h-3.5" /> Angaben zum Zitieren kopieren
                            {/if}
                        </button>
                    </div>
                {/if}
                {#if kontext && kontextOffen}
                    <KontextListe eintraege={kontext} />
                {/if}
            {/if}
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

{#if bausteinDialogOffen && bausteinArtefakt}
    <UebernahmeDialog
        artefakt={bausteinArtefakt}
        onclose={() => (bausteinDialogOffen = false)}
    />
{/if}
