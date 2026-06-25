<script>
    import { sidebarSubjectSections } from "$lib/stores/sidebarSections.js";
    import { hiddenSubjectIds, setSubjectHidden } from "$lib/stores/subjectVisibility.js";
    import { user } from "$lib/stores/user.js";
    import SubjectIcon from "$lib/components/SubjectIcon.svelte";
    import { ArrowLeft } from "lucide-svelte";

    const isTeacher = $derived($user?.roles?.includes("teacher") ?? false);

    // Alle Fächer der Lehrkraft, dedupliziert nach subjectId.
    const allSubjects = $derived.by(() => {
        const seen = new Set();
        return $sidebarSubjectSections.filter((s) => {
            if (seen.has(s.subjectId)) return false;
            seen.add(s.subjectId);
            return true;
        });
    });
</script>

<div class="h-full overflow-y-auto">
    <div class="max-w-2xl p-6">
    <button
        onclick={() => history.back()}
        class="flex items-center gap-1 mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx transition-colors"
    >
        <ArrowLeft class="w-4 h-4" /> Zurück
    </button>
    <div class="mb-6">
        <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">
            Fächer in der Seitenleiste
        </h1>
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
            Lege fest, welche deiner Fächer in der Seitenleiste erscheinen. Ausgeblendete
            Fächer bleiben hier jederzeit wieder einblendbar – etwa Fächer, in denen du nur
            persönliche Chats führst.
        </p>
    </div>

    {#if !isTeacher}
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
            Diese Einstellung ist nur für Lehrkräfte verfügbar.
        </p>
    {:else if allSubjects.length === 0}
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
            Dir sind noch keine Fächer zugeordnet.
        </p>
    {:else}
        <ul
            class="flex flex-col divide-y divide-light-ui-2 dark:divide-dark-ui-2
                   border border-light-ui-3 dark:border-dark-ui-3 rounded-xl overflow-hidden"
        >
            {#each allSubjects as s (s.subjectId)}
                {@const visible = !$hiddenSubjectIds.has(s.subjectId)}
                <li
                    class="flex items-center gap-3 px-4 py-3 bg-light-bg dark:bg-dark-bg-2"
                >
                    <SubjectIcon name={s.icon} size={18} color={s.color} />
                    <span
                        class="flex-1 min-w-0 text-sm font-medium text-light-tx dark:text-dark-tx truncate
                               {visible ? '' : 'opacity-60'}"
                    >
                        {s.name}
                    </span>
                    <span
                        class="text-xs text-light-tx-2 dark:text-dark-tx-2 w-24 text-right shrink-0"
                    >
                        {visible ? "Sichtbar" : "Ausgeblendet"}
                    </span>
                    <button
                        type="button"
                        role="switch"
                        aria-checked={visible}
                        onclick={() => setSubjectHidden(s.subjectId, visible)}
                        class="relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors
                               {visible
                            ? 'bg-primary dark:bg-primary-dark'
                            : 'bg-light-ui-3 dark:bg-dark-ui-3'}"
                        aria-label={visible
                            ? `${s.name} ausblenden`
                            : `${s.name} einblenden`}
                    >
                        <span
                            class="inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform
                                   {visible ? 'translate-x-[18px]' : 'translate-x-[3px]'}"
                        ></span>
                    </button>
                </li>
            {/each}
        </ul>
    {/if}
    </div>
</div>
