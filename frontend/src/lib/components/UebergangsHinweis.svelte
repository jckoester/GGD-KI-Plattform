<script>
    // Übergangshinweis, gekoppelt an eine Neuigkeit (0.40, F9): sichtbar, solange der Server die
    // Neuigkeit liefert (Rolle, Stufe, `bis`, nicht geschlossen); Schließen schließt die Neuigkeit.
    import { onMount } from 'svelte'
    import InfoBanner from '$lib/components/InfoBanner.svelte'
    import { getNeuigkeiten, neuigkeitGelesen } from '$lib/api.js'
    import { istOffen } from '$lib/neuigkeiten.js'

    let { neuigkeitId, message, href = null, linkLabel = undefined } = $props()
    let offen = $state(false)

    onMount(async () => {
        try {
            offen = istOffen(await getNeuigkeiten(), neuigkeitId)
        } catch {
            offen = false // ein Hinweis, kein Grund für eine Fehlermeldung
        }
    })

    async function schliessen() {
        offen = false
        try {
            await neuigkeitGelesen(neuigkeitId)
        } catch {
            // wie auf der Startseite: bewusst still, er käme höchstens wieder
        }
    }
</script>

{#if offen}
    <InfoBanner {message} {href} {linkLabel} onclose={schliessen} />
{/if}
