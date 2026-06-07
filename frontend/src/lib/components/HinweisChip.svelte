<script>
    /**
     * Hinweis-Badge für Curriculum-Tabellen
     * 
     * Props:
     * - typ: 'gs_bezug' | 'mint' | 'fach_bezug' | 'leitperspektive' | 'didaktik' | 'material'
     * - text: Anzeigetext
     * - fach: Fachcode (nur für fach_bezug)
     * - lp_code: Leitperspektive-Code (nur für leitperspektive)
     */
    let { typ = 'didaktik', text = '', fach = null, lp_code = null, href = null } = $props()

    // Farbzuordnung nach Typ
    const typeConfig = {
        gs_bezug: {
            prefix: 'GS',
            bg: 'bg-light-gr/20 dark:bg-dark-gr/20',
            text: 'text-light-gr dark:text-dark-gr',
            border: 'border-light-gr/30 dark:border-dark-gr/30'
        },
        mint: {
            prefix: 'MINT',
            bg: 'bg-light-bl/20 dark:bg-dark-bl/20',
            text: 'text-light-bl dark:text-dark-bl',
            border: 'border-light-bl/30 dark:border-dark-bl/30'
        },
        fach_bezug: {
            prefix: '→',
            bg: 'bg-light-ui-3/50 dark:bg-dark-ui-3/50',
            text: 'text-light-tx dark:text-dark-tx',
            border: 'border-light-ui-3/30 dark:border-dark-ui-3/30'
        },
        leitperspektive: {
            prefix: '',
            bg: 'bg-light-pur/20 dark:bg-dark-pur/20',
            text: 'text-light-pur dark:text-dark-pur',
            border: 'border-light-pur/30 dark:border-dark-pur/30'
        },
        leitperspektive_aspekt: {
            prefix: '▸',
            bg: 'bg-light-pur/20 dark:bg-dark-pur/20',
            text: 'text-light-pur dark:text-dark-pur',
            border: 'border-light-pur/30 dark:border-dark-pur/30'
        },
        didaktik: {
            prefix: '⚙',
            bg: 'bg-light-ui-3/50 dark:bg-dark-ui-3/50',
            text: 'text-light-tx dark:text-dark-tx',
            border: 'border-light-ui-3/30 dark:border-dark-ui-3/30'
        },
        material: {
            prefix: '🔗',
            bg: 'bg-light-ui-3/50 dark:bg-dark-ui-3/50',
            text: 'text-light-tx dark:text-dark-tx',
            border: 'border-light-ui-3/30 dark:border-dark-ui-3/30'
        }
    }
    
    const config = $derived(typeConfig[typ] || typeConfig.didaktik)

    // Display-Text zusammenbauen
    const displayText = $derived.by(() => {
        if (typ === 'fach_bezug' && fach) {
            return `${config.prefix} ${fach}`
        }
        if (typ === 'leitperspektive' && lp_code) {
            return lp_code
        }
        if (typ === 'leitperspektive_aspekt' && lp_code) {
            return `${config.prefix} ${lp_code}`
        }
        if (config.prefix && text) {
            return `${config.prefix} ${text}`
        }
        return text
    })
</script>

{#if href}
    <a
        {href}
        class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium
               hover:opacity-80 transition-opacity
               {config.bg} {config.text} {config.border}"
    >
        {displayText}
    </a>
{:else}
    <span
        class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium
               {config.bg} {config.text} {config.border}"
    >
        {displayText}
    </span>
{/if}
