<script>
  import { page } from '$app/stores'
  import { goto } from '$app/navigation'
  import PageBody from '$lib/components/PageBody.svelte'
  import { subjectMap } from '$lib/stores/subjects.js'
  import { BP_CURRICULUM_CONTENT_TYPES } from '$lib/taxonomy.js'
  import { myTeachingGroups } from '$lib/stores/myGroups.js'
  import { user } from '$lib/stores/user.js'
  import { REITER, aktiverReiter } from '$lib/gruppenseite.js'
  import SubjectIcon from '$lib/components/SubjectIcon.svelte'
  import GruppenUebersicht from '$lib/components/GruppenUebersicht.svelte'
  import GruppenArchiv from '$lib/components/GruppenArchiv.svelte'
  import KnowledgeNodeList from '$lib/components/KnowledgeNodeList.svelte'
  import CurriculumList from '$lib/components/CurriculumList.svelte'
  import BildungsplanTree from '$lib/components/BildungsplanTree.svelte'

  // ── Gruppe + Fach aus Stores ──────────────────────────────────────────────
  // `myTeachingGroups` führt die eigenen `teaching_group`-Mitgliedschaften — für
  // Schüler:innen ebenso wie für Lehrkräfte; der Filter kennt keine Rolle.
  const group = $derived(
    $myTeachingGroups.find(g => g.id === Number($page.params.id)) ?? null
  )
  const subject = $derived(
    group ? ($subjectMap[group.subject_id] ?? null) : null
  )
  // Voreingestellte Jahrgangsstufe aus dem Fach ableiten
  const defaultGrade = $derived(subject?.min_grade ?? null)

  // Admin ist eine Erweiterung der Lehrkraft-Rolle, kein eigener Nutzertyp
  // (CLAUDE.md, Rollenmodell) — deshalb `teacher`, nicht `teacher || admin`.
  const istLehrkraft = $derived($user?.roles?.includes('teacher') ?? false)

  // ── Reiter (URL-basiert, damit Zurück-Navigation den Reiter erhält) ────────
  // Die Regeln dazu — Liste, alte Kennungen, Rückfall — stehen in
  // `$lib/gruppenseite.js`, weil sie sich dort ohne Browser prüfen lassen.
  const activeTab = $derived(aktiverReiter($page.url.searchParams.get('tab')))
</script>

<PageBody>
  <!-- Seitenkopf mit Breadcrumb -->
  <div class="flex items-center gap-2 text-sm text-light-tx-2 dark:text-dark-tx-2 mb-1">
    {#if subject}
      <a href={`/subjects/${subject.slug}`}
         class="hover:text-light-tx dark:hover:text-dark-tx transition-colors flex items-center gap-1.5">
        <SubjectIcon name={subject.icon} size={14} color={subject.color} />
        {subject.name}
      </a>
      <span>/</span>
    {/if}
    <span class="text-light-tx dark:text-dark-tx font-medium">{group?.name ?? '…'}</span>
  </div>

  <!-- Reiter nur für Lehrkräfte: Schüler:innen sehen allein die Übersicht -->
  {#if istLehrkraft}
    <nav class="flex gap-1 border-b border-light-ui-2 dark:border-dark-ui-2 mb-6 mt-3">
      {#each REITER as tab (tab.id)}
        <button
          onclick={() => goto(`?tab=${tab.id}`, { replaceState: true, keepFocus: true })}
          class="px-4 py-2 text-sm font-medium border-b-2 transition-colors
                 {activeTab === tab.id
                   ? 'border-primary text-light-bl dark:text-dark-bl dark:border-primary-dark'
                   : 'border-transparent text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx'}"
        >
          {tab.label}
        </button>
      {/each}
      {#if group}
        <a
          href={`/subjects/${subject?.slug ?? $page.params.slug}/groups/${group.id}/planner`}
          class="px-4 py-2 text-sm font-medium border-b-2 border-transparent
                 text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx transition-colors"
        >
          Planung
        </a>
      {/if}
    </nav>
  {:else}
    <div class="mb-6"></div>
  {/if}

  <!-- Reiter-Inhalt -->
  {#if activeTab === 'uebersicht' || !istLehrkraft}
    <GruppenUebersicht {group} {subject} {istLehrkraft} />

  {:else if activeTab === 'curriculum'}
    <CurriculumList
      subjectId={subject?.id}
      subjectSlug={subject?.slug}
      subjectFachCode={subject?.fach_code}
      showNewButton={true}
    />

  {:else if activeTab === 'bildungsplan'}
    {#if subject?.id}
      <BildungsplanTree
        subjectId={subject.id}
        subjectSlug={subject.slug}
        initialGrade={defaultGrade}
      />
    {:else}
      <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 py-4">
        Kein Fach zugeordnet.
      </p>
    {/if}

  {:else if activeTab === 'archiv'}
    <GruppenArchiv subjectId={subject?.id} />

  {:else if activeTab === 'kontext'}
    <KnowledgeNodeList
      fixedGroupId={group?.id}
      showSubjectFilter={false}
      showNewButton={true}
      initialGrade={defaultGrade}
      excludeContentTypes={BP_CURRICULUM_CONTENT_TYPES}
    />
  {/if}
</PageBody>
