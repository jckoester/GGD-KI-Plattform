<script>
    /**
     * Abdeckung einer Zeile in der Bilanz des Jahresverlaufsplans (BD, zweiter Durchgang; Jan
     * 25.11.2026): eingetragen (circle-check), teilweise (circle-fading-check), fehlt
     * (circle-dashed-check).
     *
     * Die Pfade stammen aus Lucide (https://lucide.dev, ISC-Lizenz), `@lucide/svelte` 1.80.0.
     * Das Projekt nutzt noch `lucide-svelte` 1.0.1, das bei dieser Fassung stehen geblieben ist
     * und die beiden gestrichelten Formen nicht kennt — deshalb hier eingebettet statt importiert.
     *
     * Props: `zustand` (`voll` | `teil` | `fehlt`), `text` (Tooltip und Bildschirmleser), `size`.
     */
    let { zustand = 'voll', text = '', size = 14 } = $props()

    const PFADE = {
        voll: ['M9 12l2 2 4-4'],
        teil: ['M12 2a10 10 0 017.38 16.75', 'm16 9-5.5 5.5L8 12', 'M2.5 8.875a10 10 0 00-.5 3',
            'M2.83 16a10 10 0 002.43 3.4', 'M4.636 5.235a10 10 0 01.891-.857', 'M8.644 21.42a10 10 0 007.631-.38'],
        fehlt: ['M10.1 2.182a10 10 0 013.8 0', 'M13.9 21.818a10 10 0 01-3.8 0', 'm16 9-5.5 5.5L8 12',
            'M17.609 3.721a10 10 0 012.69 2.7', 'M2.182 13.9a10 10 0 010-3.8', 'M20.279 17.609a10 10 0 01-2.7 2.69',
            'M21.818 10.1a10 10 0 010 3.8', 'M3.721 6.391a10 10 0 012.7-2.69', 'M6.391 20.279a10 10 0 01-2.69-2.7'],
    }
    const FARBE = {
        voll: 'text-light-gr dark:text-dark-gr',
        teil: 'text-light-or dark:text-dark-or',
        fehlt: 'text-light-re dark:text-dark-re',
    }
</script>

<span class="inline-flex shrink-0 align-middle {FARBE[zustand]}" title={text || undefined} aria-label={text || undefined}
    role={text ? 'img' : undefined} aria-hidden={text ? undefined : 'true'}>
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none"
        stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        {#if zustand === 'voll'}<circle cx="12" cy="12" r="10" />{/if}
        {#each PFADE[zustand] as d (d)}<path {d} />{/each}
    </svg>
</span>
