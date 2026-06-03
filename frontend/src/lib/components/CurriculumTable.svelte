<script>
    import HinweisChip from './HinweisChip.svelte'

    export let curriculum = null
    export let editMode = false
    
    /**
     * Hilfsfunktion: Finde IK-Referenz-Objekt für gegebene IK-Nummer
     */
    function findIkRef(ikRefs, ikNr) {
        if (!ikNr) return null
        return ikRefs?.find(ref => ref.title === ikNr || ref.node_id?.endsWith(ikNr)) || null
    }
    
    /**
     * Hilfsfunktion: Finde PK-Referenz-Objekt für gegebene PK-ID
     */
    function findPkRef(pkRefs, pkId) {
        if (!pkId) return null
        return pkRefs?.find(ref => ref.title === pkId || ref.node_id?.endsWith(pkId)) || null
    }
    
    /**
     * Hilfsfunktion: Erzeuge Link zu einem Knoten
     */
    function nodeLink(nodeId) {
        return `/knowledge/${nodeId}`
    }
    
    /**
     * Hilfsfunktion: Parse und extrahiere Hinweise aus Text
     * Erkennt Muster wie [GS], [MINT], [→BNT], (L) BTV, etc.
     */
    function parseHinweise(hinweiseText) {
        if (!hinweiseText) return []
        
        const hints = []
        const text = hinweiseText.toString()
        
        // MINT-Hinweis
        if (text.includes('[MINT]') || text.includes('MINT')) {
            hints.push({ typ: 'mint', text: '' })
        }
        
        // GS-Bezug
        if (text.includes('[GS]') || text.includes('GS-Bezug')) {
            hints.push({ typ: 'gs_bezug', text: '' })
        }
        
        // Leitperspektiven: L BO, (L) BTV, etc.
        const lpPattern = /\(?L\)?\s*([A-Z]{2,4})/g
        let lpMatch
        while ((lpMatch = lpPattern.exec(text)) !== null) {
            hints.push({ typ: 'leitperspektive', lp_code: lpMatch[1] })
        }
        
        // Fachbezug: →BNT, (F) ETH 3.1.1.1, BNT: ...
        const fachPattern = /\(F\)\s*([A-Z]+)|→([A-Z]+)|([A-Z]+):/g
        let fachMatch
        while ((fachMatch = fachPattern.exec(text)) !== null) {
            const fachCode = fachMatch[1] || fachMatch[2] || fachMatch[3]
            if (fachCode) {
                hints.push({ typ: 'fach_bezug', fach: fachCode })
            }
        }
        
        return hints
    }
    
    /**
     * Hilfsfunktion: Extrahiere IK-Nummern aus String
     * Erkennt Muster wie "3.1.1" oder "IK 3.1.1"
     */
    function extractIkNumbers(ikText) {
        if (!ikText) return []
        const text = ikText.toString()
        // Muster: IK gefolt von Nummer, oder nur die Nummer
        const matches = text.match(/IK\s+([\d.]+)|([\d.]+)/g) || []
        return matches.map(m => {
            const clean = m.replace('IK', '').trim()
            return { nr: clean, partiell: clean.includes('[') }
        })
    }
    
    /**
     * Hilfsfunktion: Extrahiere PK-IDs aus Array oder String
     */
    function extractPkIds(pkData) {
        if (!pkData) return []
        if (typeof pkData === 'string') return [pkData]
        if (Array.isArray(pkData)) {
            return pkData.map(pk => typeof pk === 'string' ? pk : pk.id || pk)
        }
        return [pkData.id || pkData]
    }
</script>

<div class="overflow-x-auto">
    <table class="w-full text-left border-collapse text-sm">
        <thead>
            <tr class="border-b border-light-ui-3 dark:border-dark-ui-3">
                <th class="px-3 py-2 font-medium text-light-tx-2 dark:text-dark-tx-2 w-1/6">
                    Prozessbezogene Kompetenzen
                </th>
                <th class="px-3 py-2 font-medium text-light-tx-2 dark:text-dark-tx-2 w-1/6">
                    Inhaltsbezogene Kompetenzen
                </th>
                <th class="px-3 py-2 font-medium text-light-tx-2 dark:text-dark-tx-2 w-1/3">
                    Konkretisierung
                </th>
                <th class="px-3 py-2 font-medium text-light-tx-2 dark:text-dark-tx-2 w-1/3">
                    Hinweise
                </th>
            </tr>
        </thead>
        <tbody>
            {#each curriculum?.kapitel || [] as kap (kap.id)}
                <!-- Kapitel-Kopfzeile -->
                <tr class="bg-light-bg-2 dark:bg-dark-bg-2">
                    <td 
                        colspan="4" 
                        class="px-3 py-3 font-bold text-light-tx dark:text-dark-tx border-b border-light-ui-3 dark:border-dark-ui-3"
                    >
                        {kap.title}
                        {#if kap.metadata?.std}
                            <span class="ml-2 text-light-tx-2 dark:text-dark-tx-2 text-xs">
                                ({kap.metadata.std} Stunden)
                            </span>
                        {/if}
                    </td>
                </tr>
                
                <!-- Kapitel-Einleitung -->
                {#if kap.metadata?.einleitung}
                    <tr class="bg-light-bg-2 dark:bg-dark-bg-2">
                        <td 
                            colspan="4" 
                            class="px-3 py-2 text-sm text-light-tx-2 dark:text-dark-tx-2 italic border-b border-light-ui-3 dark:border-dark-ui-3"
                        >
                            {kap.metadata.einleitung}
                        </td>
                    </tr>
                {/if}
                
                <!-- Lernsequenzen -->
                {#each kap.lernsequenzen || [] as ls (ls.id)}
                    <!-- Lernsequenz-Titel (Subheader) -->
                    {#if ls.title}
                        <tr class="bg-light-bg-2 dark:bg-dark-bg-2">
                            <td 
                                colspan="4" 
                                class="px-3 py-2 font-semibold text-light-tx dark:text-dark-tx border-b border-light-ui-3 dark:border-dark-ui-3"
                            >
                                {ls.title}
                                {#if ls.metadata?.bp_leitidee}
                                    <span class="ml-2 text-light-tx-2 dark:text-dark-tx-2 text-xs">
                                        (Leitidee: {ls.metadata.bp_leitidee})
                                    </span>
                                {/if}
                            </td>
                        </tr>
                    {/if}
                    
                    <!-- Einträge der Lernsequenz -->
                    {#each ls.metadata?.eintraege || [] as eintrag, i (i)}
                        <tr 
                            class="border-b border-light-ui-3 dark:border-dark-ui-3 
                                   {i % 2 === 0 ? 'bg-white dark:bg-transparent' : 'bg-light-bg-2/50 dark:bg-dark-bg-2/50'}"
                        >
                            <!-- PK-Spalte (nur bei erstem Eintrag mit rowspan) -->
                            {#if i === 0}
                                <td 
                                    rowspan={(ls.metadata?.eintraege || []).length} 
                                    class="px-3 py-2 vertical-align-top"
                                >
                                    {#each extractPkIds(eintrag.pk) as pkId}
                                        {#if findPkRef(ls.pk_refs, pkId)}
                                            <a 
                                                href={nodeLink(findPkRef(ls.pk_refs, pkId).node_id)}
                                                class="block mb-1 text-light-bl dark:text-dark-bl underline hover:text-primary dark:hover:text-primary-dark"
                                            >
                                                {pkId}
                                            </a>
                                        {:else}
                                            <span class="block mb-1 text-light-tx-2 dark:text-dark-tx-2">{pkId}</span>
                                        {/if}
                                    {/each}
                                </td>
                            {/if}
                            
                            <!-- IK-Spalte -->
                            <td class="px-3 py-2 vertical-align-top">
                                {#each extractIkNumbers(eintrag.ik) as ik}
                                    {#if findIkRef(ls.ik_refs, ik.nr)}
                                        <a 
                                            href={nodeLink(findIkRef(ls.ik_refs, ik.nr).node_id)}
                                            class="inline-block mr-1 text-light-bl dark:text-dark-bl underline hover:text-primary dark:hover:text-primary-dark"
                                        >
                                            {ik.nr}
                                        </a>
                                        {#if ik.partiell}
                                            <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">[…]</span>
                                        {/if}
                                    {:else}
                                        <span class="inline-block mr-1 text-light-tx dark:text-dark-tx">{ik.nr}</span>
                                        {#if ik.partiell}
                                            <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">[…]</span>
                                        {/if}
                                    {/if}
                                {/each}
                            </td>
                            
                            <!-- Konkretisierung -->
                            <td class="px-3 py-2 vertical-align-top">
                                {#if eintrag.konkretisierung}
                                    {@html eintrag.konkretisierung.replace(/\n/g, '<br>')}
                                {/if}
                            </td>
                            
                            <!-- Hinweise -->
                            <td class="px-3 py-2 vertical-align-top">
                                {#if eintrag.hinweise}
                                    <div class="space-y-1">
                                        <!-- Parse Hinweise und zeige als Chips -->
                                        {#each parseHinweise(eintrag.hinweise) as hinweis}
                                            <HinweisChip 
                                                typ={hinweis.typ} 
                                                text={hinweis.text}
                                                fach={hinweis.fach}
                                                lp_code={hinweis.lp_code}
                                            />
                                        {/each}
                                        <!-- Originaltext falls nicht alle Muster erkannt wurden -->
                                        {#if eintrag.hinweise && parseHinweise(eintrag.hinweise).length === 0}
                                            <span class="text-light-tx-2 dark:text-dark-tx-2">{eintrag.hinweise}</span>
                                        {/if}
                                    </div>
                                {:else}
                                    <span class="text-light-tx-3 dark:text-dark-tx-3 text-xs">–</span>
                                {/if}
                            </td>
                        </tr>
                    {/each}
                {/each}
            {/each}
        </tbody>
    </table>
</div>

<style>
    /* Vertikale Ausrichtung für Tabellenzellen */
    .vertical-align-top {
        vertical-align: top;
    }
</style>
