<script>
  import { weekdayLabel, dateLabel } from '$lib/planner.js'

  // art: 'feiertag' | 'unterrichtsfrei'
  const { date, name = null, art = 'feiertag' } = $props()

  const bandClass = $derived(
    art === 'unterrichtsfrei' ? 'planner-unterrichtsfrei-band' : 'planner-ferien-band',
  )
  const fallbackLabel = $derived(art === 'unterrichtsfrei' ? 'Unterrichtsfrei' : 'Feiertag')
</script>

<div
  class="grid grid-cols-[118px_6px_1fr_230px_120px] items-center
         border-b border-light-ui-3 dark:border-dark-ui-3 {bandClass}"
>
  <!-- Termin (ohne Stundennummer) -->
  <div class="px-3 py-2.5 text-xs leading-snug font-medium">
    {weekdayLabel(date)} {dateLabel(date)}
  </div>

  <!-- Name des Sondertags statt Stundendaten -->
  <div class="col-span-4 px-3 py-2.5 text-sm font-medium">
    {name || fallbackLabel}
  </div>
</div>
