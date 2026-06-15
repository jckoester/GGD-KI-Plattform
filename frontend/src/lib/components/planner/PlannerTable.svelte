<script>
    import { tick } from "svelte";
    import { groupSlotsByWeek, isoWeek } from "$lib/planner.js";
    import PlannerRow from "./PlannerRow.svelte";
    import SpecialDayRow from "./SpecialDayRow.svelte";

    const {
        slots = [],
        units = [],
        patterns = [],
        ferien = [],
        feiertage = [],
        unterrichtsfreie = [],
        halbjahreswechsel = null,
        beginn = null,
        ende = null,
        onPatchSlot,
        onSwapSlots,
        onEditLesson = null,
        onReview = null,
    } = $props();

    const hj2Vorlaeufig = $derived(!patterns.some((p) => p.halbjahr === 2));

    const weekItems = $derived(
        groupSlotsByWeek(slots, {
            ferien,
            feiertage,
            unterrichtsfreie,
            halbjahreswechsel,
            beginn,
            ende,
        }),
    );

    // Beim ersten Aufbau einmalig zur aktuellen (bzw. nächsten Schul-)Woche scrollen.
    let didScroll = false;
    let headerEl = $state(null); // Sticky-Spaltenheader, dessen Höhe beim Scrollen abgezogen wird

    function currentWeekKey() {
        const now = new Date();
        const ds = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
        const { week, year } = isoWeek(ds);
        return `${year}-W${String(week).padStart(2, "0")}`;
    }

    // Scrollt das Element so in den Scroll-Container, dass es direkt unter dem
    // Sticky-Spaltenheader sitzt. `extraOffset` zieht zusätzliche Sticky-Höhe ab
    // (z.B. den Wochenkopf, der beim Sprung auf eine einzelne Slot-Zeile darüber liegt).
    function scrollToEl(el, behavior = "auto", extraOffset = 0) {
        const container = el?.closest(".overflow-y-auto");
        if (!el || !container) return;
        const headerOffset = headerEl?.offsetHeight ?? 33;
        const delta =
            el.getBoundingClientRect().top -
            container.getBoundingClientRect().top;
        container.scrollTo({
            top: container.scrollTop + delta - headerOffset - extraOffset,
            behavior,
        });
    }

    // Von außen aufrufbar (UE-Legende): zur ersten Stunde einer UE springen —
    // erste Stunde mit Entwurf, sonst erster zugewiesener Slot.
    export function scrollToUnit(unitId) {
        const ueSlots = slots
            .filter((s) => s.ue_node_id === unitId)
            .sort((a, b) => a.date.localeCompare(b.date));
        if (!ueSlots.length) return;
        const target = ueSlots.find((s) => s.stunde_node_id) ?? ueSlots[0];
        const el = document.querySelector(`[data-slot="${target.id}"]`);
        // Zusätzlich den (sticky) Wochenkopf der Zielzeile abziehen, sonst verdeckt
        // er die obere Hälfte der Slot-Zeile.
        const weekHeader = el?.closest("[data-week]")?.firstElementChild;
        scrollToEl(el, "smooth", weekHeader?.offsetHeight ?? 0);
    }

    $effect(() => {
        if (didScroll || !weekItems.length) return;
        didScroll = true;

        const keys = weekItems.filter((i) => i.type === "week").map((i) => i.key);
        const wk = currentWeekKey();
        // Exakte Woche; sonst die nächste folgende; sonst die letzte (Schuljahr vorbei).
        const target = keys.includes(wk)
            ? wk
            : (keys.find((k) => k > wk) ?? keys.at(-1));
        if (!target) return;

        tick().then(() =>
            scrollToEl(document.querySelector(`[data-week="${target}"]`)),
        );
    });

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
        const dates = (item.rows ?? []).map((r) => r.date).sort();
        if (!dates.length) return "";
        const first = new Date(dates[0] + "T00:00:00");
        const last = new Date(dates.at(-1) + "T00:00:00");
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
        bind:this={headerEl}
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
                data-week={item.key}
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

                <!-- Slot- und Sondertag-Zeilen (chronologisch gemischt) -->
                {#each item.rows as row (row.kind === "slot" ? row.slot.id : "sp-" + row.art + "-" + row.date)}
                    {#if row.kind === "slot"}
                        <PlannerRow
                            slot={row.slot}
                            unit={unitForId(row.slot.ue_node_id)}
                            {units}
                            vorlaeufig={hj2Vorlaeufig && row.slot.halbjahr === 2}
                            onPatch={(updates) => onPatchSlot(row.slot.id, updates)}
                            onSwap={(sourceId) => onSwapSlots(sourceId, row.slot.id)}
                            {onEditLesson}
                            {onReview}
                        />
                    {:else}
                        <SpecialDayRow
                            date={row.date}
                            name={row.name}
                            art={row.art}
                        />
                    {/if}
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
