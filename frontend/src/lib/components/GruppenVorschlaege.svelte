<script>
    /**
     * Vorgeschlagene Unterrichtsgruppen aus Klasse × Fachschaft — bestätigen oder ablehnen.
     *
     * Aus der Seite „Unterricht“ gezogen (0.43, Plan Schritt 2), damit die Einrichtung dieselben
     * Vorschläge zeigt. Erscheint nur, wenn die Schule manuelle Gruppen erlaubt und es Vorschläge
     * gibt.
     *
     * Props: `onGeaendert()` nach einer Ablehnung (die Seite lädt ihre abgelehnten Kombinationen
     * neu); `onFehler(text)` — ohne sie steht die Meldung im Abschnitt selbst.
     */
    import { Check, X } from "lucide-svelte";
    import { addExclusion, createTeachingGroup } from "$lib/api.js";
    import { refreshMyGroups } from "$lib/stores/myGroups.js";
    import {
        potentialTeachingGroups,
        refreshPotentialTeachingGroups,
    } from "$lib/stores/potentialTeachingGroups.js";
    import { groupsConfig } from "$lib/stores/groupsConfig.js";
    import SubjectIcon from "$lib/components/SubjectIcon.svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";

    const { onGeaendert = null, onFehler = null } = $props();

    let fehler = $state(null);

    function melde(text) {
        if (onFehler) onFehler(text);
        else fehler = text;
    }

    async function bestaetigen(classGroupId, subjectId) {
        fehler = null;
        try {
            await createTeachingGroup(classGroupId, subjectId);
            await refreshMyGroups();
            await refreshPotentialTeachingGroups();
        } catch (err) {
            melde(err.message || "Fehler beim Bestätigen");
        }
    }

    async function ablehnen(classGroupId, subjectId) {
        fehler = null;
        try {
            await addExclusion(classGroupId, subjectId);
            await refreshPotentialTeachingGroups();
            await onGeaendert?.();
        } catch (err) {
            melde(err.message || "Fehler beim Ablehnen");
        }
    }
</script>

{#if $groupsConfig.allow_manual_teaching_groups && $potentialTeachingGroups.length > 0}
    <section class="mb-8">
        <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx mb-1">
            Vorgeschlagene Unterrichtsgruppen
        </h2>
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-4">
            Basierend auf deinen Klassen- und Fachschaft-Mitgliedschaften.
            Bestätigst du einen Vorschlag, entsteht die Unterrichtsgruppe — und
            die Schüler:innen der Klasse sind ab ihrer nächsten Anmeldung darin.
        </p>
        {#if fehler}<div class="mb-3"><ErrorBanner message={fehler} /></div>{/if}
        <div class="space-y-3">
            {#each $potentialTeachingGroups as pot (pot.class_group_id + "-" + pot.subject_id)}
                <div
                    class="flex items-center justify-between p-3 rounded-lg
                  bg-light-bg-2 dark:bg-dark-bg-2 border border-light-ui-2 dark:border-dark-ui-2"
                >
                    <div class="flex items-center gap-3 min-w-0">
                        {#if pot.subject_icon || pot.subject_color}
                            <SubjectIcon name={pot.subject_icon} size={20} color={pot.subject_color} />
                        {/if}
                        <div class="min-w-0">
                            <p class="font-medium text-light-tx dark:text-dark-tx truncate">
                                {pot.class_name}
                            </p>
                            <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                                {pot.subject_name}
                            </p>
                        </div>
                    </div>
                    <div class="flex items-center gap-2 shrink-0">
                        <button
                            onclick={() => bestaetigen(pot.class_group_id, pot.subject_id)}
                            class="px-3 py-1.5 rounded-lg bg-primary dark:bg-primary-dark
                   text-white text-sm font-medium hover:opacity-90 transition-opacity
                   flex items-center gap-1.5"
                            title="Ich unterrichte dieses Fach in dieser Klasse"
                        >
                            <Check size={14} />
                            Bestätigen
                        </button>
                        <button
                            onclick={() => ablehnen(pot.class_group_id, pot.subject_id)}
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
