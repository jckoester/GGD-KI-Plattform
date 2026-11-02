<script>
    /**
     * Das Band der Vorschau (0.29, ADR-016): nicht schließbar, solange die Vorschau läuft.
     *
     * Läuft die Stunde ab, geht es von selbst zurück — sonst endete mit dem Vorschau-Token
     * auch die Sitzung der Lehrkraft (das Backend tauscht das abgelaufene Token noch einmal
     * gegen die alte Sitzung). Danach steht einmal ein Hinweis da.
     */
    import { onDestroy, onMount } from "svelte";
    import { Eye, Loader2 } from "lucide-svelte";
    import { user } from "$lib/stores/user.js";
    import { myGroups } from "$lib/stores/myGroups.js";
    import { verlasseVorschau } from "$lib/api.js";
    import InfoBanner from "./InfoBanner.svelte";
    import { HINWEIS_SCHLUESSEL, bandText, hinweisText, restMinuten } from "$lib/vorschau.js";

    const vorschau = $derived($user?.vorschau ?? null);
    const gruppenName = $derived(
        vorschau?.gruppe_id ? ($myGroups.find((g) => g.id === vorschau.gruppe_id)?.name ?? null) : null,
    );
    let jetzt = $state(Date.now());
    const minuten = $derived(vorschau ? restMinuten(vorschau.ablauf, jetzt) : null);
    let beendet = $state(false);
    let hinweis = $state(null);
    let uhr = null;
    let ablaufZeit = null;

    async function zurueck(grund) {
        if (beendet) return;
        beendet = true;
        try {
            await verlasseVorschau();
            sessionStorage.setItem(HINWEIS_SCHLUESSEL, grund);
            window.location.assign("/welcome");
        } catch {
            // Auch die Sitzung ist vorbei — dann bleibt nur die Anmeldung.
            window.location.assign("/");
        }
    }

    $effect(() => {
        clearTimeout(ablaufZeit);
        if (!vorschau) return;
        const ms = vorschau.ablauf * 1000 - Date.now();
        ablaufZeit = setTimeout(() => zurueck("abgelaufen"), Math.max(0, ms));
    });

    onMount(() => {
        uhr = setInterval(() => (jetzt = Date.now()), 30_000);
        const grund = sessionStorage.getItem(HINWEIS_SCHLUESSEL);
        if (grund) {
            hinweis = hinweisText(grund);
            sessionStorage.removeItem(HINWEIS_SCHLUESSEL);
        }
    });

    onDestroy(() => {
        clearInterval(uhr);
        clearTimeout(ablaufZeit);
    });
</script>

{#if vorschau}
    <div
        role="status"
        class="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 text-sm border-b
               bg-light-ye-bg dark:bg-dark-ye-bg border-light-ye dark:border-dark-ye
               text-light-tx dark:text-dark-tx"
    >
        <Eye class="w-4 h-4 shrink-0" />
        <span class="font-medium">{bandText(vorschau, gruppenName)}</span>
        {#if minuten != null}
            <span class="text-light-tx-2 dark:text-dark-tx-2">· noch {minuten} Min.</span>
        {/if}
        <button
            onclick={() => zurueck("beendet")}
            disabled={beendet}
            class="ml-auto px-3 py-1 rounded-lg bg-primary dark:bg-primary-dark text-white flex items-center gap-2 disabled:opacity-50"
        >
            {#if beendet}<Loader2 class="w-4 h-4 animate-spin" />{/if}
            Vorschau beenden
        </button>
    </div>
{:else if hinweis}
    <div class="px-4 pt-3 bg-light-bg-2 dark:bg-dark-bg-2 flex items-start gap-2">
        <div class="flex-1"><InfoBanner message={hinweis} /></div>
        <button
            class="text-sm text-light-tx-2 dark:text-dark-tx-2 px-2 py-1"
            onclick={() => (hinweis = null)}
            aria-label="Hinweis schließen">✕</button
        >
    </div>
{/if}
