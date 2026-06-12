<script>
  import { ueColor, weekdayLabel, dateLabel, periodLabel, KATEGORIE_LABELS } from '$lib/planner.js'

  const { slot, unit, units = [], vorlaeufig = false, onPatch, onSwap } = $props()

  // Inline-Thema-Bearbeitung
  let editingThema = $state(false)
  let themaInput = $state('')

  // Popovers
  let uePicker = $state(false)
  let commentOpen = $state(false)
  let menuOpen = $state(false)
  let noteInput = $state('')

  function startEditThema() {
    themaInput = slot.thema ?? ''
    editingThema = true
  }

  function commitThema() {
    editingThema = false
    const newVal = themaInput.trim() || null
    if (newVal !== (slot.thema ?? null)) onPatch({ thema: newVal })
  }

  function openComment() {
    noteInput = slot.note ?? ''
    commentOpen = true
    menuOpen = false
    uePicker = false
  }

  function commitComment() {
    commentOpen = false
    const newVal = noteInput.trim() || null
    if (newVal !== (slot.note ?? null)) onPatch({ note: newVal })
  }

  function closeAll() {
    uePicker = false
    menuOpen = false
    commentOpen = false
  }

  // Drag & Drop
  function onDragStart(e) {
    if (slot.pinned || slot.kategorie === 'ausfall') { e.preventDefault(); return }
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', slot.id)
  }

  function onDragOver(e) {
    if (!slot.pinned) { e.preventDefault(); e.dataTransfer.dropEffect = 'move' }
  }

  function onDrop(e) {
    e.preventDefault()
    const sourceId = e.dataTransfer.getData('text/plain')
    if (sourceId && sourceId !== slot.id && !slot.pinned) onSwap(sourceId)
  }

  const KATEGORIEN = ['unterricht', 'pruefung', 'puffer', 'ausfall', 'vertretung']

  const rowBase = 'grid items-start border-b border-light-ui-3 dark:border-dark-ui-3 hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 transition-colors relative group'
  const rowCols = 'grid-cols-[118px_6px_1fr_230px_120px]'

  const rowExtra = $derived(
    slot.kategorie === 'ausfall'
      ? 'opacity-60 bg-[repeating-linear-gradient(135deg,transparent,transparent_4px,rgba(0,0,0,0.04)_4px,rgba(0,0,0,0.04)_8px)] dark:bg-[repeating-linear-gradient(135deg,transparent,transparent_4px,rgba(255,255,255,0.06)_4px,rgba(255,255,255,0.06)_8px)]'
      : slot.kategorie === 'pruefung'
        ? 'bg-red-50/60 dark:bg-red-950/20'
        : slot.kategorie === 'puffer'
          ? 'opacity-60'
          : vorlaeufig
            ? 'opacity-55'
            : ''
  )
</script>

<div
  class="{rowBase} {rowCols} {rowExtra} planner-row-{slot.id}"
  draggable={!slot.pinned && slot.kategorie !== 'ausfall'}
  ondragstart={onDragStart}
  ondragover={onDragOver}
  ondrop={onDrop}
>
  <!-- Termin -->
  <div class="px-3 py-2.5 text-xs leading-snug">
    <div class="font-medium text-light-tx dark:text-dark-tx">
      {weekdayLabel(slot.date)} {dateLabel(slot.date)}
    </div>
    <div class="text-light-tx-2 dark:text-dark-tx-2">{periodLabel(slot)}</div>
  </div>

  <!-- UE-Farbstreifen -->
  <div class="relative self-stretch">
    <div
      style="background-color: {unit ? ueColor(unit) : 'transparent'}"
      class="absolute inset-y-1 left-0 right-0 rounded-sm cursor-pointer
             {!unit ? 'bg-light-ui-3 dark:bg-dark-ui-3 opacity-0 group-hover:opacity-40' : ''}"
      onclick={(e) => { e.stopPropagation(); uePicker = !uePicker; menuOpen = false; commentOpen = false }}
      title={unit ? `UE: ${unit.title}` : 'UE zuweisen'}
    ></div>

    {#if uePicker}
      <div
        class="absolute left-2 top-0 z-50 w-52 bg-light-bg dark:bg-dark-bg border border-light-ui-3 dark:border-dark-ui-3 rounded-lg shadow-xl py-1"
        onclick={(e) => e.stopPropagation()}
      >
        <div class="px-3 py-1 text-xs font-semibold text-light-tx-2 dark:text-dark-tx-2 uppercase tracking-wide">UE zuweisen</div>
        <button
          onclick={() => { onPatch({ ue_node_id: null }); uePicker = false }}
          class="w-full text-left px-3 py-1.5 text-sm hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 text-light-tx-2 dark:text-dark-tx-2"
        >
          — keine UE
        </button>
        {#each units as u (u.id)}
          <button
            onclick={() => { onPatch({ ue_node_id: u.id }); uePicker = false }}
            class="w-full text-left px-3 py-1.5 text-sm hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 flex items-center gap-2"
          >
            <span class="w-2.5 h-2.5 rounded-full flex-shrink-0" style="background-color: {ueColor(u)}"></span>
            <span class="text-light-tx dark:text-dark-tx truncate">{u.title}</span>
          </button>
        {/each}
      </div>
    {/if}
  </div>

  <!-- Thema / Inhalt -->
  <div class="px-3 py-2.5 min-w-0">
    {#if editingThema}
      <input
        type="text"
        bind:value={themaInput}
        onblur={commitThema}
        onkeydown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); if (e.key === 'Escape') { editingThema = false } }}
        class="w-full bg-transparent border-b border-primary dark:border-primary-dark outline-none text-sm text-light-tx dark:text-dark-tx"
      />
    {:else}
      <!-- fett = stunde_node_id gesetzt; kursiv = nur thema -->
      <div
        onclick={startEditThema}
        class="cursor-text text-sm truncate leading-snug
               {slot.kategorie === 'ausfall' ? 'line-through' : ''}
               {slot.stunde_node_id
                 ? 'font-semibold text-light-tx dark:text-dark-tx'
                 : slot.thema
                   ? 'italic text-light-tx dark:text-dark-tx'
                   : 'text-light-tx-2 dark:text-dark-tx-2 italic'}"
        title={slot.thema ?? ''}
      >
        {slot.thema || (unit ? unit.title : 'Thema eingeben …')}
      </div>
    {/if}
    {#if slot.note}
      <div class="text-xs text-light-tx-2 dark:text-dark-tx-2 truncate mt-0.5">
        <span class="text-light-bl dark:text-dark-bl">&#9679;</span> {slot.note}
      </div>
    {/if}
  </div>

  <!-- Status-Badges -->
  <div class="px-2 py-2.5 flex flex-wrap gap-1 items-start">
    {#if slot.pinned}
      <span class="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium
                   bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
        Fixpunkt
      </span>
    {/if}
    {#if slot.nachbereitet_at}
      <span class="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium
                   bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300">
        nachbereitet
      </span>
    {/if}
    {#if slot.anpassung_noetig}
      <span class="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium
                   bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300">
        Anpassung
      </span>
    {/if}
    {#if vorlaeufig}
      <span class="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium
                   bg-light-ui-2 text-light-tx-2 dark:bg-dark-ui-2 dark:text-dark-tx-2">
        vorläufig
      </span>
    {/if}
    {#if slot.kategorie !== 'unterricht'}
      <span class="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium
                   bg-light-ui-2 text-light-tx-2 dark:bg-dark-ui-2 dark:text-dark-tx-2">
        {KATEGORIE_LABELS[slot.kategorie] ?? slot.kategorie}
      </span>
    {/if}
  </div>

  <!-- Aktionen -->
  <div class="px-2 py-2 flex items-center gap-0.5 justify-end">
    <!-- Pin -->
    <button
      onclick={(e) => { e.stopPropagation(); onPatch({ pinned: !slot.pinned }) }}
      title={slot.pinned ? 'Fixpunkt aufheben' : 'Als Fixpunkt markieren'}
      class="p-1.5 rounded hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
             {slot.pinned ? 'text-amber-500' : 'text-light-tx-2 dark:text-dark-tx-2 opacity-0 group-hover:opacity-100'}"
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
           fill={slot.pinned ? 'currentColor' : 'none'} stroke="currentColor" stroke-width="2"
           stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 2L8 6H4v4l2.5 2.5L3 16h4l1-3 4 4 4-4 1 3h4l-3.5-3.5L20 10V6h-4L12 2z"/>
      </svg>
    </button>

    <!-- Kommentar -->
    <button
      onclick={(e) => { e.stopPropagation(); openComment() }}
      title="Notiz"
      class="p-1.5 rounded hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
             {slot.note ? 'text-light-bl dark:text-dark-bl' : 'text-light-tx-2 dark:text-dark-tx-2 opacity-0 group-hover:opacity-100'}"
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
           fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
      </svg>
    </button>

    <!-- Menü -->
    <div class="relative">
      <button
        onclick={(e) => { e.stopPropagation(); menuOpen = !menuOpen; uePicker = false; commentOpen = false }}
        class="p-1.5 rounded hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
               text-light-tx-2 dark:text-dark-tx-2 opacity-0 group-hover:opacity-100
               {menuOpen ? 'opacity-100' : ''}"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
             fill="currentColor">
          <circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/>
        </svg>
      </button>

      {#if menuOpen}
        <div
          class="absolute right-0 top-full mt-1 z-50 w-48 bg-light-bg dark:bg-dark-bg border border-light-ui-3 dark:border-dark-ui-3 rounded-lg shadow-xl py-1"
          onclick={(e) => e.stopPropagation()}
        >
          <div class="px-3 py-1 text-xs font-semibold text-light-tx-2 dark:text-dark-tx-2 uppercase tracking-wide">Kategorie</div>
          {#each KATEGORIEN as kat}
            <button
              onclick={() => { onPatch({ kategorie: kat }); menuOpen = false }}
              class="w-full text-left px-3 py-1.5 text-sm hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 transition-colors
                     {slot.kategorie === kat ? 'text-light-bl dark:text-dark-bl font-medium' : 'text-light-tx dark:text-dark-tx'}"
            >
              {KATEGORIE_LABELS[kat] ?? kat}
            </button>
          {/each}
          <div class="border-t border-light-ui-3 dark:border-dark-ui-3 my-1"></div>
          {#if slot.ue_node_id}
            <button
              onclick={() => { onPatch({ ue_node_id: null }); menuOpen = false }}
              class="w-full text-left px-3 py-1.5 text-sm hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 transition-colors text-light-tx dark:text-dark-tx"
            >
              UE-Zuweisung aufheben
            </button>
          {/if}
          {#if slot.stunde_node_id}
            <button
              onclick={() => { onPatch({ stunde_node_id: null }); menuOpen = false }}
              class="w-full text-left px-3 py-1.5 text-sm hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 transition-colors text-light-tx dark:text-dark-tx"
            >
              Stunden-Verknüpfung lösen
            </button>
          {/if}
          <button
            onclick={() => { onPatch({ anpassung_noetig: !slot.anpassung_noetig }); menuOpen = false }}
            class="w-full text-left px-3 py-1.5 text-sm hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 transition-colors text-light-tx dark:text-dark-tx"
          >
            {slot.anpassung_noetig ? 'Anpassung als erledigt markieren' : 'Anpassung nötig'}
          </button>
        </div>
      {/if}
    </div>
  </div>
</div>

{#if commentOpen}
  <div
    class="grid grid-cols-[118px_6px_1fr_230px_120px] border-b border-light-ui-3 dark:border-dark-ui-3 bg-light-bg-2/50 dark:bg-dark-bg-2/50 planner-row-{slot.id}"
    onclick={(e) => e.stopPropagation()}
  >
    <div class="col-span-5 px-4 py-2.5">
      <textarea
        bind:value={noteInput}
        rows="2"
        placeholder="Notiz zu diesem Termin …"
        class="w-full text-sm bg-light-bg dark:bg-dark-bg border border-light-ui-3 dark:border-dark-ui-3 rounded-md px-2.5 py-1.5 resize-none
               text-light-tx dark:text-dark-tx outline-none focus:border-primary dark:focus:border-primary-dark transition-colors"
      ></textarea>
      <div class="flex gap-3 mt-1.5 justify-end">
        <button
          onclick={() => { commentOpen = false }}
          class="text-xs text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx"
        >Abbrechen</button>
        <button
          onclick={commitComment}
          class="text-xs font-medium text-light-bl dark:text-dark-bl hover:opacity-80"
        >Speichern</button>
      </div>
    </div>
  </div>
{/if}
