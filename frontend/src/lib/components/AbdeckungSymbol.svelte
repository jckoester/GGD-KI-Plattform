<script>
    /**
     * Abdeckung einer Zeile in der Bilanz des Jahresverlaufsplans (BD, zweiter Durchgang; Jan
     * 25.11.2026): eingetragen (circle-check), teilweise (circle-fading-check), fehlt
     * (circle-dashed-check).
     *
     * Props: `zustand` (`voll` | `teil` | `fehlt`), `text` (Tooltip und Bildschirmleser), `size`.
     */
    import { CircleCheck, CircleDashedCheck, CircleFadingCheck } from '@lucide/svelte'

    let { zustand = 'voll', text = '', size = 14 } = $props()

    const SYMBOL = { voll: CircleCheck, teil: CircleFadingCheck, fehlt: CircleDashedCheck }
    const FARBE = {
        voll: 'text-light-gr dark:text-dark-gr',
        teil: 'text-light-or dark:text-dark-or',
        fehlt: 'text-light-re dark:text-dark-re',
    }
    const Symbol = $derived(SYMBOL[zustand] ?? CircleCheck)
</script>

<span class="inline-flex shrink-0 align-middle {FARBE[zustand]}" title={text || undefined} aria-label={text || undefined}
    role={text ? 'img' : undefined} aria-hidden={text ? undefined : 'true'}>
    <Symbol {size} />
</span>
