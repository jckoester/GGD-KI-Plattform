<script>
    /**
     * PK-Selektor-Komponente für den Curriculum-Editor
     * 
     * Props:
     * - subjectId: ID des Fachs (zum Laden der PK-Kompetenzknoten)
     * - selected: Array der aktuell ausgewählten PKs [{node_id, title, pk_id}]
     * - onchange: Callback bei Änderung (newSelectedArray)
     */

    import { X, Search, Check, ChevronDown, ChevronRight } from 'lucide-svelte'
    
    let { subjectId = null, bpVersion = null, selected = $bindable([]), onchange = () => {} } = $props()

    let pkGruppen = $state([])
    let loadingGruppen = $state(false)
    let expandedGruppe = $state(null)
    let searchQuery = $state('')
    let filteredPkList = $state([])
    let showDropdown = $state(false)

    // Lade PK-Gruppen und -Kompetenzknoten
    $effect(() => {
        if (!subjectId) return

        async function loadPkData() {
            loadingGruppen = true
            try {
                // PK-Gruppen laden (content_type = 'pk_gruppe')
                const paramsGruppen = new URLSearchParams()
                paramsGruppen.append('content_type', 'pk_gruppe')
                paramsGruppen.set('subject_id', subjectId)
                if (bpVersion) paramsGruppen.set('bp_version', bpVersion)
                paramsGruppen.set('limit', '100')

                const gruppenRes = await fetch(`/api/context/nodes?${paramsGruppen}`, { credentials: 'include' })
                const gruppenData = gruppenRes.ok ? await gruppenRes.json() : []

                // PK-Kompetenzknoten laden
                const paramsKompetenzen = new URLSearchParams()
                paramsKompetenzen.append('content_type', 'pk_kompetenz')
                paramsKompetenzen.set('subject_id', subjectId)
                if (bpVersion) paramsKompetenzen.set('bp_version', bpVersion)
                paramsKompetenzen.set('limit', '200')
                
                const kompetenzRes = await fetch(`/api/context/nodes?${paramsKompetenzen}`, { credentials: 'include' })
                const kompetenzData = kompetenzRes.ok ? await kompetenzRes.json() : []
                
                // Gruppen strukturieren
                const gruppenMap = new Map()
                gruppenData.forEach(g => {
                    gruppenMap.set(g.id, {
                        ...g,
                        kompetenzen: []
                    })
                })
                
                // Kompetenzen den Gruppen zuordnen (über metadata oder Titel)
                kompetenzData.forEach(k => {
                    // Versuche Gruppe aus metadata zu extrahieren
                    const gruppeId = k.metadata?.pk_gruppe_id
                    if (gruppeId && gruppenMap.has(gruppeId)) {
                        gruppenMap.get(gruppeId).kompetenzen.push(k)
                    }
                })
                
                // Als Array für die Anzeige
                pkGruppen = Array.from(gruppenMap.values())
                
            } catch (e) {
                console.error('Fehler beim Laden der PK-Daten:', e)
            } finally {
                loadingGruppen = false
            }
        }
        
        loadPkData()
    })
    
    // Filter PKs basierend auf Suche
    $effect(() => {
        if (!searchQuery.trim()) {
            filteredPkList = []
            return
        }
        
        // Durchsuche alle PK-Kompetenzknoten
        const allPks = pkGruppen.flatMap(g => g.kompetenzen)
        const matches = allPks.filter(pk => 
            pk.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
            extractPkIdFromTitle(pk.title).toLowerCase().includes(searchQuery.toLowerCase())
        )
        filteredPkList = matches
    })
    
    // Extrahiere PK-ID aus Titel (z.B. "PK_05.1" aus "PK 05.1 - Prozessbezogene Kompetenz")
    function extractPkIdFromTitle(title) {
        const match = title.match(/(PK[\-_]?\d+\.\d+)/i)
        return match ? match[1].replace('-', '_').replace('.', '_') : title
    }
    
    // PK auswählen
    function selectPK(pkNode) {
        const alreadySelected = selected.some(s => s.node_id === pkNode.id)
        if (!alreadySelected) {
            selected = [...selected, {
                node_id: pkNode.id,
                title: pkNode.title,
                pk_id: extractPkIdFromTitle(pkNode.title)
            }]
            emitChange()
        }
        searchQuery = ''
        showDropdown = false
    }
    
    // PK entfernen
    function removePK(pk_id) {
        selected = selected.filter(s => s.pk_id !== pk_id)
        emitChange()
    }
    
    // Gruppe expandieren/collapsen
    function toggleGruppe(gruppeId) {
        expandedGruppe = expandedGruppe === gruppeId ? null : gruppeId
    }
    
    // Change-Event auslösen
    function emitChange() {
        onchange(selected)
    }
    
    // Füge PK per Direkteingabe hinzu
    function addById() {
        if (!searchQuery.trim()) return
        
        const pkId = searchQuery.trim().replace('PK', '').replace('_', '.')
        
        // Prüfe ob bereits ausgewählt
        const alreadySelected = selected.some(s => s.pk_id === pkId)
        if (alreadySelected) {
            searchQuery = ''
            showDropdown = false
            return
        }
        
        // Prüfe ob wir den Knoten in den Gruppen haben
        const found = pkGruppen.flatMap(g => g.kompetenzen).find(pk => 
            extractPkIdFromTitle(pk.title) === pkId || pk.title.includes(pkId)
        )
        
        if (found) {
            selectPK(found)
        } else {
            // Nicht gefunden - trotzdem hinzufügen
            selected = [...selected, {
                node_id: null,
                title: `Unbekannte PK: ${pkId}`,
                pk_id: pkId
            }]
            emitChange()
            searchQuery = ''
            showDropdown = false
        }
    }
    
    // Blur-Handler
    function handleBlur() {
        setTimeout(() => {
            showDropdown = false
        }, 200)
    }
</script>

<div class="space-y-2">
    <!-- Ausgewählte PKs -->
    {#if selected.length > 0}
        <div class="flex flex-wrap gap-2">
            {#each selected as pk}
                <div class="flex items-center gap-1 px-2 py-1 rounded-full bg-light-gr/20 dark:bg-dark-gr/20">
                    <span class="text-sm text-light-tx dark:text-dark-tx">
                        {pk.pk_id}
                    </span>
                    {#if !pk.node_id}
                        <span class="text-xs text-light-ye dark:text-dark-ye" title="Nicht in Datenbank gefunden">
                            ⚠
                        </span>
                    {/if}
                    <button
                        onclick={() => removePK(pk.pk_id)}
                        class="text-light-re dark:text-dark-re hover:text-light-re/80"
                        title="Entfernen"
                    >
                        <X class="w-3 h-3" />
                    </button>
                </div>
            {/each}
        </div>
    {/if}
    
    <!-- Suchfeld mit Hierarchie-Auswahl -->
    <div class="relative">
        <div class="relative">
            <Search class="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-light-tx-2 dark:text-dark-tx-2" />
            <input
                type="text"
                bind:value={searchQuery}
                onfocus={() => showDropdown = true}
                onblur={handleBlur}
                onkeydown={(e) => {
                    if (e.key === 'Enter') {
                        e.preventDefault()
                        addById()
                    }
                }}
                placeholder="PK-ID suchen (z.B. PK_05.1)"
                class="w-full pl-8 pr-10 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                       focus:outline-none focus:border-primary dark:focus:border-primary-dark"
            />
        </div>
        
        <!-- Dropdown mit PK-Hierarchie oder Suchergebnissen -->
        {#if showDropdown}
            <div class="absolute top-full left-0 right-0 mt-1 z-50 bg-white dark:bg-dark-bg-2 
                        border border-light-ui-3 dark:border-dark-ui-3 rounded-md shadow-lg max-h-80 overflow-y-auto">
                
                {#if searchQuery.trim() && filteredPkList.length > 0}
                    <!-- Suchergebnisse -->
                    {#each filteredPkList as pk (pk.id)}
                        <button
                            onclick={() => selectPK(pk)}
                            class="w-full px-3 py-2 text-left text-sm hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 
                                   flex items-center gap-2 transition-colors"
                        >
                            <div class="w-4 h-4 rounded-full border border-light-ui-3 dark:border-dark-ui-3 flex items-center justify-center">
                                {#if selected.some(s => s.node_id === pk.id)}
                                    <Check class="w-3 h-3 text-primary dark:text-primary-dark" />
                                {/if}
                            </div>
                            <div class="min-w-0 flex-1">
                                <div class="font-medium text-light-tx dark:text-dark-tx">
                                    {pk.title}
                                </div>
                                <div class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                                    {extractPkIdFromTitle(pk.title)}
                                </div>
                            </div>
                        </button>
                    {/each}
                {:else if loadingGruppen}
                    <div class="p-3 text-sm text-light-tx-2 dark:text-dark-tx-2">
                        Wird geladen…
                    </div>
                {:else if pkGruppen.length === 0}
                    <div class="p-3 text-sm text-light-tx-2 dark:text-dark-tx-2">
                        Keine PK-Gruppen gefunden.
                    </div>
                {:else}
                    <!-- PK-Gruppen Hierarchie -->
                    {#each pkGruppen as gruppe (gruppe.id)}
                        <div class="border-b border-light-ui-3 dark:border-dark-ui-3 last:border-0">
                            <button
                                onclick={() => toggleGruppe(gruppe.id)}
                                class="w-full px-3 py-2 text-left text-sm hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 
                                       flex items-center justify-between transition-colors"
                            >
                                <span class="font-medium text-light-tx dark:text-dark-tx">
                                    {gruppe.title}
                                </span>
                                {#if expandedGruppe === gruppe.id}
                                    <ChevronDown class="w-4 h-4 text-light-tx-2 dark:text-dark-tx-2" />
                                {:else}
                                    <ChevronRight class="w-4 h-4 text-light-tx-2 dark:text-dark-tx-2" />
                                {/if}
                            </button>
                            
                            {#if expandedGruppe === gruppe.id && gruppe.kompetenzen.length > 0}
                                {#each gruppe.kompetenzen as pk (pk.id)}
                                    <button
                                        onclick={() => selectPK(pk)}
                                        class="w-full px-3 py-1.5 text-left text-sm hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 
                                               flex items-center gap-2 transition-colors ml-4"
                                    >
                                        <div class="w-4 h-4 rounded-full border border-light-ui-3 dark:border-dark-ui-3 flex items-center justify-center">
                                            {#if selected.some(s => s.node_id === pk.id)}
                                                <Check class="w-3 h-3 text-primary dark:text-primary-dark" />
                                            {/if}
                                        </div>
                                        <div class="min-w-0 flex-1">
                                            <div class="text-light-tx dark:text-dark-tx">
                                                {pk.title}
                                            </div>
                                            <div class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                                                {extractPkIdFromTitle(pk.title)}
                                            </div>
                                        </div>
                                    </button>
                                {/each}
                            {/if}
                        </div>
                    {/each}
                {/if}
            </div>
        {/if}
    </div>
</div>
