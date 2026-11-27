<script>
    /**
     * Absprachen mit anderen Fächern am Kapitel bearbeiten (0.63, Päckchen AY Teil 2, Schritt 3).
     *
     * Liste der eigenen Absprachen mit „Bearbeiten“ und „Entfernen“, darunter das Formular: Fach,
     * wahlweise Curriculum und Kapitel des Fachs, Art, Text. Gespeichert wird mit dem Curriculum
     * (Editor); das Backend prüft beim Speichern noch einmal. Regeln in `$lib/absprachen.js`.
     *
     * Props:
     * - absprachen: die Liste am Kapitel (`kap.metadata.absprachen`)
     * - eigenesFachId: Fach des Curriculums (erscheint nicht in der Auswahl)
     * - stufe: Klassenstufe des Curriculums — Curricula dieser Stufe stehen oben
     * - vorbelegung: öffnet das Formular vorbelegt (aus einer Fundstelle der Querverweise)
     * - onchange(liste): neue Liste
     */
    import { Pencil, Plus, Trash2 } from "@lucide/svelte";
    import { getCurriculaBySubject, getCurriculum } from "$lib/api.js";
    import { subjects } from "$lib/stores/subjects.js";
    import FachWahl from "$lib/components/FachWahl.svelte";
    import SubjectIcon from "$lib/components/SubjectIcon.svelte";
    import {
        ARTEN, ART_AUSWAHL, ART_KURZ, ausFormular, curriculaZurAuswahl, fachToenung, faecherZurAuswahl,
        formular, formularFehler, uebernehmen,
    } from "$lib/absprachen.js";

    let { absprachen = [], eigenesFachId = null, stufe = null, vorbelegung = null, onchange = () => {} } = $props();

    let form = $state(null);
    let curricula = $state([]);
    let kapitel = $state([]);
    let ladefehler = $state(null);

    const faecher = $derived(faecherZurAuswahl($subjects, eigenesFachId));
    const jeCode = $derived(Object.fromEntries(($subjects ?? []).filter((s) => s.fach_code).map((s) => [s.fach_code, s])));
    const eigenesFach = $derived(($subjects ?? []).find((s) => s.id === eigenesFachId)?.fach_code ?? null);
    const fehler = $derived(form ? formularFehler(form, { vorhandene: absprachen ?? [], eigenesFach }) : "");
    const formId = `abspr-${Math.random().toString(36).slice(2, 9)}`;

    // Vorbelegung von außen öffnet das Formular (und lädt Curricula und Kapitel dazu).
    $effect(() => {
        if (vorbelegung) oeffnen(formular(vorbelegung));
    });

    async function oeffnen(f) {
        form = f;
        await fachGewaehlt(false);
        if (form.curriculum_id) await curriculumGewaehlt(false);
    }

    async function fachGewaehlt(zuruecksetzen = true) {
        curricula = [];
        kapitel = [];
        ladefehler = null;
        if (zuruecksetzen) Object.assign(form, { curriculum_id: "", kapitel_id: "", kapitel_titel: "" });
        const fach = jeCode[form.fach_code];
        if (!fach) return;
        try {
            curricula = curriculaZurAuswahl(await getCurriculaBySubject(fach.id), stufe);
        } catch (e) {
            ladefehler = e.message;
        }
    }

    async function curriculumGewaehlt(zuruecksetzen = true) {
        kapitel = [];
        ladefehler = null;
        if (zuruecksetzen) Object.assign(form, { kapitel_id: "", kapitel_titel: "" });
        if (!form.curriculum_id) return;
        try {
            const c = await getCurriculum(form.curriculum_id);
            kapitel = (c.kapitel ?? []).map((k) => ({ id: k.id, titel: k.title }));
        } catch (e) {
            ladefehler = e.message;
        }
    }

    function kapitelGewaehlt() {
        form.kapitel_titel = kapitel.find((k) => k.id === form.kapitel_id)?.titel ?? "";
    }

    function uebernimm() {
        if (fehler) return;
        onchange(uebernehmen(absprachen, ausFormular(form)));
        form = null;
    }

    function entferne(a) {
        onchange((absprachen ?? []).filter((x) => x !== a));
    }

    const feld = "w-full text-sm rounded border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx pl-2 pr-8 py-1";
    const knopf = "inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium border border-light-ui-3 dark:border-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors disabled:opacity-50";
</script>

<div class="space-y-2">
    <div class="text-xs font-semibold text-light-tx-2 dark:text-dark-tx-2">Absprachen mit anderen Fächern</div>
    {#if absprachen?.length}
        <ul class="space-y-1">
            {#each absprachen as a (a.id ?? a)}
                {@const fach = jeCode[a.fach_code]}
                <li class="flex items-start gap-2 text-sm text-light-tx dark:text-dark-tx">
                    <span class="shrink-0 rounded border border-light-ui-3 dark:border-dark-ui-3 px-1 text-[11px] text-light-tx-2 dark:text-dark-tx-2">{ART_KURZ[a.art] ?? a.art}</span>
                    <span class="shrink-0 inline-flex items-center gap-1 rounded border px-1 text-[11px] leading-4
                                 text-light-tx-2 dark:text-dark-tx-2 border-light-ui-3 dark:border-dark-ui-3"
                          style={fachToenung(fach?.color)}>
                        <SubjectIcon name={fach?.icon} size={11} color={fach?.color} />
                        {fach?.name ?? a.fach_code}
                    </span>
                    <span class="flex-1">
                        <span class="font-medium">{a.kapitel_titel ?? "ganzes Fach"}</span>{#if a.text}: {a.text}{/if}
                    </span>
                    <button type="button" class={knopf} onclick={() => oeffnen(formular({ ...a, curriculum_id: "" }))} aria-label="Absprache bearbeiten">
                        <Pencil class="w-3 h-3" />
                    </button>
                    <button type="button" class={knopf} onclick={() => entferne(a)} aria-label="Absprache entfernen">
                        <Trash2 class="w-3 h-3" />
                    </button>
                </li>
            {/each}
        </ul>
    {/if}

    {#if form}
        <div class="rounded border border-light-ui-3 dark:border-dark-ui-3 p-2 space-y-2" role="group" aria-labelledby="{formId}-titel">
            <div id="{formId}-titel" class="text-xs font-medium text-light-tx dark:text-dark-tx">
                {form.id ? "Absprache bearbeiten" : "Neue Absprache"}
            </div>
            <div class="grid gap-2 sm:grid-cols-3">
                <div class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                    <label for="{formId}-fach">Fach</label>
                    <FachWahl id="{formId}-fach" {faecher} wert={form.fach_code}
                              onwahl={(code) => { form.fach_code = code; fachGewaehlt(); }} />
                </div>
                <label class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                    Curriculum (wahlweise)
                    <select class={feld} value={form.curriculum_id}
                            onchange={(e) => { form.curriculum_id = e.target.value; curriculumGewaehlt(); }} disabled={!curricula.length}>
                        <option value="">{form.kapitel_titel && !form.curriculum_id ? `– bisher: ${form.kapitel_titel} –` : "– ganzes Fach –"}</option>
                        {#each curricula as c (c.id)}<option value={c.id}>{c.text}</option>{/each}
                    </select>
                </label>
                <label class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                    Kapitel
                    <!-- Ohne Bindung: Beim Bearbeiten ist das Curriculum des gespeicherten Kapitels nicht
                         bekannt; die Kennung bleibt stehen, bis jemand ein anderes wählt. -->
                    <select class={feld} value={form.kapitel_id}
                            onchange={(e) => { form.kapitel_id = e.target.value; kapitelGewaehlt(); }} disabled={!kapitel.length}>
                        <option value="">– wählen –</option>
                        {#each kapitel as k (k.id)}<option value={k.id}>{k.titel}</option>{/each}
                    </select>
                </label>
            </div>
            <label class="block text-xs text-light-tx-2 dark:text-dark-tx-2">
                Art
                <select class={feld} bind:value={form.art}>
                    {#each ARTEN as art (art)}<option value={art}>{ART_AUSWAHL[art]}</option>{/each}
                </select>
            </label>
            <label class="block text-xs text-light-tx-2 dark:text-dark-tx-2">
                Was vereinbart ist
                <textarea class="{feld} pr-2" rows="2" maxlength="1000" bind:value={form.text}
                          placeholder="etwa: Bruchrechnung vor Dichte, damit Dichte = Masse/Volumen verstanden wird"></textarea>
            </label>
            {#if ladefehler}<p class="text-xs text-light-re dark:text-dark-re">{ladefehler}</p>{/if}
            {#if fehler}<p class="text-xs text-light-tx-2 dark:text-dark-tx-2">{fehler}</p>{/if}
            <div class="flex justify-end gap-2">
                <button type="button" class={knopf} onclick={() => (form = null)}>Abbrechen</button>
                <button type="button" class="{knopf} bg-primary dark:bg-primary-dark text-on-fill border-transparent hover:opacity-90"
                        disabled={!!fehler} onclick={uebernimm}>Übernehmen</button>
            </div>
        </div>
    {:else}
        <button type="button" class={knopf} onclick={() => oeffnen(formular())}>
            <Plus class="w-3 h-3" /> Absprache hinzufügen
        </button>
    {/if}
</div>
