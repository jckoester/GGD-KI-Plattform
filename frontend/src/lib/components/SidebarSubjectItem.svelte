<script>
    import { slide } from "svelte/transition";
    import { ChevronDown, ChevronRight } from "lucide-svelte";
    import SubjectIcon from "./SubjectIcon.svelte";
    import TeachingGroupMenu from "./TeachingGroupMenu.svelte";
    import PotentialGroupMenu from "./PotentialGroupMenu.svelte";
    import { refreshMyGroups } from "$lib/stores/myGroups.js";
    import { refreshPotentialTeachingGroups } from "$lib/stores/potentialTeachingGroups.js";
    import { groupsConfig } from "$lib/stores/groupsConfig.js";
    import { page } from "$app/stores";

    let { section, expanded = false, ontoggle = () => {} } = $props()

    function formatCount(n) {
        if (n === 0) return "–";
        return String(n);
    }
</script>

{#if section.type === "student"}
    <!-- Schüler-Zeile: Fachname, Anzahl, Link.
         Das Ziel ist die **Unterrichtsgruppe**, nicht das Fach: Jeder Eintrag hier
         *ist* eine Gruppe (`sidebarSubjectSections` bildet für Schüler:innen eine
         Zeile je `teaching_group`). Der Umweg über `/subjects/<slug>` war zudem
         mehrdeutig — zwei Gruppen desselben Fachs zeigten auf dieselbe Adresse. -->
    {@const ziel = section.slug
        ? `/subjects/${section.slug}/groups/${section.groupId}`
        : "/history"}
    <a
        href={ziel}
        aria-current={section.slug && $page.url.pathname === ziel ? 'page' : undefined}
        class="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors
               text-light-tx dark:text-dark-tx
               {section.slug && $page.url.pathname === ziel
                 ? 'bg-light-ui-2 dark:bg-dark-ui-2 font-medium'
                 : 'hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
    >
        <SubjectIcon name={section.icon} size={15} color={section.color} />
        <span class="flex-1 truncate">
            {section.name}{section.qualifier ? ` · ${section.qualifier}` : ""}
        </span>
        <span class="text-xs text-light-tx-2 dark:text-dark-tx-2 shrink-0">
            {formatCount(section.count)}
        </span>
    </a>
{:else if section.type === "teacher"}
    {@const isSubjectActive = $page.url.pathname.startsWith(`/subjects/${section.slug}`)}
    <!-- Lehrkraft-Kopfzeile: Link zum Fach + optionaler Chevron-Toggle -->
    <div
        class="flex items-stretch gap-0 rounded-md transition-colors
               {isSubjectActive
                 ? 'bg-light-ui-2 dark:bg-dark-ui-2'
                 : 'hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
    >
        <a
            href={`/subjects/${section.slug}`}
            aria-current={$page.url.pathname === `/subjects/${section.slug}` ? 'page' : undefined}
            class="flex items-center gap-2 flex-1 min-w-0 px-3 py-1.5 text-sm font-medium
                   text-light-tx dark:text-dark-tx"
        >
            <SubjectIcon name={section.icon} size={15} color={section.color} />
            <span class="flex-1 truncate">{section.name}</span>
        </a>
        {#if section.groups.length > 0 || ($groupsConfig.allow_manual_teaching_groups && section.potentialGroups.length > 0)}
            <button
                type="button"
                onclick={ontoggle}
                class="flex items-center px-2.5 rounded-r-md shrink-0 text-light-tx-2 dark:text-dark-tx-2
                       hover:text-light-tx dark:hover:text-dark-tx
                       hover:bg-light-ui-3/50 dark:hover:bg-dark-ui-3/50 transition-colors"
                aria-expanded={expanded}
                aria-label={`${section.name} ${expanded ? "zuklappen" : "aufklappen"}`}
            >
                {#if expanded}
                    <ChevronDown size={14} />
                {:else}
                    <ChevronRight size={14} />
                {/if}
            </button>
        {/if}
    </div>

    {#if expanded && (section.groups.length > 0 || ($groupsConfig.allow_manual_teaching_groups && section.potentialGroups.length > 0))}
        <div transition:slide={{ duration: 150 }}>
            <!-- Bestätigte Gruppen -->
            {#each section.groups as group (group.groupId)}
                {@const isGroupActive = $page.url.pathname === `/subjects/${section.slug}/groups/${group.groupId}`}
                <!-- Die Einrückung liegt im Link, nicht im Rahmen — sonst reagierte der
                     linke Rand der Zeile nicht (0.48). -->
                <div
                    class="flex items-center group/item pr-1 rounded-md transition-colors
                           {isGroupActive
                             ? 'bg-light-ui-2 dark:bg-dark-ui-2 font-medium'
                             : 'hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
                >
                    <a
                        href={`/subjects/${section.slug}/groups/${group.groupId}`}
                        aria-current={isGroupActive ? 'page' : undefined}
                        class="flex items-center gap-2 flex-1 pl-10 py-1.5 text-sm min-w-0
                               text-light-tx-2 dark:text-dark-tx-2"
                    >
                        <span class="flex-1 truncate">{group.name}</span>
                        <span class="text-xs shrink-0"
                            >{formatCount(group.count)}</span
                        >
                    </a>
                    {#if group.isManual}
                        <TeachingGroupMenu
                            groupId={group.groupId}
                            className={group.name}
                            subjectId={section.subjectId}
                            onrefresh={() => {
                                refreshMyGroups();
                                refreshPotentialTeachingGroups();
                            }}
                        />
                    {/if}
                </div>
            {/each}

            <!-- Trennlinie (nur wenn beide Listen nicht leer UND Flag aktiv) -->
            {#if section.groups.length > 0 && section.potentialGroups.length > 0 && $groupsConfig.allow_manual_teaching_groups}
                <div
                    class="mx-3 my-1 border-t border-light-ui-2 dark:border-dark-ui-2"
                ></div>
            {/if}

            <!-- Potenzielle Gruppen: nur wenn Flag aktiv -->
            {#if $groupsConfig.allow_manual_teaching_groups}
                {#each section.potentialGroups as pot (pot.classGroupId + "-" + pot.subjectId)}
                    <div
                        class="flex items-center pl-10 pr-1 rounded-md
                      hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                    >
                        <span
                            class="flex-1 py-1.5 text-sm text-light-tx-3 dark:text-dark-tx-3 truncate"
                        >
                            {pot.className}
                        </span>
                        <PotentialGroupMenu
                            classGroupId={pot.classGroupId}
                            subjectId={pot.subjectId}
                            className={pot.className}
                            onrefresh={() => {
                                refreshMyGroups();
                                refreshPotentialTeachingGroups();
                            }}
                        />
                    </div>
                {/each}
            {/if}
        </div>
    {/if}
{/if}
