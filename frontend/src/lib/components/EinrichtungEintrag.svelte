<script>
    /**
     * Wiederaufruf der Einrichtung (0.43, Schritt 6) — unter „Unterricht“ und im Profil.
     * Erscheint nur für Rollen mit Einrichtung (F10) und außerhalb der Vorschau; öffnet den
     * Dialog mit dem gespeicherten Stand (nach „später“ dort, sonst von vorn).
     */
    import { user } from '$lib/stores/user.js'
    import { einrichtung, oeffneEinrichtung } from '$lib/stores/einrichtung.js'
    import { einrichtungsRolle } from '$lib/einrichtung.js'

    const sichtbar = $derived(Boolean(einrichtungsRolle($user?.roles) && $einrichtung.daten))
</script>

{#if sichtbar}
    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
        Erscheinungsbild, Umfang der Oberfläche, Stundenplan und Gruppen in einem Durchgang:
        <button type="button" onclick={oeffneEinrichtung}
                class="text-light-bl dark:text-dark-bl hover:underline">Einrichtung durchgehen</button>
    </p>
{/if}
