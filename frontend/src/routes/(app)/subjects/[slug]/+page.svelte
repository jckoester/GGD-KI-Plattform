<script>
  import { page } from '$app/stores'
  import { subjects } from '$lib/stores/subjects.js'
  import SubjectIcon from '$lib/components/SubjectIcon.svelte'

  const subject = $derived(
    $subjects.find(s => s.slug === $page.params.slug) ?? null
  )
</script>

<div class="flex flex-col items-center justify-center h-64 gap-3
            text-light-tx-2 dark:text-dark-tx-2">
  {#if subject}
    <SubjectIcon name={subject.icon} size={32} color={subject.color} />
    <p class="text-lg font-semibold text-light-tx dark:text-dark-tx">{subject.name}</p>
  {/if}
  <p class="text-sm">Diese Ansicht wird in Kürze verfügbar sein.</p>
</div>
