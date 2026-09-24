<script>
    import PageBody from '$lib/components/PageBody.svelte'
    import { onMount } from "svelte";
    import { ArrowLeft, Check, ChevronRight, Pencil, TriangleAlert, Trash2, X } from "lucide-svelte";
    import {
        aktuelleTeachingGroups,
        fruehereTeachingGroups,
        refreshMyGroups,
    } from "$lib/stores/myGroups.js";
    import {
        potentialTeachingGroups,
        refreshPotentialTeachingGroups,
    } from "$lib/stores/potentialTeachingGroups.js";
    import {
        groupsConfig,
        refreshGroupsConfig,
    } from "$lib/stores/groupsConfig.js";
    import {
        getExclusions,
        removeExclusion,
        createTeachingGroup,
        deleteTeachingGroup,
        setGruppenJahrgang,
        setGruppenAnzeigename,
        setGruppenSchuelerSichtbarkeit,
        addExclusion,
    } from "$lib/api.js";
    import { subjectMap } from "$lib/stores/subjects.js";
    import SubjectIcon from "$lib/components/SubjectIcon.svelte";
    import StundenrasterUebernahme from "$lib/components/StundenrasterUebernahme.svelte";
    import GruppenAngebote from "$lib/components/GruppenAngebote.svelte";
    import InfoBanner from "$lib/components/InfoBanner.svelte";

    let exclusions = $state([]);
    let loading = $state(true);
    let error = $state(null);

    async function loadData() {
        loading = true;
        error = null;
        try {
            const exclData = await getExclusions();
            exclusions = exclData;
        } catch (err) {
            error = err.message || "Fehler beim Laden der Daten";
        } finally {
            loading = false;
        }
    }

    async function handleConfirm(classGroupId, subjectId) {
        try {
            await createTeachingGroup(classGroupId, subjectId);
            await refreshMyGroups();
            await refreshPotentialTeachingGroups();
        } catch (err) {
            error = err.message || "Fehler beim Bestätigen";
        }
    }

    async function handleExclude(classGroupId, subjectId) {
        try {
            await addExclusion(classGroupId, subjectId);
            await refreshPotentialTeachingGroups();
            await loadData();
        } catch (err) {
            error = err.message || "Fehler beim Ablehnen";
        }
    }

    async function handleRemoveExclusion(classGroupId, subjectId) {
        try {
            await removeExclusion(classGroupId, subjectId);
            await createTeachingGroup(classGroupId, subjectId);
            await refreshMyGroups();
            await refreshPotentialTeachingGroups();
            await loadData();
        } catch (err) {
            error = err.message || "Fehler beim Reaktivieren";
        }
    }

    // ── Anzeigename ──────────────────────────────────────────────────────────
    //
    // Der Name aus dem Schulkonto (`ch2-ks-abi28`) ist für die Oberfläche unbrauchbar.
    // Umbenannt wird nur die **Anzeige**; der rohe Name bleibt, und die
    // Stundenplan-Zuordnung rechnet weiter auf ihm — deshalb der Hinweis im Formular.
    let bearbeiteteGruppe = $state(null);
    let nameEntwurf = $state("");

    function nameBearbeiten(group) {
        bearbeiteteGruppe = group.id;
        nameEntwurf = group.display_name ?? "";
    }

    async function nameSpeichern(groupId) {
        try {
            await setGruppenAnzeigename(groupId, nameEntwurf.trim() || null);
            bearbeiteteGruppe = null;
            await refreshMyGroups();
        } catch (err) {
            error = err.message || "Der Name konnte nicht gespeichert werden";
        }
    }

    // Begrenzter Testbetrieb: Der Schalter erscheint nur, wenn der Modus aktiv ist —
    // andernfalls wäre er wirkungslos, und ein wirkungsloser Schalter ist schlimmer als
    // keiner. Die Freigabe selbst bleibt beim Abschalten des Modus gespeichert.
    async function jahrgangSetzen(groupId, roh) {
        // Leeres Feld heißt „nicht festgelegt" — dann leitet die Plattform wieder ab.
        const wert = roh.trim() === "" ? null : Number(roh);
        if (wert !== null && !Number.isInteger(wert)) return;
        try {
            await setGruppenJahrgang(groupId, wert);
            await refreshMyGroups();
        } catch (err) {
            error = err.message || "Der Jahrgang konnte nicht gespeichert werden";
        }
    }

    async function sichtbarkeitSetzen(groupId, sichtbar) {
        try {
            await setGruppenSchuelerSichtbarkeit(groupId, sichtbar);
            await refreshMyGroups();
        } catch (err) {
            error = err.message || "Die Freigabe konnte nicht gespeichert werden";
        }
    }

    async function handleDeleteGroup(groupId) {
        try {
            await deleteTeachingGroup(groupId);
            await refreshMyGroups();
            await refreshPotentialTeachingGroups();
        } catch (err) {
            error = err.message || "Fehler beim Löschen";
        }
    }

    onMount(() => {
        loadData();
        refreshPotentialTeachingGroups();
        refreshGroupsConfig();
    });
</script>

<PageBody>
    <button
        onclick={() => history.back()}
        class="flex items-center gap-1 mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx transition-colors"
    >
        <ArrowLeft class="w-4 h-4" /> Zurück
    </button>
    <div class="mb-6">
        <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">
            Unterrichtsgruppen verwalten
        </h1>
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
            Hier kannst du deine Unterrichtsgruppen verwalten und abgelehnte
            Kombinationen wiederherstellen.
        </p>
    </div>

    {#if error}
        <div
            class="mb-4 p-3 bg-red-100 dark:bg-red-900/20 border border-red-300 dark:border-red-700 rounded-lg"
        >
            <p class="text-sm text-red-700 dark:text-red-300">{error}</p>
        </div>
    {/if}

    <!-- Stundenraster für alle Gruppen auf einmal. Steht oben, weil es die Einrichtung
         ist: Wer hier landet, hat seine Gruppen gerade erst zusammengestellt. Die
         Komponente zeigt sich nur, wenn eine Stundenplanquelle eingerichtet ist. -->
    <section class="mb-8">
        <GruppenAngebote />

        <StundenrasterUebernahme />
    </section>

    <!-- Sektion 1: Eigene Unterrichtsgruppen -->
    <section class="mb-8">
        <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx mb-4">
            Meine Unterrichtsgruppen
        </h2>

        {#if $groupsConfig.student_subjects_opt_in}
            <InfoBanner
                message="Erprobungsbetrieb: Deine Schüler:innen sehen ein Fach nur, wenn du die zugehörige Gruppe unten freigibst. Ohne Freigabe erscheint es weder in ihrer Fachübersicht noch im Chat."
            />
        {/if}

        {#if loading}
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                Wird geladen...
            </p>
        {:else if $aktuelleTeachingGroups.length === 0}
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                {$fruehereTeachingGroups.length > 0
                    ? "Für dieses Schuljahr hast du noch keine Unterrichtsgruppen."
                    : "Du hast noch keine Unterrichtsgruppen."}
            </p>
        {:else}
            <div class="space-y-3">
                {#each $aktuelleTeachingGroups as group (group.id)}
                    {@render gruppenzeile(group, true)}
                {/each}
            </div>
        {/if}

        <!-- Frühere Schuljahre: eingeklappt, nicht verborgen. Eine Fehleinschätzung der
             Regel bleibt damit folgenlos — und sobald die Gruppe im laufenden Schuljahr
             Stunden oder einen Jahresplan hat, ordnet sie sich von selbst wieder oben
             ein. -->
        {#if $fruehereTeachingGroups.length > 0}
            <details class="mt-4 group">
                <summary
                    class="flex items-center gap-1 cursor-pointer text-sm text-light-tx-2 dark:text-dark-tx-2
                           hover:text-light-tx dark:hover:text-dark-tx transition-colors"
                >
                    <ChevronRight
                        size={16}
                        class="transition-transform group-open:rotate-90"
                    />
                    Aus früheren Schuljahren ({$fruehereTeachingGroups.length})
                </summary>
                <div class="space-y-3 mt-3">
                    {#each $fruehereTeachingGroups as group (group.id)}
                        {@render gruppenzeile(group)}
                    {/each}
                </div>
            </details>
        {/if}
    </section>

    <!-- Sektion 2: Vorgeschlagene Unterrichtsgruppen -->
    {#if $groupsConfig.allow_manual_teaching_groups && $potentialTeachingGroups.length > 0}
        <section class="mb-8">
            <h2
                class="text-lg font-semibold text-light-tx dark:text-dark-tx mb-1"
            >
                Vorgeschlagene Unterrichtsgruppen
            </h2>
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-4">
                Basierend auf deinen Klassen- und Fachschaft-Mitgliedschaften.
                Bestätigst du einen Vorschlag, entsteht die Unterrichtsgruppe — und
                die Schüler:innen der Klasse sind ab ihrer nächsten Anmeldung darin.
            </p>
            <div class="space-y-3">
                {#each $potentialTeachingGroups as pot (pot.class_group_id + "-" + pot.subject_id)}
                    <div
                        class="flex items-center justify-between p-3 rounded-lg
                      bg-light-bg-2 dark:bg-dark-bg-2 border border-light-ui-2 dark:border-dark-ui-2"
                    >
                        <div class="flex items-center gap-3 min-w-0">
                            {#if pot.subject_icon || pot.subject_color}
                                <SubjectIcon
                                    name={pot.subject_icon}
                                    size={20}
                                    color={pot.subject_color}
                                />
                            {/if}
                            <div class="min-w-0">
                                <p
                                    class="font-medium text-light-tx dark:text-dark-tx truncate"
                                >
                                    {pot.class_name}
                                </p>
                                <p
                                    class="text-xs text-light-tx-2 dark:text-dark-tx-2"
                                >
                                    {pot.subject_name}
                                </p>
                            </div>
                        </div>
                        <div class="flex items-center gap-2 shrink-0">
                            <button
                                onclick={() =>
                                    handleConfirm(
                                        pot.class_group_id,
                                        pot.subject_id,
                                    )}
                                class="px-3 py-1.5 rounded-lg bg-primary dark:bg-primary-dark
                       text-white text-sm font-medium hover:opacity-90 transition-opacity
                       flex items-center gap-1.5"
                                title="Ich unterrichte dieses Fach in dieser Klasse"
                            >
                                <Check size={14} />
                                Bestätigen
                            </button>
                            <button
                                onclick={() =>
                                    handleExclude(
                                        pot.class_group_id,
                                        pot.subject_id,
                                    )}
                                class="p-1.5 rounded-lg text-light-tx-2 dark:text-dark-tx-2
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                                title="Ich unterrichte dieses Fach nicht in dieser Klasse"
                            >
                                <X size={16} />
                            </button>
                        </div>
                    </div>
                {/each}
            </div>
        </section>
    {/if}

    <!-- Sektion 3: Abgelehnte Kombinationen -->
    <section class="mb-8">
        <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx mb-4">
            Abgelehnte Kombinationen
        </h2>

        {#if loading}
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                Wird geladen...
            </p>
        {:else if exclusions.length === 0}
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                Keine abgelehnten Kombinationen.
            </p>
        {:else}
            <div class="space-y-3">
                {#each exclusions as excl (excl.class_group_id + "-" + excl.subject_id)}
                    <div
                        class="flex items-center justify-between p-3 rounded-lg
                      bg-light-bg-2 dark:bg-dark-bg-2 border border-light-ui-2 dark:border-dark-ui-2"
                    >
                        <div class="flex items-center gap-3 min-w-0">
                            {#if $subjectMap[excl.subject_id]}
                                <SubjectIcon
                                    name={$subjectMap[excl.subject_id]?.icon}
                                    size={20}
                                    color={$subjectMap[excl.subject_id]?.color}
                                />
                            {/if}
                            <div class="min-w-0">
                                <p
                                    class="font-medium text-light-tx dark:text-dark-tx truncate"
                                >
                                    {excl.class_name}
                                </p>
                                {#if $subjectMap[excl.subject_id]}
                                    <p
                                        class="text-xs text-light-tx-2 dark:text-dark-tx-2"
                                    >
                                        {$subjectMap[excl.subject_id].name}
                                    </p>
                                {/if}
                            </div>
                        </div>
                        <button
                            onclick={() =>
                                handleRemoveExclusion(
                                    excl.class_group_id,
                                    excl.subject_id,
                                )}
                            class="px-3 py-1.5 rounded-lg bg-primary dark:bg-primary-dark
                     text-white text-sm font-medium hover:opacity-90 disabled:opacity-50
                     transition-opacity flex items-center gap-1.5"
                        >
                            <Check size={14} />
                            Reaktivieren
                        </button>
                    </div>
                {/each}
            </div>
        {/if}
    </section>

    <!-- Hinweis -->
    <section class="text-sm text-light-tx-2 dark:text-dark-tx-2">
        <p>
            <strong>Hinweis:</strong> Unterrichtsgruppen aus dem SSO-System werden
            automatisch verwaltet und können hier nicht gelöscht werden. Manuell angelegte
            Gruppen (ohne SSO-Verknüpfung) können gelöscht werden.
        </p>
    </section>
    
</PageBody>

{#snippet gruppenzeile(group, mitFreigabe = false)}
    {@const subj = group.subject_id ? $subjectMap[group.subject_id] : null}
    {@const href = subj ? `/subjects/${subj.slug}/groups/${group.id}` : null}
                    <div
        class="flex items-center justify-between p-3 rounded-lg
      bg-light-bg-2 dark:bg-dark-bg-2 border border-light-ui-2 dark:border-dark-ui-2"
    >
        <div class="flex items-center gap-3 min-w-0">
            {#if subj}
                <SubjectIcon
                    name={subj.icon}
                    size={20}
                    color={subj.color}
                />
            {/if}
            <div class="min-w-0">
                {#if bearbeiteteGruppe === group.id}
                    <div class="flex items-center gap-2">
                        <input
                            bind:value={nameEntwurf}
                            placeholder={group.name}
                            onkeydown={(e) => {
                                if (e.key === "Enter") nameSpeichern(group.id);
                                if (e.key === "Escape") bearbeiteteGruppe = null;
                            }}
                            class="px-2 py-1 text-sm bg-light-bg dark:bg-dark-bg border border-light-ui-3 dark:border-dark-ui-3 rounded-md
                                   text-light-tx dark:text-dark-tx outline-none focus:border-primary dark:focus:border-primary-dark"
                        />
                        <button
                            onclick={() => nameSpeichern(group.id)}
                            class="p-1 rounded text-light-gr dark:text-dark-gr hover:bg-light-bg-2 dark:hover:bg-dark-bg-2"
                            title="Übernehmen"
                        ><Check size={16} /></button>
                        <button
                            onclick={() => (bearbeiteteGruppe = null)}
                            class="p-1 rounded text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-bg-2 dark:hover:bg-dark-bg-2"
                            title="Abbrechen"
                        ><X size={16} /></button>
                    </div>
                    <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mt-1">
                        Leer lassen, um den Namen aus dem Schulkonto zu verwenden. Der
                        Anzeigename ändert nichts an der Zuordnung zum Stundenplan.
                    </p>
                {:else if href}
                    <a
        {href}
        class="font-medium text-light-tx dark:text-dark-tx hover:text-light-bl dark:hover:text-dark-bl transition-colors truncate block"
                    >
        {group.name}
                    </a>
                {:else}
                    <p
        class="font-medium text-light-tx dark:text-dark-tx truncate"
                    >
        {group.name}
                    </p>
                {/if}
                {#if subj || group.letztes_schuljahr}
                    <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                        {[subj?.name, group.letztes_schuljahr]
                            .filter(Boolean)
                            .join(" · ")}
                    </p>
                {/if}
                <!-- Ohne Fach lässt sich die Gruppe nicht als Fach darstellen: kein
                     Symbol, keine Fachseite, und bei Schüler:innen erscheint sie gar
                     nicht. Geprüft wird `subject_id`, NICHT das aufgelöste `subj` —
                     solange die Fachliste noch lädt, ist `subj` für jede Gruppe leer,
                     und der Hinweis blitzte überall auf. -->
                {#if group.subject_id == null}
                    <p
                        class="mt-1 flex items-start gap-1.5 text-xs text-light-tx-2 dark:text-dark-tx-2"
                    >
                        <TriangleAlert
                            size={13}
                            class="mt-px shrink-0 text-light-or dark:text-dark-or"
                        />
                        <span>
                            Keinem Fach zugeordnet — Schüler:innen sehen diese Gruppe
                            nicht. Das lässt sich nur in der Konfiguration des
                            Schulkontos beheben; bitte an die Administration wenden.
                        </span>
                    </p>
                {/if}
                <label
                    class="mt-1.5 flex items-center gap-2 text-xs text-light-tx-2 dark:text-dark-tx-2"
                >
                    Jahrgang
                    <input
                        type="number"
                        min="1"
                        max="13"
                        value={group.jahrgang ?? ""}
                        placeholder="wird abgeleitet"
                        onchange={(e) => jahrgangSetzen(group.id, e.currentTarget.value)}
                        class="w-28 rounded border border-light-ui-3 dark:border-dark-ui-3
                               bg-light-bg dark:bg-dark-bg px-1.5 py-0.5
                               text-light-tx dark:text-dark-tx"
                    />
                </label>
                {#if mitFreigabe && $groupsConfig.student_subjects_opt_in}
                    <label
                        class="mt-1.5 flex items-center gap-2 text-xs text-light-tx-2 dark:text-dark-tx-2
                               {group.subject_id == null
                            ? 'opacity-50'
                            : 'cursor-pointer'}"
                    >
                        <input
                            type="checkbox"
                            checked={group.student_visible}
                            disabled={group.subject_id == null}
                            onchange={(e) =>
                                sichtbarkeitSetzen(
                                    group.id,
                                    e.currentTarget.checked,
                                )}
                            class="rounded border-light-ui-3 dark:border-dark-ui-3 text-primary"
                        />
                        Für Schüler:innen sichtbar
                    </label>
                {/if}
            </div>
        </div>
        <div class="flex items-center gap-2 shrink-0">
            {#if bearbeiteteGruppe !== group.id}
                <button
                    onclick={() => nameBearbeiten(group)}
                    class="p-1.5 rounded-lg text-light-tx-2 dark:text-dark-tx-2
                           hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 hover:text-light-tx dark:hover:text-dark-tx transition-colors"
                    title="Anzeigename ändern"
                >
                    <Pencil size={16} />
                </button>
            {/if}
            <span
                class="text-xs px-2 py-0.5 rounded-full
          {group.sso_group_id
                    ? 'bg-light-ui-3 dark:bg-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2'
                    : 'bg-primary/10 dark:bg-primary-dark/10 text-primary dark:text-primary-dark'}"
            >
                {group.sso_group_id ? "SSO" : "Manuell"}
            </span>
            {#if !group.sso_group_id}
                <button
                    onclick={() => handleDeleteGroup(group.id)}
                    class="p-1.5 rounded-lg text-light-re dark:text-dark-re
         hover:bg-red-100 dark:hover:bg-red-900/20 transition-colors"
                    title="Löschen"
                >
                    <Trash2 size={16} />
                </button>
            {/if}
        </div>
    </div>
{/snippet}
