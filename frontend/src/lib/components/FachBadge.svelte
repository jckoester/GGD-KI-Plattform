<script>
    /**
     * Das Fach eines Assistenten als Etikett in der Fachfarbe (0.27, Plan Schritt 9.2).
     *
     * Bis 0.27 kennzeichnete nur ein dünner Farbstreifen das Fach — für Schüler:innen nicht
     * eindeutig (Jan, 01.11.2026). Der Name steht jetzt da; die Farbe tönt nur den Grund
     * (`color-mix`, geht mit Hex und hsl), die Schrift bleibt neutral und damit in beiden Modi
     * lesbar. Ohne Farbe ein neutrales Etikett.
     */
    import { BADGE } from "$lib/badges.js";

    let { fach } = $props();
</script>

{#if fach?.name}
    {#if fach.color}
        <span
            class="text-xs px-1.5 py-0.5 rounded-full border text-light-tx dark:text-dark-tx"
            style="background-color: color-mix(in srgb, {fach.color} 18%, transparent); border-color: color-mix(in srgb, {fach.color} 55%, transparent)"
        >{fach.name}</span>
    {:else}
        <span class={BADGE}>{fach.name}</span>
    {/if}
{/if}
