<script>
    /**
     * Der Weg zurück (0.48, Päckchen N, F3 a / G1).
     *
     * Ein Link mit festem Ziel: vorhersagbar, beim Überfahren lesbar, auch in einem neuen Tab
     * richtig. Bis 0.47 gingen 18 Seiten per `history.back()` zurück. Das führte dorthin, wo man
     * vorher war: in einem neuen Tab nirgends hin, nach einem Seitenleisten-Klick auf eine
     * fremde Seite.
     *
     * - `label` nennt das Ziel („Einstellungen“, „Bibliothek“); ohne steht „Zurück“.
     * - `schliessen`: × und „Schließen“ statt Pfeil, für Seiten aus dem Nutzermenü (Profil,
     *   Unterricht), die keine Elternseite haben.
     * - `echt`: Hat dieser Tab vorher eine Seite der Plattform gezeigt, geht der Klick per
     *   `history.back()` dorthin, über beliebig viele Schritte. Sonst gilt der Link. Nur dort,
     *   wo man von Seite zu Seite derselben Art geht (Baustein zu Baustein, Jan 18.11.2026).
     */
    import { afterNavigate } from '$app/navigation';
    import { ArrowLeft, X } from 'lucide-svelte';

    let { href, label = undefined, schliessen = false, echt = false } = $props();

    // SvelteKit meldet beim Einhängen die Navigation, die hierher geführt hat; `from` fehlt,
    // wenn die Seite frisch geladen wurde (neuer Tab, Lesezeichen, Neuladen).
    let vorgaenger = $state(false);
    afterNavigate(({ from }) => {
        vorgaenger = Boolean(from);
    });

    function klick(e) {
        if (!echt || !vorgaenger) return;
        if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        history.back();
    }
</script>

<a
    {href}
    onclick={klick}
    class="inline-flex items-center gap-1 mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2
           hover:text-light-tx dark:hover:text-dark-tx transition-colors"
>
    {#if schliessen}
        <X class="w-4 h-4" /> {label ?? 'Schließen'}
    {:else}
        <ArrowLeft class="w-4 h-4" /> {label ?? 'Zurück'}
    {/if}
</a>
