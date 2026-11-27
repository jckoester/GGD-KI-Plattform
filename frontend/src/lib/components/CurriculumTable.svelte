<script>
    import { bausteinPfad } from "$lib/rueckweg.js";
    /**
     * Curriculum-Tabelle für Read-only und Edit-Darstellung
     *
     * Props:
     * - curriculum: CurriculumRead-Objekt vom Backend
     * - editMode: boolean (Default: false) - Aktiviert Bearbeitungsmodus
     * - onchange: Callback bei Änderungen im Edit-Mode
     */
    import HinweisChip from "./HinweisChip.svelte";
    import IKSelector from "./IKSelector.svelte";
    import PKSelector from "./PKSelector.svelte";
    import HinweisEditor from "./HinweisEditor.svelte";
    import { parseHinweise } from "$lib/hinweise.js";
    import { kapitelStd, lernsequenzStd } from "$lib/curriculum.js";
    import { renderMarkdown } from "$lib/markdown.js";
    import { parseMaterial } from "$lib/material.js";
    import MaterialEditor from "./MaterialEditor.svelte";
    import NamenChips from "./NamenChips.svelte";
    import CurriculumAbdeckung from "./CurriculumAbdeckung.svelte";
    import { untrack } from "svelte";
    import { page } from "$app/stores";
    import { aufloesenCurriculumBegriffe, fehlendeBegriffeUrl, getQuerverweise } from "$lib/api.js";
    import Querverweise from "./Querverweise.svelte";
    import AbsprachenEditor from "./AbsprachenEditor.svelte";
    import AbsprachenAnzeige from "./AbsprachenAnzeige.svelte";
    import { getCurriculumAbsprachen } from "$lib/api.js";
    import { findeVonAussen, gegenabsprache, gegenabspracheHref, hatAbsprachen } from "$lib/absprachen.js";
    import { tick } from "svelte";
    import { fehlendeIds, kompetenzIdsImCurriculum, uebernehmen } from "$lib/querverweise.js";
    import { myFachschaften } from "$lib/stores/myGroups.js";
    import {
        aufloesungsMap,
        aufloesungVon,
        begriffeImCurriculum,
        fachmethodenImCurriculum,
        fehlendeListe,
        fehlendUeberschrift,
        kannAnlegen,
        ungeprueft,
    } from "$lib/curriculum_begriffe.js";
    import {
        Trash2,
        MoreVertical,
        Move,
        ChevronRight,
        FileDown,
        Plus,
    } from "@lucide/svelte";

    // Tooltip für als „veraltet" markierte Kompetenzen (nach BP-Migration ohne Zwilling).
    const VERALTET_HINT =
        "Diese Kompetenz ist im aktuellen Bildungsplan nicht mehr enthalten oder wurde inhaltlich geändert – bitte prüfen.";

    let {
        curriculum = null,
        editMode = false,
        subjectId = null,
        grade = null,
        bpVersion = null,
        onchange = () => {},
    } = $props();

    // ── Absprachen mit anderen Fächern (0.63, AY Teil 2) ─────────────────────
    // „Absprache anlegen“ an einer Fundstelle der Querverweise öffnet das Formular am Kapitel,
    // in dem die Kompetenz steht — vorbelegt mit Fach und Kapitel des anderen Fachs.
    let vorbelegungen = $state({});
    async function absprachVorbelegen(kapId, fundstelle, verweis) {
        vorbelegungen = { ...vorbelegungen, [kapId]: {
            fach_code: verweis.fach_code, curriculum_id: fundstelle.curriculum_id,
            kapitel_id: fundstelle.kapitel_id, kapitel_titel: fundstelle.kapitel,
        } };
        if (collapsedChapters.has(kapId)) toggleChapter(kapId);
        await tick();
        document.getElementById(`absprachen-${kapId}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
    // Absprachen beider Richtungen vom Backend (Ziele aufgelöst, von außen, an das Fach).
    let absprachenDaten = $state(null);
    let gegenErledigt = false;
    $effect(() => {
        const id = curriculum?.id;
        if (!id) return;
        let abgebrochen = false;
        getCurriculumAbsprachen(id)
            .then((d) => { if (!abgebrochen) absprachenDaten = d; })
            .catch(() => { if (!abgebrochen) absprachenDaten = null; });
        return () => { abgebrochen = true; };
    });
    // `?gegen=<Kennung>` aus der Lesesicht: Gegenabsprache am passenden Kapitel vorbelegen.
    $effect(() => {
        const gegen = $page.url.searchParams.get("gegen");
        if (!editMode || !gegen || !absprachenDaten || gegenErledigt) return;
        gegenErledigt = true;
        const treffer = findeVonAussen(absprachenDaten, gegen);
        if (treffer) gegenVorbelegen(treffer.kapId, treffer.absprache);
    });
    async function gegenVorbelegen(kapId, a) {
        vorbelegungen = { ...vorbelegungen, [kapId]: gegenabsprache(a) };
        if (collapsedChapters.has(kapId)) toggleChapter(kapId);
        await tick();
        document.getElementById(`absprachen-${kapId}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
    const absprachenVon = (kapId) => absprachenDaten?.kapitel?.[kapId] ?? { eigene: [], von_aussen: [] };

    function absprachenSetzen(kap, liste) {
        // Die Vorbelegung ist verbraucht — sonst öffnete ein neu aufgebauter Editor sie wieder.
        if (vorbelegungen[kap.id]) {
            const { [kap.id]: _, ...rest } = vorbelegungen;
            vorbelegungen = rest;
        }
        kap.metadata = { ...kap.metadata, absprachen: liste };
        curriculum.kapitel = [...curriculum.kapitel];
        onchange();
    }

    // ── Begriffe und Fachmethoden am Eintrag (0.44, AQ) ──────────────────────
    // Die Auflösung kommt mit dem Curriculum (`curriculum.begriffe`) und wird für neu
    // eingetragene Namen nachgereicht. Sie steht neben dem Baum, nicht in den Einträgen.
    const fachId = $derived(subjectId ?? curriculum?.subject_id ?? null);
    const darfAnlegen = $derived(kannAnlegen($myFachschaften, fachId));
    // Nach dem Anlegen zurück in die Leseansicht — im Editor öffnet der Link einen neuen Tab.
    const rueckweg = $derived(
        curriculum?.id ? `/knowledge/curriculum/${curriculum.id}` : $page.url.pathname,
    );
    let aufloesung = $state(new Map());
    $effect(() => {
        const liste = curriculum?.begriffe;
        untrack(() => {
            aufloesung = aufloesungsMap(liste, aufloesung);
        });
    });
    // Übersicht der fehlenden Begriffe (Schritt 4) — aus derselben Auflösung wie die Chips.
    const fehlListe = $derived(fehlendeListe(curriculum, aufloesung));

    /** Namen beim Server prüfen — nur ungeprüfte, mit `alle` auch schon geprüfte. */
    async function pruefeBegriffe(namen, alle = false) {
        const offen = alle ? namen : ungeprueft(namen, aufloesung);
        if (!offen.length || !curriculum?.id) return;
        try {
            const neu = await aufloesenCurriculumBegriffe(
                curriculum.id,
                offen.map((b) => ({ name: b.name, fassung: b.fassung ?? null })),
            );
            aufloesung = aufloesungsMap(neu, aufloesung);
        } catch {
            // Ohne Prüfung bleibt der Chip „ungeprüft“ — der Name ist trotzdem gespeichert.
        }
    }

    // Im Editor wird ein fehlender Begriff in einem neuen Tab angelegt. Zurück im Tab
    // prüfen wir, was noch nicht gefunden war.
    function beiRueckkehr() {
        if (!editMode || document.visibilityState !== "visible") return;
        const offen = begriffeImCurriculum(curriculum).filter(
            (b) => aufloesungVon(aufloesung, b)?.zustand !== "gefunden",
        );
        pruefeBegriffe(offen, true);
    }

    function setzeNamen(eintrag, feld, neu) {
        if (neu.length) eintrag[feld] = neu;
        else delete eintrag[feld];
        curriculum.kapitel = [...curriculum.kapitel];
        onchange();
        if (feld === "begriffe") pruefeBegriffe(neu);
    }

    // ── Querverweise in andere Fächer (AY Teil 1) ──────────────────────────────
    // Nachgeladen, nicht im Baum: Der Baum bleibt schlank, und in der Bearbeitung kommen
    // auch neu gewählte Kompetenzen dazu — nur die noch unbekannten werden gefragt.
    let querverweise = $state(new Map());
    let qvTimer = null;
    $effect(() => {
        const ids = kompetenzIdsImCurriculum(curriculum);
        untrack(() => {
            const fehlend = fehlendeIds(ids, querverweise);
            if (!fehlend.length) return;
            clearTimeout(qvTimer);
            qvTimer = setTimeout(async () => {
                try {
                    const antwort = await getQuerverweise(fehlend);
                    querverweise = uebernehmen(querverweise, fehlend, antwort);
                } catch {
                    // Ohne Querverweise bleibt die Tabelle, wie sie war.
                }
            }, editMode ? 400 : 0);
        });
    });
    const qvVon = (nodeId) => (nodeId && querverweise.get(nodeId)) || [];

    // Lokaler State für Edit-Mode
    let showContextMenu = $state(null); // { type: 'kapitel'|'ls'|'eintrag', id: string, x: number, y: number }
    let deleteConfirm = $state(null); // { type, id, title }
    let draggedItem = $state(null); // { type, id, chapterId, lsId }

    // Einklapp-Zustand der Kapitel (Set mit Kapitel-IDs)
    let collapsedChapters = $state(new Set());

    function toggleChapter(kapId) {
        const next = new Set(collapsedChapters);
        next.has(kapId) ? next.delete(kapId) : next.add(kapId);
        collapsedChapters = next;
    }

    /**
     * Normalisiert eintrag.ik auf Array<{node_id, nr, partiell}>.
     * Versteht altes String-Format ("3.1.1, 3.1.2 [partiell]") und neues Array-Format.
     */
    function normalizeIk(ikData) {
        if (!ikData) return [];
        // Neues Format: Array von Objekten
        if (Array.isArray(ikData)) {
            return ikData.map((ik) => {
                if (typeof ik === "object" && ik !== null) return ik;
                return { node_id: null, nr: String(ik), partiell: false };
            });
        }
        // Altes Format: String
        if (typeof ikData === "string") {
            const matches =
                ikData.match(/(?:IK\s+)?([\d.]+(?:\s*\[partiell\])?)/g) || [];
            return matches.map((m) => {
                const partiell = m.includes("[partiell]") || m.includes("[");
                const nr = m
                    .replace("IK", "")
                    .replace(/\[.*\]/g, "")
                    .trim();
                return { node_id: null, nr, partiell };
            });
        }
        return [];
    }

    /**
     * Normalisiert eintrag.pk auf Array<{node_id, pk_id}>.
     * Versteht altes String-Array-Format und neues Objekt-Array-Format.
     */
    function normalizePk(pkData) {
        if (!pkData) return [];
        if (Array.isArray(pkData)) {
            return pkData.map((pk) => {
                if (typeof pk === "object" && pk !== null) return pk;
                return { node_id: null, pk_id: String(pk) };
            });
        }
        if (typeof pkData === "string")
            return [{ node_id: null, pk_id: pkData }];
        return [];
    }

    /**
     * Füge ein neues Kapitel hinzu
     */
    function addKapitel() {
        if (!curriculum || !curriculum.kapitel) {
            curriculum.kapitel = [];
        }
        const newReihenfolge = curriculum.kapitel.length + 1;
        curriculum.kapitel.push({
            id: `temp_${Date.now()}_${newReihenfolge}`,
            title: "Neues Kapitel",
            metadata: {
                std: "",
                reihenfolge: newReihenfolge,
                einleitung: "",
                breadcrumb: "",
            },
            lernsequenzen: [],
        });
        onchange();
    }

    /**
     * Füge eine neue Lernsequenz zu einem Kapitel hinzu
     */
    function addLernsequenz(kapitelIndex) {
        if (
            !curriculum ||
            !curriculum.kapitel ||
            kapitelIndex >= curriculum.kapitel.length
        ) {
            return;
        }
        const kapitel = curriculum.kapitel[kapitelIndex];
        if (!kapitel.lernsequenzen) {
            kapitel.lernsequenzen = [];
        }
        const newReihenfolge = kapitel.lernsequenzen.length + 1;
        kapitel.lernsequenzen.push({
            id: `temp_${Date.now()}_ls_${newReihenfolge}`,
            title: "",
            metadata: {
                bp_titel: "",
                bp_leitidee: "",
                reihenfolge: newReihenfolge,
                std: 0,
                eintraege: [],
                ik_refs: [],
                pk_refs: [],
                leitperspektive_refs: [],
            },
        });
        curriculum.kapitel = [...curriculum.kapitel];
        onchange();
    }

    /**
     * Füge einen neuen Eintrag zu einer Lernsequenz hinzu
     */
    function addEintrag(kapitelIndex, lsIndex) {
        if (
            !curriculum ||
            !curriculum.kapitel ||
            kapitelIndex >= curriculum.kapitel.length
        ) {
            return;
        }
        const ls = curriculum.kapitel[kapitelIndex].lernsequenzen[lsIndex];
        if (!ls.metadata) ls.metadata = {};
        if (!ls.metadata.eintraege) ls.metadata.eintraege = [];

        ls.metadata.eintraege.push({
            ik: [],
            pk: [],
            konkretisierung: "",
            hinweise: "",
            material: "",
        });
        curriculum.kapitel = [...curriculum.kapitel];
        onchange();
    }

    /**
     * Lösche ein Kapitel, eine Lernsequenz oder einen Eintrag
     */
    function confirmDelete(type, id, title, chapterId = null, lsId = null) {
        deleteConfirm = { type, id, title, chapterId, lsId };
    }

    async function executeDelete() {
        if (!deleteConfirm || !curriculum) return;

        const { type, id, chapterId, lsId } = deleteConfirm;

        if (type === "kapitel") {
            curriculum.kapitel = curriculum.kapitel.filter((k) => k.id !== id);
        } else if (type === "lernsequenz" && chapterId) {
            const kapitel = curriculum.kapitel.find((k) => k.id === chapterId);
            if (kapitel) {
                kapitel.lernsequenzen = kapitel.lernsequenzen.filter(
                    (ls) => ls.id !== id,
                );
                curriculum.kapitel = [...curriculum.kapitel];
            }
        } else if (type === "eintrag" && chapterId && lsId) {
            const kapitel = curriculum.kapitel.find((k) => k.id === chapterId);
            if (kapitel) {
                const ls = kapitel.lernsequenzen.find((ls) => ls.id === lsId);
                if (ls && ls.metadata?.eintraege) {
                    ls.metadata.eintraege = ls.metadata.eintraege.filter(
                        (_, i) => i !== id,
                    );
                    curriculum.kapitel = [...curriculum.kapitel];
                }
            }
        }

        deleteConfirm = null;
        onchange();
    }

    /**
     * Zeige Kontextmenü
     */
    function showMenu(event, type, id, chapterId = null, lsId = null) {
        event.preventDefault();
        event.stopPropagation();
        showContextMenu = {
            type,
            id,
            chapterId,
            lsId,
            x: event.clientX,
            y: event.clientY,
        };
    }

    /**
     * Verstecke Kontextmenü
     */
    function hideMenu() {
        showContextMenu = null;
    }

    /**
     * Handle Drag Start
     */
    function handleDragStart(event, type, id, chapterId = null, lsId = null) {
        draggedItem = { type, id, chapterId, lsId };
        event.dataTransfer?.setData("text/plain", JSON.stringify(draggedItem));
    }

    /**
     * Handle Drag Over
     */
    function handleDragOver(event) {
        event.preventDefault();
    }

    /**
     * Handle Drop - verschiebe Elemente
     */
    function handleDrop(
        event,
        type,
        id,
        chapterId = null,
        lsId = null,
        dropPosition = "before",
    ) {
        event.preventDefault();
        if (!draggedItem) return;

        // Nicht auf sich selbst ziehen
        if (draggedItem.id === id && draggedItem.type === type) return;

        if (type === "kapitel" && draggedItem.type === "kapitel") {
            // Kapitel verschieben
            const fromIndex = curriculum.kapitel.findIndex(
                (k) => k.id === draggedItem.id,
            );
            const toIndex = curriculum.kapitel.findIndex((k) => k.id === id);
            if (fromIndex !== -1 && toIndex !== -1) {
                const [moved] = curriculum.kapitel.splice(fromIndex, 1);
                curriculum.kapitel.splice(
                    dropPosition === "before" ? toIndex : toIndex + 1,
                    0,
                    moved,
                );
                // Reihenfolge aktualisieren
                curriculum.kapitel.forEach((k, i) => {
                    if (k.metadata) k.metadata.reihenfolge = i + 1;
                });
                curriculum.kapitel = [...curriculum.kapitel];
                onchange();
            }
        } else if (
            type === "lernsequenz" &&
            draggedItem.type === "lernsequenz" &&
            chapterId
        ) {
            // Lernsequenz innerhalb eines Kapitels verschieben
            const kapitel = curriculum.kapitel.find((k) => k.id === chapterId);
            if (kapitel) {
                const fromIndex = kapitel.lernsequenzen.findIndex(
                    (ls) => ls.id === draggedItem.id,
                );
                const toIndex = kapitel.lernsequenzen.findIndex(
                    (ls) => ls.id === id,
                );
                if (fromIndex !== -1 && toIndex !== -1) {
                    const [moved] = kapitel.lernsequenzen.splice(fromIndex, 1);
                    kapitel.lernsequenzen.splice(
                        dropPosition === "before" ? toIndex : toIndex + 1,
                        0,
                        moved,
                    );
                    // Reihenfolge aktualisieren
                    kapitel.lernsequenzen.forEach((ls, i) => {
                        if (ls.metadata) ls.metadata.reihenfolge = i + 1;
                    });
                    curriculum.kapitel = [...curriculum.kapitel];
                    onchange();
                }
            }
        } else if (
            type === "eintrag" &&
            draggedItem.type === "eintrag" &&
            chapterId &&
            lsId
        ) {
            // Eintrag innerhalb einer Lernsequenz verschieben
            const kapitel = curriculum.kapitel.find((k) => k.id === chapterId);
            if (kapitel) {
                const ls = kapitel.lernsequenzen.find((ls) => ls.id === lsId);
                if (ls && ls.metadata?.eintraege) {
                    const fromIndex = ls.metadata.eintraege.findIndex(
                        (e) => e === draggedItem.id,
                    );
                    const toIndex = ls.metadata.eintraege.findIndex(
                        (e) => e === id,
                    );
                    if (fromIndex !== -1 && toIndex !== -1) {
                        const [moved] = ls.metadata.eintraege.splice(
                            fromIndex,
                            1,
                        );
                        ls.metadata.eintraege.splice(
                            dropPosition === "before" ? toIndex : toIndex + 1,
                            0,
                            moved,
                        );
                        curriculum.kapitel = [...curriculum.kapitel];
                        onchange();
                    }
                }
            }
        }

        draggedItem = null;
    }

    // Link zu einem Wissensknoten (Read-only-Ansicht von PK/IK)
    function nodeLink(nodeId) {
        return bausteinPfad(nodeId, $page.url);
    }

    // Volltext einer IK/PK aus den Refs der Lernsequenz (für title-Attribut)
    function refTitle(ls, nodeId, kind) {
        if (!nodeId) return null;
        const refs = kind === "ik" ? ls.ik_refs || [] : ls.pk_refs || [];
        return refs.find((r) => r.node_id === nodeId)?.title ?? null;
    }

    // Reichert normalisierte IK/PK-Einträge mit dem Volltext (title) an — für den
    // Hover-Tooltip in den IK/PK-Selektoren (Editor). Deckt auch Altdaten ab, in
    // denen der Titel nicht im Eintrag gespeichert ist (Fallback über die Refs).
    function withRefTitle(items, ls, kind) {
        return items.map((it) => ({
            ...it,
            title: it.title ?? refTitle(ls, it.node_id, kind) ?? undefined,
        }));
    }

</script>

<!-- Kontextmenü -->
{#snippet namenFelder(eintrag)}
    <NamenChips
        art="begriffe"
        namen={eintrag.begriffe ?? []}
        {aufloesung}
        {editMode}
        subjectId={fachId}
        curriculumId={curriculum?.id}
        {darfAnlegen}
        back={rueckweg}
        onchange={(neu) => setzeNamen(eintrag, "begriffe", neu)}
    />
    <NamenChips
        art="fachmethoden"
        namen={eintrag.fachmethoden ?? []}
        lokal={fachmethodenImCurriculum(curriculum)}
        {editMode}
        subjectId={fachId}
        curriculumId={curriculum?.id}
        onchange={(neu) => setzeNamen(eintrag, "fachmethoden", neu)}
    />
{/snippet}

{#if showContextMenu}
    <div role="presentation" class="fixed inset-0 z-50 bg-black/10" onclick={hideMenu}></div>
    <div
        class="fixed z-50 bg-white dark:bg-dark-bg-2 rounded-lg shadow-lg border border-light-ui-3 dark:border-dark-ui-3 py-2 min-w-[160px]"
        style="left: {showContextMenu.x}px; top: {showContextMenu.y}px;"
        role="presentation"
        onclick={(e) => e.stopPropagation()}
    >
        <button
            onclick={() => {
                confirmDelete(
                    showContextMenu.type,
                    showContextMenu.id,
                    showContextMenu.type === "kapitel"
                        ? curriculum.kapitel.find(
                              (k) => k.id === showContextMenu.id,
                          )?.title
                        : showContextMenu.type === "lernsequenz"
                          ? curriculum.kapitel
                                .find((k) => k.id === showContextMenu.chapterId)
                                ?.lernsequenzen.find(
                                    (ls) => ls.id === showContextMenu.id,
                                )?.title
                          : "Eintrag",
                    showContextMenu.chapterId,
                    showContextMenu.lsId,
                );
                hideMenu();
            }}
            class="w-full px-4 py-2 text-left text-sm text-light-re dark:text-dark-re hover:bg-light-re/10 dark:hover:bg-dark-re/10 flex items-center gap-2"
        >
            <Trash2 class="w-4 h-4" />
            Löschen
        </button>
    </div>
{/if}

<!-- Lösch-Bestätigungsdialog -->
{#if deleteConfirm}
    <div
        class="fixed inset-0 z-50 bg-black/30 flex items-center justify-center p-4"
    >
        <div
            class="bg-white dark:bg-dark-bg-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3 p-6 max-w-md w-full"
            role="dialog"
            aria-modal="true"
        >
            <h3
                class="text-lg font-semibold text-light-tx dark:text-dark-tx mb-3"
            >
                Löschen bestätigen
            </h3>
            <p class="text-light-tx-2 dark:text-dark-tx-2 mb-4">
                Möchtest du "{deleteConfirm.title}" wirklich löschen? Dieser
                Vorgang kann nicht rückgängig gemacht werden.
            </p>
            <div class="flex gap-3 justify-end">
                <button
                    onclick={() => (deleteConfirm = null)}
                    class="px-4 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                           text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
                >
                    Abbrechen
                </button>
                <button
                    onclick={executeDelete}
                    class="px-4 py-2 text-sm rounded-md bg-light-re dark:bg-dark-re text-on-fill
                           hover:opacity-90"
                >
                    Löschen
                </button>
            </div>
        </div>
    </div>
{/if}

<!-- Ein Klick in die Tabelle schließt das Kontextmenü (Maus). -->
<svelte:document onvisibilitychange={beiRueckkehr} />

<CurriculumAbdeckung curriculumId={curriculum?.id} stand={curriculum} {editMode} {fachId} />

{#if fehlListe.fehlend.length || fehlListe.mehrdeutig.length}
    <details
        class="mt-3 rounded-md border border-light-ui-3 dark:border-dark-ui-3 px-3 py-2 text-sm"
        data-uebersicht="begriffe"
    >
        <summary class="cursor-pointer text-light-tx dark:text-dark-tx">
            {fehlendUeberschrift(fehlListe)}
        </summary>
        <div class="mt-2 space-y-2">
            {#if fehlListe.fehlend.length}
                <p class="text-xs text-light-tx-2 dark:text-dark-tx-2" data-legende="begriffe">
                    Gestrichelte Begriffe gibt es in der Bibliothek noch nicht.
                    {darfAnlegen
                        ? "Mit „anlegen“ legst du sie für die Fachschaft an — einzeln am Begriff oder gesammelt über die Gerüste."
                        : "Anlegen kann die Fachschaft des Fachs."}
                </p>
                <ul class="text-xs space-y-0.5">
                    {#each fehlListe.fehlend as b (`${b.name}\u0000${b.fassung ?? ""}`)}
                        <li class="text-light-tx dark:text-dark-tx">
                            {b.name}{b.fassung ? ` (${b.fassung})` : ""}
                            <span class="text-light-tx-2 dark:text-dark-tx-2">
                                — {b.anzahl}× — {b.kapitel.join("; ")}
                            </span>
                        </li>
                    {/each}
                </ul>
            {/if}
            {#if fehlListe.mehrdeutig.length}
                <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                    Mehrdeutig — im Editor am gelben Begriff die Fassung wählen:
                    {fehlListe.mehrdeutig.map((b) => b.name).join(", ")}
                </p>
            {/if}
            {#if fehlListe.fehlend.length && curriculum?.id}
                <div class="flex flex-wrap items-center gap-2 pt-1">
                    <a
                        href={fehlendeBegriffeUrl(curriculum.id, "txt")}
                        download
                        class="inline-flex items-center gap-1.5 px-3 py-1 text-xs rounded-md border border-light-ui-3 dark:border-dark-ui-3
                               text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
                    >
                        <FileDown class="w-4 h-4" /> Liste
                    </a>
                    <a
                        href={fehlendeBegriffeUrl(curriculum.id, "zip")}
                        download
                        title="Je Begriff eine Datei im Format der Fachbegriffe — Definition eintragen und unter Fachbegriffe einspielen"
                        class="inline-flex items-center gap-1.5 px-3 py-1 text-xs rounded-md border border-light-ui-3 dark:border-dark-ui-3
                               text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
                    >
                        <FileDown class="w-4 h-4" /> Gerüste (Zip)
                    </a>
                    {#if editMode}
                        <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                            Die Downloads zeigen den gespeicherten Stand.
                        </span>
                    {/if}
                </div>
            {/if}
        </div>
    </details>
{/if}

{#if absprachenDaten?.fach?.length}
    <!-- Absprachen anderer Fächer mit dem ganzen Fach, ohne Kapitel (0.63, AY Teil 2) -->
    <div class="mt-3 rounded-md border border-light-ui-3 dark:border-dark-ui-3 px-3 py-2" data-uebersicht="absprachen">
        <AbsprachenAnzeige vonAussen={absprachenDaten.fach} titel="Absprachen anderer Fächer mit dem ganzen Fach" />
    </div>
{/if}

<div class="overflow-x-auto" role="presentation" onclick={hideMenu}>
    <table class="kapitel-tabelle w-full text-left border-collapse text-sm">
        <thead>
            <!-- Abstand zu den Kästen darüber (Abdeckung, Begriffe), wie zwischen den Kapiteln -->
            <tr aria-hidden="true" class="abstand">
                <th colspan={editMode ? 5 : 4}
                    class="h-4 p-0 border-0 border-b border-light-ui-3 dark:border-dark-ui-3 bg-light-bg-2 dark:bg-dark-bg-2"></th>
            </tr>
            <tr class="border-y border-light-ui-3 dark:border-dark-ui-3">
                <th
                    class="px-3 py-2 font-medium text-light-tx-2 dark:text-dark-tx-2 w-1/6"
                >
                    Prozessbezogene Kompetenzen
                </th>
                <th
                    class="px-3 py-2 font-medium text-light-tx-2 dark:text-dark-tx-2 w-1/6"
                >
                    Inhaltsbezogene Kompetenzen
                </th>
                <th
                    class="px-3 py-2 font-medium text-light-tx-2 dark:text-dark-tx-2 w-1/3"
                >
                    Konkretisierung
                </th>
                <th
                    class="px-3 py-2 font-medium text-light-tx-2 dark:text-dark-tx-2 w-1/3"
                >
                    Hinweise &amp; Material
                </th>
                {#if editMode}
                    <th class="px-3 py-2 w-12"></th>
                {/if}
            </tr>
        </thead>
        <tbody>
            {#each curriculum?.kapitel || [] as kap, kapIndex (kap.id)}
                <!-- Abstand zwischen den Kapiteln (0.63): Die Kapitel setzen sich ab, auch wenn
                     Einleitung und Absprachen im Editor viel Raum einnehmen. -->
                {#if kapIndex > 0}
                    <tr aria-hidden="true" class="abstand">
                        <td colspan={editMode ? 5 : 4}
                            class="h-6 p-0 border-y border-x-0 border-light-ui-3 dark:border-dark-ui-3 bg-light-bg-2 dark:bg-dark-bg-2"></td>
                    </tr>
                {/if}
                <!-- Kapitel-Kopfzeile; `id` als Sprungziel (Leitlinien-Übersicht, 0.53) -->
                <tr
                    id="kapitel-{kap.id}"
                    class="scroll-mt-24 bg-light-bg-2 dark:bg-dark-bg-2 {editMode
                        ? 'cursor-move'
                        : ''}"
                    draggable={editMode}
                    ondragstart={(e) => {
                        e.preventDefault();
                        handleDragStart(e, "kapitel", kap.id);
                    }}
                    ondragover={(e) => {
                        e.preventDefault();
                        handleDragOver(e);
                    }}
                    ondrop={(e) => {
                        e.preventDefault();
                        handleDrop(e, "kapitel", kap.id);
                    }}
                >
                    <td
                        colspan={editMode ? 5 : 4}
                        class="px-3 py-3 font-bold text-light-tx dark:text-dark-tx border-b border-light-ui-3 dark:border-dark-ui-3 relative"
                    >
                        {#if editMode}
                            <div class="flex items-center gap-2">
                                <button
                                    onclick={() => toggleChapter(kap.id)}
                                    class="p-0.5 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 rounded shrink-0"
                                    title={collapsedChapters.has(kap.id) ? "Ausklappen" : "Einklappen"}
                                >
                                    <ChevronRight
                                        class="w-4 h-4 text-light-tx-2 dark:text-dark-tx-2 transition-transform {collapsedChapters.has(kap.id) ? '' : 'rotate-90'}"
                                    />
                                </button>
                                <Move
                                    class="w-4 h-4 text-light-tx-2 dark:text-dark-tx-2 cursor-move"
                                />
                                <input
                                    type="text"
                                    value={kap.title}
                                    oninput={(e) => {
                                        kap.title = e.target.value;
                                        curriculum.kapitel = [
                                            ...curriculum.kapitel,
                                        ];
                                        onchange();
                                    }}
                                    class="font-bold text-light-tx dark:text-dark-tx bg-transparent border-none focus:outline-none flex-1"
                                />
                                <span
                                    class="text-xs text-light-tx-2 dark:text-dark-tx-2 shrink-0"
                                >
                                    ({kapitelStd(kap)} Std.)
                                </span>
                                <button
                                    onclick={(e) =>
                                        showMenu(e, "kapitel", kap.id)}
                                    class="p-1 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 rounded"
                                >
                                    <MoreVertical
                                        class="w-4 h-4 text-light-tx-2 dark:text-dark-tx-2"
                                    />
                                </button>
                            </div>
                        {:else}
                            <div class="flex items-center gap-2">
                                <button
                                    onclick={() => toggleChapter(kap.id)}
                                    class="p-0.5 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 rounded shrink-0"
                                    title={collapsedChapters.has(kap.id) ? "Ausklappen" : "Einklappen"}
                                >
                                    <ChevronRight
                                        class="w-4 h-4 text-light-tx-2 dark:text-dark-tx-2 transition-transform {collapsedChapters.has(kap.id) ? '' : 'rotate-90'}"
                                    />
                                </button>
                                <span>{kap.title}</span>
                                {#if kapitelStd(kap) > 0}
                                    <span
                                        class="text-light-tx-2 dark:text-dark-tx-2 text-xs font-normal"
                                    >
                                        ({kapitelStd(kap)} Stunden)
                                    </span>
                                {/if}
                            </div>
                        {/if}
                    </td>
                </tr>

                <!-- Kapitel-Inhalt (einklappbar) -->
                {#if !collapsedChapters.has(kap.id)}

                <!-- Kapitel-Einleitung (editierbar) -->
                {#if kap.metadata?.einleitung || editMode}
                    <tr class="bg-light-bg-2 dark:bg-dark-bg-2">
                        <td
                            colspan={editMode ? 5 : 4}
                            class="px-3 py-2 text-sm text-light-tx-2 dark:text-dark-tx-2 border-b border-light-ui-3 dark:border-dark-ui-3"
                        >
                            {#if editMode}
                                <textarea
                                    value={kap.metadata?.einleitung || ""}
                                    oninput={(e) => {
                                        kap.metadata = {
                                            ...kap.metadata,
                                            einleitung: e.target.value,
                                        };
                                        curriculum.kapitel = [
                                            ...curriculum.kapitel,
                                        ];
                                        onchange();
                                    }}
                                    class="w-full text-sm text-light-tx-2 dark:text-dark-tx-2 bg-transparent border-none focus:outline-none resize-none"
                                    rows="4"
></textarea>
                            {:else}
                                {kap.metadata.einleitung}
                            {/if}
                        </td>
                    </tr>
                {/if}

                <!-- Absprachen mit anderen Fächern (0.63, AY Teil 2) -->
                {#if editMode}
                    <tr class="bg-light-bg-2 dark:bg-dark-bg-2">
                        <td id="absprachen-{kap.id}" colspan="5"
                            class="px-3 py-2 border-b border-light-ui-3 dark:border-dark-ui-3 scroll-mt-24">
                            <AbsprachenEditor
                                absprachen={kap.metadata?.absprachen ?? []}
                                eigenesFachId={fachId}
                                stufe={grade}
                                vorbelegung={vorbelegungen[kap.id] ?? null}
                                onchange={(liste) => absprachenSetzen(kap, liste)}
                            />
                            {#if absprachenVon(kap.id).von_aussen.length}
                                <div class="mt-3">
                                    <AbsprachenAnzeige
                                        vonAussen={absprachenVon(kap.id).von_aussen}
                                        titel="Von anderen Fächern eingetragen"
                                        ongegen={(a) => gegenVorbelegen(kap.id, a)}
                                    />
                                </div>
                            {/if}
                        </td>
                    </tr>
                {:else if hatAbsprachen(absprachenVon(kap.id).eigene, absprachenVon(kap.id).von_aussen)}
                    <tr class="bg-light-bg-2 dark:bg-dark-bg-2">
                        <td id="absprachen-{kap.id}" colspan="4"
                            class="px-3 py-2 border-b border-light-ui-3 dark:border-dark-ui-3 scroll-mt-24">
                            <AbsprachenAnzeige
                                eigene={absprachenVon(kap.id).eigene}
                                vonAussen={absprachenVon(kap.id).von_aussen}
                                gegenHref={curriculum?.can_edit ? (a) => gegenabspracheHref(curriculum.id, a) : null}
                            />
                        </td>
                    </tr>
                {/if}

                <!-- Lernsequenzen -->
                {#each kap.lernsequenzen || [] as ls, lsIndex (ls.id)}
                    <!-- Lernsequenz-Titel -->
                    {#if ls.title || editMode}
                        <tr
                            class="bg-light-bg-2 dark:bg-dark-bg-2 {editMode
                                ? 'cursor-move'
                                : ''}"
                            draggable={editMode}
                            ondragstart={(e) => {
                                e.preventDefault();
                                handleDragStart(
                                    e,
                                    "lernsequenz",
                                    ls.id,
                                    kap.id,
                                );
                            }}
                            ondragover={(e) => {
                                e.preventDefault();
                                handleDragOver(e);
                            }}
                            ondrop={(e) => {
                                e.preventDefault();
                                handleDrop(e, "lernsequenz", ls.id, kap.id);
                            }}
                        >
                            <td
                                colspan={editMode ? 5 : 4}
                                class="px-3 py-2 font-semibold text-light-tx dark:text-dark-tx border-b border-light-ui-3 dark:border-dark-ui-3 relative"
                            >
                                {#if editMode}
                                    <div class="flex items-center gap-2">
                                        <Move
                                            class="w-4 h-4 text-light-tx-2 dark:text-dark-tx-2 cursor-move"
                                        />
                                        <input
                                            type="text"
                                            value={ls.title || ""}
                                            oninput={(e) => {
                                                ls.title = e.target.value;
                                                curriculum.kapitel = [
                                                    ...curriculum.kapitel,
                                                ];
                                                onchange();
                                            }}
                                            class="font-semibold text-light-tx dark:text-dark-tx bg-transparent border-none focus:outline-none flex-1"
                                            placeholder="Lernsequenz-Titel"
                                        />
                                        {#if ls.metadata?.bp_leitidee}
                                            <span
                                                class="text-light-tx-2 dark:text-dark-tx-2 text-xs"
                                            >
                                                (Leitidee: {ls.metadata
                                                    .bp_leitidee})
                                            </span>
                                        {/if}
                                        <div
                                            class="flex items-center gap-1 text-xs text-light-tx-2 dark:text-dark-tx-2 shrink-0"
                                        >
                                            <input
                                                type="number"
                                                min="0"
                                                value={ls.metadata?.std || ""}
                                                oninput={(e) => {
                                                    ls.metadata = {
                                                        ...ls.metadata,
                                                        std: Number(
                                                            e.target.value,
                                                        ),
                                                    };
                                                    curriculum.kapitel = [
                                                        ...curriculum.kapitel,
                                                    ];
                                                    onchange();
                                                }}
                                                class="w-12 text-xs text-center text-light-tx dark:text-dark-tx
                                                       bg-light-bg dark:bg-dark-bg border border-light-ui-3 dark:border-dark-ui-3
                                                       rounded px-1 py-0.5 focus:outline-none focus:border-primary dark:focus:border-primary-dark"
                                                placeholder="0"
                                            />
                                            <span>Std.</span>
                                        </div>
                                        <button
                                            onclick={(e) =>
                                                showMenu(
                                                    e,
                                                    "lernsequenz",
                                                    ls.id,
                                                    kap.id,
                                                )}
                                            class="p-1 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 rounded"
                                        >
                                            <MoreVertical
                                                class="w-4 h-4 text-light-tx-2 dark:text-dark-tx-2"
                                            />
                                        </button>
                                    </div>
                                {:else}
                                    {ls.title}
                                    {#if ls.metadata?.bp_leitidee}
                                        <span
                                            class="ml-2 text-light-tx-2 dark:text-dark-tx-2 text-xs"
                                        >
                                            (Leitidee: {ls.metadata
                                                .bp_leitidee})
                                        </span>
                                    {/if}
                                    {#if lernsequenzStd(ls) > 0}
                                        <span
                                            class="ml-2 text-light-tx-2 dark:text-dark-tx-2 text-xs"
                                        >
                                            ({lernsequenzStd(ls)} Std.)
                                        </span>
                                    {/if}
                                {/if}
                            </td>
                        </tr>
                    {/if}

                    <!-- Einträge der Lernsequenz -->
                    {#each ls.metadata?.eintraege || [] as eintrag, entryIndex (entryIndex)}
                        <tr
                            class="border-b border-light-ui-3 dark:border-dark-ui-3
                                   {entryIndex % 2 === 0
                                ? 'bg-white dark:bg-transparent'
                                : 'bg-light-bg-2/50 dark:bg-dark-bg-2/50'}"
                            draggable={editMode}
                            ondragstart={(e) => {
                                e.preventDefault();
                                handleDragStart(
                                    e,
                                    "eintrag",
                                    entryIndex,
                                    kap.id,
                                    ls.id,
                                );
                            }}
                            ondragover={(e) => {
                                e.preventDefault();
                                handleDragOver(e);
                            }}
                            ondrop={(e) => {
                                e.preventDefault();
                                handleDrop(
                                    e,
                                    "eintrag",
                                    entryIndex,
                                    kap.id,
                                    ls.id,
                                );
                            }}
                        >
                            <!-- PK-Spalte (nur bei erstem Eintrag mit rowspan) -->
                            {#if entryIndex === 0}
                                <td
                                    rowspan={(ls.metadata?.eintraege || [])
                                        .length}
                                    class="px-3 py-2 vertical-align-top"
                                >
                                    {#if editMode}
                                        <PKSelector
                                            {subjectId}
                                            {grade}
                                            {bpVersion}
                                            selected={withRefTitle(normalizePk(eintrag.pk), ls, "pk")}
                                            onchange={(newPk) => {
                                                eintrag.pk = newPk;
                                                curriculum.kapitel = [
                                                    ...curriculum.kapitel,
                                                ];
                                                onchange();
                                            }}
                                        />
                                    {:else}
                                        {#each normalizePk(eintrag.pk) as pk}
                                            {#if pk.node_id}
                                                <a
                                                    href={nodeLink(pk.node_id)}
                                                    title={pk.veraltet ? VERALTET_HINT : refTitle(ls, pk.node_id, "pk")}
                                                    class="block mb-1 underline hover:text-primary dark:hover:text-primary-dark
                                                           {pk.veraltet ? 'line-through text-light-re dark:text-dark-re' : 'text-light-bl dark:text-dark-bl'}"
                                                >
                                                    {pk.pk_id}{#if pk.veraltet}&nbsp;⚠{/if}
                                                </a>
                                            {:else}
                                                <span
                                                    class="block mb-1 {pk.veraltet ? 'line-through text-light-re dark:text-dark-re' : 'text-light-tx-2 dark:text-dark-tx-2'}"
                                                    title={pk.veraltet ? VERALTET_HINT : null}
                                                    >{pk.pk_id}{#if pk.veraltet}&nbsp;⚠{/if}</span
                                                >
                                            {/if}
                                        {/each}
                                    {/if}
                                </td>
                            {/if}

                            <!-- IK-Spalte -->
                            <td class="px-3 py-2 vertical-align-top">
                                {#if editMode}
                                    <IKSelector
                                        {subjectId}
                                        {grade}
                                        {bpVersion}
                                        selected={withRefTitle(normalizeIk(eintrag.ik), ls, "ik")}
                                        onchange={(newIk) => {
                                            eintrag.ik = newIk;
                                            curriculum.kapitel = [
                                                ...curriculum.kapitel,
                                            ];
                                            onchange();
                                        }}
                                    />
                                    {#each normalizeIk(eintrag.ik).filter((ik) => qvVon(ik.node_id).length) as ik (ik.node_id)}
                                        <div class="mt-1 text-xs text-light-tx-2 dark:text-dark-tx-2">
                                            {ik.nr}
                                            <Querverweise liste={qvVon(ik.node_id)}
                                                onabsprache={(f, e) => absprachVorbelegen(kap.id, f, e)} />
                                        </div>
                                    {/each}
                                {:else}
                                    {#each normalizeIk(eintrag.ik) as ik}
                                        {#if ik.node_id}
                                            <a
                                                href={nodeLink(ik.node_id)}
                                                title={ik.veraltet ? VERALTET_HINT : refTitle(ls, ik.node_id, "ik")}
                                                class="inline-block mr-1 underline hover:text-primary dark:hover:text-primary-dark
                                                       {ik.veraltet ? 'line-through text-light-re dark:text-dark-re' : 'text-light-bl dark:text-dark-bl'}"
                                            >
                                                {ik.nr}{#if ik.veraltet}&nbsp;⚠{/if}
                                            </a>
                                            <Querverweise liste={qvVon(ik.node_id)} />
                                        {:else}
                                            <span
                                                class="inline-block mr-1 {ik.veraltet ? 'line-through text-light-re dark:text-dark-re' : 'text-light-tx dark:text-dark-tx'}"
                                                title={ik.veraltet ? VERALTET_HINT : null}
                                                >{ik.nr}{#if ik.veraltet}&nbsp;⚠{/if}</span
                                            >
                                        {/if}
                                        {#if ik.partiell}
                                            <span
                                                class="text-xs text-light-tx-2 dark:text-dark-tx-2"
                                                >[…]</span
                                            >
                                        {/if}
                                    {/each}
                                {/if}
                            </td>

                            <!-- Konkretisierung -->
                            <td class="px-3 py-2 vertical-align-top">
                                {#if editMode}
                                    <p
                                        class="text-xs font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1"
                                    >
                                        Konkretisierung
                                    </p>
                                    <textarea
                                        value={eintrag.konkretisierung || ""}
                                        oninput={(e) => {
                                            eintrag.konkretisierung =
                                                e.target.value;
                                            curriculum.kapitel = [
                                                ...curriculum.kapitel,
                                            ];
                                            onchange();
                                        }}
                                        class="w-full text-sm rounded border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx p-2"
                                        rows="8"
                                        placeholder="Konkretisierungstext"
></textarea>
                                    {@render namenFelder(eintrag)}
                                {:else}
                                    {#if eintrag.konkretisierung}
                                        <div
                                            class="prose prose-sm dark:prose-invert max-w-none
                                                    prose-p:my-1 prose-ul:my-1 prose-ol:my-1
                                                    prose-p:text-light-tx dark:prose-p:text-dark-tx
                                                    prose-a:text-light-bl dark:prose-a:text-dark-bl"
                                        >
                                            {@html renderMarkdown(
                                                eintrag.konkretisierung,
                                            )}
                                        </div>
                                    {/if}
                                    {@render namenFelder(eintrag)}
                                {/if}
                            </td>

                            <!-- Hinweise -->
                            <td class="px-3 py-2 vertical-align-top">
                                {#if editMode}
                                    <div class="space-y-3">
                                        <div>
                                            <p
                                                class="text-xs font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1"
                                            >
                                                Hinweise
                                            </p>
                                            <HinweisEditor
                                                value={eintrag.hinweise || ""}
                                                onchange={(newVal) => {
                                                    eintrag.hinweise = newVal;
                                                    curriculum.kapitel = [
                                                        ...curriculum.kapitel,
                                                    ];
                                                    onchange();
                                                }}
                                            />
                                        </div>
                                        <div>
                                            <p
                                                class="text-xs font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1"
                                            >
                                                Material
                                            </p>
                                            <MaterialEditor
                                                value={eintrag.material || ""}
                                                onchange={(newVal) => {
                                                    eintrag.material = newVal;
                                                    curriculum.kapitel = [
                                                        ...curriculum.kapitel,
                                                    ];
                                                    onchange();
                                                }}
                                            />
                                        </div>
                                    </div>
                                {:else}
                                    <div class="space-y-2 text-sm">
                                        <!-- Hinweise -->
                                        {#if eintrag.hinweise}
                                            {@const parts = parseHinweise(
                                                eintrag.hinweise,
                                            )}
                                            <div
                                                class="prose prose-sm dark:prose-invert max-w-none
                                                       prose-p:my-1 prose-ul:my-1 prose-ol:my-1
                                                       prose-p:text-light-tx-2 dark:prose-p:text-dark-tx-2
                                                       prose-li:text-light-tx-2 dark:prose-li:text-dark-tx-2
                                                       prose-a:text-light-bl dark:prose-a:text-dark-bl"
                                            >
                                                {#each parts as part}
                                                    {#if part.kind === "lp"}
                                                        <HinweisChip
                                                            typ="leitperspektive"
                                                            lp_code={part.label}
                                                            href={bausteinPfad(part.node_id, $page.url)}
                                                        />
                                                    {:else if part.kind === "lpa"}
                                                        <HinweisChip
                                                            typ="leitperspektive_aspekt"
                                                            lp_code={part.label}
                                                            href={bausteinPfad(part.node_id, $page.url)}
                                                        />
                                                    {:else if part.kind === "lb" || part.kind === "lba"}
                                                        <HinweisChip
                                                            typ={part.kind === "lb" ? "leitlinie" : "leitlinie_aspekt"}
                                                            lp_code={part.label}
                                                            href={bausteinPfad(part.node_id, $page.url)}
                                                        />
                                                    {:else if part.kind === "ik"}
                                                        <HinweisChip
                                                            typ="fach_bezug"
                                                            fach={part.label}
                                                            href={bausteinPfad(part.node_id, $page.url)}
                                                        />
                                                    {:else if part.label.trim()}
                                                        <!-- Freitext als Markdown (URLs verlinkt marked/gfm selbst) -->
                                                        {@html renderMarkdown(part.label)}
                                                    {/if}
                                                {/each}
                                            </div>
                                        {/if}

                                        <!-- Material -->
                                        {#if eintrag.material}
                                            {@const matParts = parseMaterial(
                                                eintrag.material,
                                            )}
                                            <div class="text-xs">
                                                <span
                                                    class="font-medium text-light-tx-2 dark:text-dark-tx-2"
                                                    >Material:</span
                                                >
                                                <div
                                                    class="prose prose-sm dark:prose-invert max-w-none
                                                           prose-p:my-1 prose-ul:my-1 prose-ol:my-1
                                                           prose-p:text-light-tx-2 dark:prose-p:text-dark-tx-2
                                                           prose-li:text-light-tx-2 dark:prose-li:text-dark-tx-2
                                                           prose-a:text-light-bl dark:prose-a:text-dark-bl"
                                                >
                                                    {#each matParts as part}
                                                        {#if part.kind === "node"}
                                                            <HinweisChip
                                                                typ="material"
                                                                text={part.label}
                                                                href={bausteinPfad(part.node_id, $page.url)}
                                                            />
                                                        {:else if part.label.trim()}
                                                            <!-- Freitext als Markdown (URLs verlinkt marked/gfm selbst) -->
                                                            {@html renderMarkdown(part.label)}
                                                        {/if}
                                                    {/each}
                                                </div>
                                            </div>
                                        {/if}

                                        {#if !eintrag.hinweise && !eintrag.material}
                                            <span
                                                class="text-light-tx-3 dark:text-dark-tx-3 text-xs"
                                                >–</span
                                            >
                                        {/if}
                                    </div>
                                {/if}
                            </td>

                            {#if editMode}
                                <td class="px-3 py-2 text-center">
                                    <button
                                        onclick={(e) =>
                                            showMenu(
                                                e,
                                                "eintrag",
                                                entryIndex,
                                                kap.id,
                                                ls.id,
                                            )}
                                        class="p-1 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 rounded"
                                    >
                                        <MoreVertical
                                            class="w-4 h-4 text-light-tx-2 dark:text-dark-tx-2"
                                        />
                                    </button>
                                </td>
                            {/if}
                        </tr>
                    {/each}

                    <!-- Neue Eintrag Zeile im Edit-Mode -->
                    {#if editMode && (ls.metadata?.eintraege || []).length === 0}
                        <tr
                            class="border-b border-light-ui-3 dark:border-dark-ui-3"
                        >
                            <td class="px-3 py-2"></td>
                            <td class="px-3 py-2"></td>
                            <td
                                class="px-3 py-2 text-light-tx-3 dark:text-dark-tx-3 text-xs italic"
                            >
                                Keine Einträge
                            </td>
                            <td class="px-3 py-2"></td>
                            <td class="px-3 py-2 text-center">
                                <button
                                    onclick={() =>
                                        addEintrag(kapIndex, lsIndex)}
                                    class="inline-flex items-center gap-1 text-sm text-light-bl dark:text-dark-bl hover:underline"
                                >
                                    <Plus class="w-4 h-4" /> Eintrag
                                </button>
                            </td>
                        </tr>
                    {:else if editMode}
                        <tr
                            class="border-b border-light-ui-3 dark:border-dark-ui-3 bg-light-bg-2/50 dark:bg-dark-bg-2/50"
                        >
                            <td colspan="4" class="px-3 py-2">
                                <button
                                    onclick={() =>
                                        addEintrag(kapIndex, lsIndex)}
                                    class="inline-flex items-center gap-1 text-sm text-light-bl dark:text-dark-bl hover:underline"
                                >
                                    <Plus class="w-4 h-4" /> Neuer Eintrag
                                </button>
                            </td>
                            <td class="px-3 py-2"></td>
                        </tr>
                    {/if}
                {/each}

                <!-- Neue Lernsequenz Zeile im Edit-Mode -->
                {#if editMode && (kap.lernsequenzen || []).length === 0}
                    <tr class="bg-light-bg-2 dark:bg-dark-bg-2">
                        <td
                            colspan="5"
                            class="px-3 py-2 text-center text-sm text-light-tx-3 dark:text-dark-tx-3 italic"
                        >
                            Keine Lernsequenzen
                        </td>
                    </tr>
                    <tr class="bg-light-bg-2 dark:bg-dark-bg-2">
                        <td colspan="5" class="px-3 py-2">
                            <button
                                onclick={() => addLernsequenz(kapIndex)}
                                class="inline-flex items-center gap-1 text-sm text-light-bl dark:text-dark-bl hover:underline"
                            >
                                <Plus class="w-4 h-4" /> Lernsequenz hinzufügen
                            </button>
                        </td>
                    </tr>
                {:else if editMode}
                    <tr class="bg-light-bg-2 dark:bg-dark-bg-2">
                        <td colspan="5" class="px-3 py-2">
                            <button
                                onclick={() => addLernsequenz(kapIndex)}
                                class="inline-flex items-center gap-1 text-sm text-light-bl dark:text-dark-bl hover:underline"
                            >
                                <Plus class="w-4 h-4" /> Lernsequenz hinzufügen
                            </button>
                        </td>
                    </tr>
                {/if}

                {/if}<!-- Ende einklappbarer Kapitelinhalt -->
            {/each}

            <!-- Neues Kapitel im Edit-Mode -->
            {#if editMode && (curriculum?.kapitel || []).length === 0}
                <tr class="bg-light-bg-2 dark:bg-dark-bg-2">
                    <td
                        colspan="5"
                        class="px-3 py-4 text-center text-sm text-light-tx-3 dark:text-dark-tx-3"
                    >
                        <p class="mb-2">Keine Kapitel vorhanden</p>
                        <button
                            onclick={addKapitel}
                            class="inline-flex items-center gap-1 text-sm text-light-bl dark:text-dark-bl hover:underline"
                        >
                            <Plus class="w-4 h-4" /> Erstes Kapitel hinzufügen
                        </button>
                    </td>
                </tr>
            {:else if editMode}
                <!-- Außerhalb der Kapitel-Kästen: ohne Rand links und rechts, Rand oben schließt das
                     letzte Kapitel ab (0.63). -->
                <tr class="abstand">
                    <td colspan="5" class="px-0 pt-3 pb-1 border-t border-light-ui-3 dark:border-dark-ui-3 bg-light-bg-2 dark:bg-dark-bg-2">
                        <button
                            type="button"
                            onclick={addKapitel}
                            class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium
                                   border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg
                                   text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                        >
                            <Plus class="w-4 h-4" /> Kapitel hinzufügen
                        </button>
                    </td>
                </tr>
            {/if}
        </tbody>
    </table>
</div>

<style>
    /* Rand links und rechts an jeder Zeile außer den Abstandszeilen zwischen den Kapiteln (0.63):
       So wirkt jedes Kapitel als Kasten, und die Abstände bleiben offen. */
    .kapitel-tabelle > :is(thead, tbody) > tr:not(.abstand) > :is(td, th):first-child {
        border-left: 1px solid var(--color-light-ui-3);
    }
    .kapitel-tabelle > :is(thead, tbody) > tr:not(.abstand) > :is(td, th):last-child {
        border-right: 1px solid var(--color-light-ui-3);
    }
    /* In der Lesesicht schließt die letzte Zeile das letzte Kapitel ab. */
    .kapitel-tabelle > tbody > tr:not(.abstand):last-child > td {
        border-bottom: 1px solid var(--color-light-ui-3);
    }
    :global(.dark) .kapitel-tabelle > tbody > tr:not(.abstand):last-child > td {
        border-bottom-color: var(--color-dark-ui-3);
    }
    :global(.dark) .kapitel-tabelle > :is(thead, tbody) > tr:not(.abstand) > :is(td, th):first-child {
        border-left-color: var(--color-dark-ui-3);
    }
    :global(.dark) .kapitel-tabelle > :is(thead, tbody) > tr:not(.abstand) > :is(td, th):last-child {
        border-right-color: var(--color-dark-ui-3);
    }

    .vertical-align-top {
        vertical-align: top;
    }

    /* Input-Styling im Edit-Mode */
    input[type="text"],
    input[type="number"],
    textarea {
        outline: none;
        transition: border-color 0.15s ease;
    }

    input[type="text"]:focus,
    input[type="number"]:focus,
    textarea:focus {
        border-color: #3b82f6;
        box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
    }
</style>
