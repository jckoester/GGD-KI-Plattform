<script>
  import { page } from '$app/stores'
  import { goto } from '$app/navigation'
  import PageBody from '$lib/components/PageBody.svelte'
  import { subjectMap } from '$lib/stores/subjects.js'
  import { BP_CURRICULUM_CONTENT_TYPES } from '$lib/taxonomy.js'
  import { myTeachingGroups } from '$lib/stores/myGroups.js'
  import { user } from '$lib/stores/user.js'
  import { REITER, aktiverReiter } from '$lib/gruppenseite.js'
  import { groupsConfig } from '$lib/stores/groupsConfig.js'
  import { zeigtEintrag } from '$lib/stores/uiLevel.js'
  import { CircleCheck, TriangleAlert } from 'lucide-svelte'
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

  <!-- Erprobungsbetrieb: Ob diese Gruppe für ihre Schüler:innen sichtbar ist.
       Nur für Lehrkräfte — Schüler:innen sehen eine nicht freigegebene Gruppe ohnehin
       nicht, und für sie wäre die Auskunft ohne Handhabe. Der freigegebene Fall bleibt
       leise (er ist der Normalfall), der andere trägt die Handlung. -->
  {#if istLehrkraft && group && $groupsConfig.student_subjects_opt_in}
    {#if group.student_visible}
      <p class="mt-2 flex items-center gap-1.5 text-xs text-light-tx-2 dark:text-dark-tx-2">
        <CircleCheck size={13} class="shrink-0 text-light-gr dark:text-dark-gr" />
        Für Schüler:innen freigegeben.
        <a href="/profile/teaching-groups"
           class="underline hover:text-light-tx dark:hover:text-dark-tx transition-colors">
          Ändern
        </a>
      </p>
    {:else}
      <div class="mt-2 flex items-start gap-2 rounded border p-3 text-sm
                  bg-light-ye-bg dark:bg-dark-ye-bg
                  border-light-ye dark:border-dark-ye
                  text-light-tx dark:text-dark-tx">
        <TriangleAlert size={16} class="mt-0.5 shrink-0 text-light-ye dark:text-dark-ye" />
        <span>
          <b>Nicht für Schüler:innen freigegeben.</b> Sie sehen dieses Fach derzeit nicht —
          weder in ihrer Fachübersicht noch im Chat.
          <a href="/profile/teaching-groups"
             class="underline hover:no-underline">Unter „Meine Unterrichtsgruppen" freigeben</a>
        </span>
      </div>
    {/if}
  {/if}

  <!-- Reiter nur für Lehrkräfte: Schüler:innen sehen allein die Übersicht -->
  {#if istLehrkraft}
    <nav class="flex gap-1 border-b border-light-ui-2 dark:border-dark-ui-2 mb-6 mt-3">
      <!-- Ein Durchlauf für alle Einträge: Die Reihenfolge steht in `REITER`, nicht
           halb dort und halb hier. `extern` führt auf eine eigene Route (Planung) —
           das ist ein Link, kein Reiter, und muss auch einer bleiben. -->
      {#each REITER as tab (tab.id)}
        {@const gemeinsam =
          'px-4 py-2 text-sm font-medium border-b-2 transition-colors'}
        {#if tab.extern}
          <!-- Die Planung ist der einzige Reiter, der eine eigene Stufe hat: Sie hängt
               nicht in der Sidebar, sondern nur hier. Unterhalb ihrer Stufe verschwindet
               der Reiter — die Seite selbst bleibt über den Direktlink erreichbar und
               erklärt sich dort (Leitprinzip 1). -->
          {#if group && $zeigtEintrag('planner')}
            <a
              href={`/subjects/${subject?.slug ?? $page.params.slug}/groups/${group.id}/planner`}
              class="{gemeinsam} border-transparent
                     text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx"
            >
              {tab.label}
            </a>
          {/if}
        {:else}
          <button
            onclick={() => goto(`?tab=${tab.id}`, { replaceState: true, keepFocus: true })}
            class="{gemeinsam}
                   {activeTab === tab.id
                     ? 'border-primary text-light-bl dark:text-dark-bl dark:border-primary-dark'
                     : 'border-transparent text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx'}"
          >
            {tab.label}
          </button>
        {/if}
      {/each}
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
