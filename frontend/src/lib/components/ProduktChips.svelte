<script>
    // Angehängte Produkte aus der Werkstatt (0.41, Schritt 10) — neben den Bausteinen
    // (`ContextChips`), in derselben Form, mit dem Werkstatt-Symbol. Nur die Chips; die Reihe
    // und das Einklappen übernimmt `NachrichtenChips` (0.49).
    import { Hammer, X } from "lucide-svelte";
    import { kindLabel } from "$lib/library.js";
    import { CATEGORY_COLORS } from "$lib/taxonomy.js";
    import { CHIP_AKZENT, CHIP_FORM, CHIP_ICON } from "$lib/chip_form.js";

    let { produkte = [], onremove, disabled = false } = $props();
</script>

{#each produkte as p (p.artifact_id)}
    <!-- Akzent wie die Kategorie „Material“ (`artifact`) bei den Bausteinen -->
    <span
        class="{CHIP_FORM} {CHIP_AKZENT[CATEGORY_COLORS.artifact]}"
        title="{kindLabel(p.kind)} aus deiner Werkstatt"
    >
        <Hammer size={CHIP_ICON} class="shrink-0" />
        <a href="/workshop/{p.artifact_id}" class="max-w-[200px] truncate hover:underline">{p.title}</a>
        {#if !disabled}
            <button
                type="button"
                onclick={() => onremove?.(p.artifact_id)}
                class="text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx ml-0.5"
                title="Aus dem Chat nehmen"
                aria-label="Produkt {p.title} aus dem Chat nehmen"
            >
                <X class="w-3 h-3" />
            </button>
        {/if}
    </span>
{/each}
