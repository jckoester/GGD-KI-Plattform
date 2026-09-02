<script>
    /**
     * Sammlungs-Editor (UI-Notiz A2) — eigene Seite, kein Modal.
     *
     * Das Formular entsteht aus dem Feldschema der Taxonomie: derselben Beschreibung,
     * aus der das Backend prüft. Ein neues Feld braucht deshalb keinen Code hier.
     */
    import { goto } from "$app/navigation";
    import { CONTENT_TYPE_LABELS, SCOPE_DEFAULTS } from "$lib/taxonomy.js";
    import {
        contentFeld,
        feldSchema,
        kategorieVon,
        metadatenAusFormular,
        pruefeEntwurf,
        sammlung,
    } from "$lib/collections.js";
    import { createContextNode, updateContextNode } from "$lib/api.js";
    import { myFachschaften } from "$lib/stores/myGroups.js";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import WarningBanner from "$lib/components/WarningBanner.svelte";

    let { typ, node = null, vorgabeFachId = null, back = null } = $props();

    /**
     * Wohin „Abbrechen" und der Kopf-Link führen.
     *
     * Ohne den durchgereichten Rückweg landete man am Anfang der Sammlung statt bei dem
     * gefilterten Ausschnitt, aus dem man kam — dieselbe Lücke, die der Zurück-Button
     * der Detailansicht hatte.
     */
    const zurueck = $derived(back || `/knowledge/collections/${typ}`);

    const config = $derived(sammlung(typ));
    const schema = $derived(feldSchema(typ));
    const text = $derived(contentFeld(typ));
    const label = $derived(CONTENT_TYPE_LABELS[typ] ?? typ);
    const [defRead, defWrite] = SCOPE_DEFAULTS[typ] ?? ["school", "private"];

    let title = $state(node?.title ?? "");
    let content = $state(node?.content ?? "");
    // Gewählt wird die **Fachschaft**, nicht das Fach: Sie trägt `write_scope_group_id`,
    // das die Datenbank bei `write_scope = subject` verlangt. Das Fach ergibt sich daraus.
    let fachschaftId = $state("");
    $effect(() => {
        if (fachschaftId) return;
        const fach = node?.subject_id ?? (vorgabeFachId ? Number(vorgabeFachId) : null);
        const treffer = $myFachschaften.find((g) => g.subject_id === fach);
        if (treffer) fachschaftId = String(treffer.id);
    });
    const gewaehlteFachschaft = $derived(
        $myFachschaften.find((g) => String(g.id) === fachschaftId) ?? null,
    );
    let felder = $state(
        Object.fromEntries(
            Object.keys(feldSchema(typ)).map((name) => [
                name,
                (node?.metadata ?? {})[name] ?? (feldSchema(typ)[name].typ === "liste" ? [] : ""),
            ]),
        ),
    );
    let listenEingabe = $state({});

    let speichert = $state(false);
    let fehler = $state({});
    let serverfehler = $state(null);

    // Ein Fach ist nur dort wählbar, wo die Fachschaft pflegt — bei `sozialform`
    // (schulweit) gäbe es nichts zu wählen.
    const fachWaehlbar = $derived((config?.filter ?? []).includes("fach"));
    // Ohne Fachschaft lässt sich ein fachgebundener Baustein gar nicht anlegen.
    const fachschaftFehlt = $derived(
        fachWaehlbar && !node && ["subject", "group"].includes(defWrite) && !fachschaftId,
    );

    const entwurf = $derived({ title, content, metadata: felder });
    const bereit = $derived(
        Object.keys(pruefeEntwurf(typ, entwurf)).length === 0 && !fachschaftFehlt,
    );

    function listeErgaenzen(name) {
        const wert = (listenEingabe[name] ?? "").trim();
        if (!wert) return;
        felder[name] = [...(felder[name] ?? []), wert];
        listenEingabe[name] = "";
    }

    async function speichern() {
        fehler = pruefeEntwurf(typ, entwurf);
        if (Object.keys(fehler).length > 0) return;

        speichert = true;
        serverfehler = null;
        try {
            const payload = {
                title: title.trim(),
                content: content.trim() || null,
                metadata: metadatenAusFormular(typ, felder, node?.metadata ?? {}),
                subject_id: gewaehlteFachschaft?.subject_id ?? null,
            };
            const gespeichert = node
                ? await updateContextNode(node.id, payload)
                : await createContextNode({
                      ...payload,
                      category: kategorieVon(typ),
                      content_type: typ,
                      read_scope: defRead,
                      write_scope: defWrite,
                      // Pflicht bei `subject`/`group` — ohne die Gruppe weist die
                      // Datenbank den Baustein ab.
                      write_scope_group_id: ["subject", "group"].includes(defWrite)
                          ? gewaehlteFachschaft?.id ?? null
                          : null,
                  });
            // Nach dem Speichern in die Detailansicht (UI-Notiz A2) — mit dem Rückweg,
            // damit es von dort weiter in die gefilterte Sammlung geht.
            goto(
                `/knowledge/${gespeichert.id}?back=${encodeURIComponent(zurueck)}`,
            );
        } catch (e) {
            serverfehler = e.message;
        } finally {
            speichert = false;
        }
    }
</script>

<div class="h-full overflow-y-auto p-6 max-w-2xl">
    <a
        href={zurueck}
        class="text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx
               dark:hover:text-dark-tx transition-colors mb-1 block"
    >
        ← {label}
    </a>
    <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx mb-6">
        {node ? "Eintrag bearbeiten" : `Neuer Eintrag: ${label}`}
    </h1>

    {#if serverfehler}
        <div class="mb-4"><ErrorBanner message={serverfehler} /></div>
    {/if}

    <div class="space-y-5">
        <!-- Titel -->
        <div>
            <label
                for="titel"
                class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
            >
                Titel
            </label>
            <input
                id="titel"
                bind:value={title}
                class="w-full px-3 py-2 text-sm rounded-md border border-light-ui-3
                       dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg
                       text-light-tx dark:text-dark-tx"
            />
            {#if fehler.title}
                <p class="text-xs text-light-re dark:text-dark-re mt-1">{fehler.title}</p>
            {/if}
        </div>

        <!-- Knotentext -->
        <div>
            <label
                for="inhalt"
                class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
            >
                {text.label}{text.pflicht ? "" : " (optional)"}
            </label>
            <textarea
                id="inhalt"
                bind:value={content}
                rows="6"
                class="w-full px-3 py-2 text-sm rounded-md border border-light-ui-3
                       dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg
                       text-light-tx dark:text-dark-tx"
            ></textarea>
            {#if text.hinweis}
                <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mt-1">
                    {text.hinweis}
                </p>
            {/if}
            {#if fehler.content}
                <p class="text-xs text-light-re dark:text-dark-re mt-1">{fehler.content}</p>
            {/if}
        </div>

        <!-- Typspezifische Felder aus dem Schema -->
        {#each Object.entries(schema) as [name, feld]}
            <div>
                <label
                    for="feld-{name}"
                    class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
                >
                    {feld.label} (optional)
                </label>

                {#if feld.typ === "int"}
                    <input
                        id="feld-{name}"
                        type="number"
                        min={feld.min}
                        max={feld.max}
                        bind:value={felder[name]}
                        class="w-32 px-3 py-2 text-sm rounded-md border border-light-ui-3
                               dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg
                               text-light-tx dark:text-dark-tx"
                    />
                {:else if feld.typ === "auswahl"}
                    <select
                        id="feld-{name}"
                        bind:value={felder[name]}
                        class="px-3 py-2 text-sm rounded-md border border-light-ui-3
                               dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg
                               text-light-tx dark:text-dark-tx"
                    >
                        <option value="">— nicht gesetzt —</option>
                        {#each feld.werte ?? [] as wert}
                            <option value={wert}>{wert}</option>
                        {/each}
                    </select>
                {:else if feld.typ === "liste"}
                    <div class="flex flex-wrap gap-1.5 mb-2">
                        {#each felder[name] ?? [] as eintrag, i}
                            <span
                                class="inline-flex items-center gap-1 px-2 py-0.5 text-xs
                                       rounded-full border border-light-ui-3
                                       dark:border-dark-ui-3 text-light-tx dark:text-dark-tx"
                            >
                                {eintrag}
                                <button
                                    onclick={() =>
                                        (felder[name] = felder[name].filter((_, j) => j !== i))}
                                    class="text-light-tx-2 dark:text-dark-tx-2
                                           hover:text-light-re dark:hover:text-dark-re"
                                    aria-label="{eintrag} entfernen">×</button
                                >
                            </span>
                        {/each}
                    </div>
                    <input
                        id="feld-{name}"
                        bind:value={listenEingabe[name]}
                        onkeydown={(e) => {
                            if (e.key === "Enter") {
                                e.preventDefault();
                                listeErgaenzen(name);
                            }
                        }}
                        onblur={() => listeErgaenzen(name)}
                        placeholder="Eingeben und Enter"
                        class="w-full px-3 py-2 text-sm rounded-md border border-light-ui-3
                               dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg
                               text-light-tx dark:text-dark-tx"
                    />
                {:else}
                    <input
                        id="feld-{name}"
                        bind:value={felder[name]}
                        class="w-full px-3 py-2 text-sm rounded-md border border-light-ui-3
                               dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg
                               text-light-tx dark:text-dark-tx"
                    />
                {/if}

                {#if feld.hinweis}
                    <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mt-1">
                        {feld.hinweis}
                    </p>
                {/if}
                {#if fehler[name]}
                    <p class="text-xs text-light-re dark:text-dark-re mt-1">{fehler[name]}</p>
                {/if}
            </div>
        {/each}

        <!-- Fach -->
        {#if fachWaehlbar}
            <div>
                <label
                    for="fach"
                    class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
                >
                    Fachschaft
                </label>
                <select
                    id="fach"
                    bind:value={fachschaftId}
                    class="px-3 py-2 text-sm rounded-md border border-light-ui-3
                           dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg
                           text-light-tx dark:text-dark-tx"
                >
                    <option value="">— bitte wählen —</option>
                    {#each $myFachschaften as fs}
                        <option value={String(fs.id)}>{fs.name}</option>
                    {/each}
                </select>
                <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mt-1">
                    Wer den Eintrag pflegen darf. Nur eigene Fachschaften — für andere
                    ließe sich der Eintrag danach nicht ändern.
                </p>
                {#if fachschaftFehlt && $myFachschaften.length === 0}
                    <p class="text-xs text-light-re dark:text-dark-re mt-1">
                        Sie gehören keiner Fachschaft an; dieser Eintrag lässt sich
                        deshalb nicht anlegen.
                    </p>
                {/if}
            </div>
        {/if}

        {#if !node}
            <WarningBanner
                message="Sichtbarkeit: {defRead} lesen, {defWrite} bearbeiten — die
                         Vorgabe dieser Bausteinart. Ändern lässt sie sich nach dem
                         Speichern in der Knoten-Bearbeitung."
            />
        {/if}

        <div class="flex gap-3 pt-2">
            <button
                onclick={speichern}
                disabled={speichert || !bereit}
                class="px-4 py-2 rounded-md text-sm bg-primary dark:bg-primary-dark
                       text-white hover:opacity-90 disabled:opacity-50"
            >
                {speichert ? "Speichert…" : "Speichern"}
            </button>
            <a
                href={zurueck}
                class="px-4 py-2 rounded-md text-sm text-light-tx-2 dark:text-dark-tx-2
                       hover:text-light-tx dark:hover:text-dark-tx"
            >
                Abbrechen
            </a>
        </div>
    </div>
</div>
