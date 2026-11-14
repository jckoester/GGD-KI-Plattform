<script>
    /**
     * Wiederaufruf der Einrichtung (0.43, Schritt 6) — unter „Unterricht“ und oben im Profil.
     *
     * Ein blauer Kasten ohne ×: Als einfache Textzeile wurde er übersehen (Jan, 14.11.2026). Nach
     * „später“ nennt er den Stand und setzt fort; sonst beginnt der Durchgang von vorn. Nur für
     * Rollen mit Einrichtung (F10) und außerhalb der Vorschau.
     */
    import { user } from '$lib/stores/user.js'
    import { einrichtung, oeffneEinrichtung } from '$lib/stores/einrichtung.js'
    import { einrichtungsRolle, hinweisText, hinweisZeigen } from '$lib/einrichtung.js'
    import InfoBanner from '$lib/components/InfoBanner.svelte'

    const rolle = $derived(einrichtungsRolle($user?.roles))
    const fortsetzen = $derived(hinweisZeigen($einrichtung.daten))
</script>

{#if rolle && $einrichtung.daten}
    <InfoBanner
        title="Einrichtung"
        message={fortsetzen
            ? hinweisText(rolle, $einrichtung.daten)
            : 'Erscheinungsbild, Umfang der Oberfläche, Stundenplan und Gruppen in einem Durchgang.'}
        onaction={oeffneEinrichtung}
        actionLabel={fortsetzen ? 'Fortsetzen' : 'Einrichtung durchgehen'}
    />
{/if}
