<script>
    import { groupSlotsByWeek } from "$lib/planner.js";
    import PlannerRow from "./PlannerRow.svelte";

    const {
        slots = [],
        units = [],
        patterns = [],
        ferien = [],
        halbjahreswechsel = null,
        onPatchSlot,
        onSwapSlots,
        onEditLesson = null,
        onReview = null,
    } = $props();

    const hj2Vorlaeufig = $derived(!patterns.some((p) => p.halbjahr === 2));

    const weekItems = $derived(
        groupSlotsByWeek(slots, { ferien, halbjahreswechsel }),
    );

    function unitForId(id) {
        return id ? (units.find((u) => u.id === id) ?? null) : null;
    }

    function formatFerienRange(von, bis) {
        const fmt = (d) =>
            new Date(d + "T00:00:00").toLocaleDateString("de-DE", {
                day: "2-digit",
                month: "2-digit",
            });
        return `${fmt(von)} – ${fmt(bis)}`;
    }

    function weekRangeLabel(item) {
        if (!item.slots.length) return "";
        const first = new Date(item.slots[0].date + "T00:00:00");
        const last = new Date(item.slots.at(-1).date + "T00:00:00");
        const fmtShort = (d) =>
            d.toLocaleDateString("de-DE", { day: "numeric", month: "numeric" });
        return `${fmtShort(first)} – ${fmtShort(last)}`;
    }
</script>

{#if !slots.length}
    <div class="py-12 text-center text-sm text-light-tx-2 dark:text-dark-tx-2">
        Noch keine Slots generiert. Bitte erst ein Wochenmuster anlegen und
        Slots generieren.
    </div>
{:else}
    <!-- Spaltenheader (sticky, volle Breite) -->
    <div
        class="grid grid-cols-[118px_6px_1fr_230px_120px] sticky top-0 z-20
              border-b-2 border-light-ui-3 dark:border-dark-ui-3
              bg-light-bg dark:bg-dark-bg text-xs font-semibold uppercase tracking-wide
              text-light-tx-2 dark:text-dark-tx-2"
    >
        <div class="px-3 py-2">Termin</div>
        <div></div>
        <div class="px-3 py-2">UE / Thema</div>
        <div class="px-2 py-2">Status</div>
        <div class="px-2 py-2 text-right">Aktionen</div>
    </div>

    {#each weekItems as item (item.type === "week" ? item.key : item.type + (item.name ?? item.type))}
        {#if item.type === "week"}
            <!--
        Wochen-Wrapper: linker Balken zeigt Wochenzugehörigkeit,
        mb-3 erzeugt sichtbare Lücke zwischen Wochen.
        overflow:visible damit sticky und Dropdown-Popovers funktionieren.
      -->
            <div
                class="border-l-2 border-light-ui-3 dark:border-dark-ui-3 ml-1 mb-3"
            >
                <!-- Wochenkopf (sticky innerhalb des Scroll-Containers) -->
                <div
                    class="grid grid-cols-[118px_6px_1fr_230px_120px] sticky top-[33px] z-10
                    bg-light-bg-2 dark:bg-dark-bg-2 border-b border-light-ui-2 dark:border-dark-ui-2"
                >
                    <div
                        class="col-span-5 px-3 py-1.5 text-xs font-semibold
                      text-light-tx-2 dark:text-dark-tx-2 flex items-baseline gap-2"
                    >
                        <span class="text-light-tx dark:text-dark-tx"
                            >KW {item.week}</span
                        >
                        <span class="font-normal opacity-70"
                            >{weekRangeLabel(item)}</span
                        >
                    </div>
                </div>

                <!-- Slot-Zeilen -->
                {#each item.slots as slot (slot.id)}
                    <PlannerRow
                        {slot}
                        unit={unitForId(slot.ue_node_id)}
                        {units}
                        vorlaeufig={hj2Vorlaeufig && slot.halbjahr === 2}
                        onPatch={(updates) => onPatchSlot(slot.id, updates)}
                        onSwap={(sourceId) => onSwapSlots(sourceId, slot.id)}
                        {onEditLesson}
                        {onReview}
                    />
                {/each}
            </div>
        {:else if item.type === "ferien"}
            <!-- Ferien-Band: Farbe über CSS-Klasse (schulintern überschreibbar) -->
            <div
                class="planner-ferien-band px-3 py-2 font-medium text-sm mb-3 ml-1"
            >
                <span class="font-semibold">{item.name}</span>
                <span class="opacity-70">
                    &nbsp;&#183;&nbsp; {formatFerienRange(
                        item.von,
                        item.bis,
                    )}</span
                >
            </div>
        {:else if item.type === "halbjahr"}
            <!-- Halbjahresbruch-Band -->
            <div
                class="px-3 py-1.5 mb-3 ml-1 text-xs font-semibold
                  text-yellow-700 dark:text-yellow-200
                  bg-yellow-50 dark:bg-[color-mix(in_srgb,var(--color-yellow-300)_8%,transparent)]
                  border-y-2 border-yellow-300 dark:border-[color-mix(in_srgb,var(--color-yellow-400)_30%,transparent)]"
            >
                2. Halbjahr
            </div>
        {/if}
    {/each}
{/if}
