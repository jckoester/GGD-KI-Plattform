<script>
  import { SvelteFlow, Controls, Background } from '@xyflow/svelte'
  import '@xyflow/svelte/dist/style.css'
  import { goto } from '$app/navigation'
  import { getNeighborhood } from '$lib/api.js'
  import { CATEGORY_LABELS } from '$lib/taxonomy.js'
  import dagre from 'dagre'

  let {
    nodeId,            // UUID des Startknotens (string)
    initialDepth = 2,  // 1 oder 2
  } = $props()

  let depth = $state(initialDepth)
  let loading = $state(false)
  let error = $state(null)

  // Filterauswahl
  const ALL_RELATIONS = [
    'requires', 'used_with', 'part_of', 'develops', 'supersedes',
    'references', 'related_to', 'follows', 'reflects_on', 'derived_from',
  ]
  const ALL_CATEGORIES = ['document', 'knowledge', 'artifact', 'concept']

  let selectedRelations = $state(new Set(ALL_RELATIONS))
  let selectedCategories = $state(new Set(ALL_CATEGORIES))

  // SvelteFlow-Daten
  let flowNodes = $state([])
  let flowEdges = $state([])

  // Farben nach Category
  const CATEGORY_COLORS = {
    document:  { bg: '#e0f2fe', border: '#0284c7', text: '#0c4a6e' },  // blau
    knowledge: { bg: '#dcfce7', border: '#16a34a', text: '#14532d' },  // gruen
    artifact:  { bg: '#fef9c3', border: '#ca8a04', text: '#713f12' },  // gelb
    concept:   { bg: '#ede9fe', border: '#7c3aed', text: '#2e1065' },  // violett
  }

  async function load() {
    if (!nodeId) return
    loading = true
    error = null
    try {
      const data = await getNeighborhood(nodeId, {
        depth,
        relation: [...selectedRelations],
        category: [...selectedCategories],
      })

      // Nodes -> SvelteFlow-Format
      flowNodes = data.nodes.map(n => ({
        id: n.id,
        type: 'default',
        position: { x: 0, y: 0 },  // wird von Layout ueberschrieben
        data: {
          label: n.title,
          category: n.category,
          contentType: n.content_type,
          isStart: n.id === nodeId,
        },
        style: buildNodeStyle(n.category, n.id === nodeId),
      }))

      // Edges -> SvelteFlow-Format
      flowEdges = data.edges.map(e => ({
        id: e.id,
        source: e.from_node_id,
        target: e.to_node_id,
        label: e.relation,
        type: 'smoothstep',
        markerEnd: { type: 'arrowclosed' },
        style: 'stroke: #94a3b8; stroke-width: 1.5',
        labelStyle: 'font-size: 10px; fill: #64748b',
      }))

      // Auto-Layout mit dagre
      applyDagreLayout()

    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  }

  function buildNodeStyle(category, isStart) {
    const colors = CATEGORY_COLORS[category] ?? { bg: '#f1f5f9', border: '#94a3b8', text: '#1e293b' }
    return [
      `background: ${colors.bg}`,
      `border: 2px solid ${colors.border}`,
      `color: ${colors.text}`,
      `border-radius: 6px`,
      `padding: 8px 12px`,
      `font-size: 13px`,
      `font-weight: ${isStart ? 700 : 400}`,
      `min-width: 120px`,
      isStart ? `box-shadow: 0 0 0 3px ${colors.border}66` : '',
    ].filter(Boolean).join('; ')
  }

  function applyDagreLayout() {
    const g = new dagre.graphlib.Graph()
    g.setDefaultEdgeLabel(() => ({}))
    g.setGraph({ rankdir: 'TB', ranksep: 80, nodesep: 60 })

    flowNodes.forEach(n => g.setNode(n.id, { width: 160, height: 50 }))
    flowEdges.forEach(e => g.setEdge(e.source, e.target))

    dagre.layout(g)

    flowNodes = flowNodes.map(n => {
      const pos = g.node(n.id)
      return { ...n, position: { x: pos.x - 80, y: pos.y - 25 } }
    })
  }

  $effect(() => {
    nodeId; depth; selectedRelations; selectedCategories
    load()
  })
</script>

<div class="flex flex-col h-full">
  <!-- Kontrollleiste -->
  <div class="flex flex-wrap gap-3 px-4 py-3 border-b border-light-ui-2 dark:border-dark-ui-2
              bg-light-bg-2 dark:bg-dark-bg-2 text-sm flex-shrink-0">

    <!-- Tiefe -->
    <div class="flex items-center gap-2">
      <span class="text-light-tx-2 dark:text-dark-tx-2 text-xs font-medium">Tiefe:</span>
      {#each [1, 2] as d}
        <button
          onclick={() => { depth = d }}
          class="px-2.5 py-1 rounded text-xs border transition-colors
                 {depth === d
                   ? 'bg-primary/10 dark:bg-primary-dark/10 border-primary dark:border-primary-dark text-primary dark:text-primary-dark font-medium'
                   : 'border-light-ui-3 dark:border-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2'}"
        >
          {d}
        </button>
      {/each}
    </div>

    <!-- Kategorie-Filter -->
    <div class="flex items-center gap-1 flex-wrap">
      <span class="text-light-tx-2 dark:text-dark-tx-2 text-xs font-medium mr-1">Kategorien:</span>
      {#each ALL_CATEGORIES as cat}
        <button
          onclick={() => {
            const next = new Set(selectedCategories)
            next.has(cat) ? next.delete(cat) : next.add(cat)
            selectedCategories = next
          }}
          class="px-2 py-0.5 rounded text-xs border transition-colors
                 {selectedCategories.has(cat)
                   ? 'border-primary dark:border-primary-dark bg-primary/5 dark:bg-primary-dark/5 text-light-tx dark:text-dark-tx'
                   : 'border-light-ui-3 dark:border-dark-ui-3 text-light-tx-3 dark:text-dark-tx-3'}"
        >
          {CATEGORY_LABELS[cat]}
        </button>
      {/each}
    </div>

    <!-- Knoten-Zaehler -->
    <span class="ml-auto text-xs text-light-tx-2 dark:text-dark-tx-2 self-center">
      {flowNodes.length} Knoten · {flowEdges.length} Kanten
    </span>
  </div>

  <!-- Graph-Canvas -->
  <div class="flex-1 relative">
    {#if loading}
      <div class="absolute inset-0 flex items-center justify-center bg-light-bg/80 dark:bg-dark-bg/80 z-10">
        <span class="text-sm text-light-tx-2 dark:text-dark-tx-2">Wird geladen…</span>
      </div>
    {/if}
    {#if error}
      <div class="absolute inset-0 flex items-center justify-center">
        <p class="text-sm text-light-re dark:text-dark-re">{error}</p>
      </div>
    {:else if flowNodes.length > 0}
      <SvelteFlow
        nodes={flowNodes}
        edges={flowEdges}
        fitView
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={true}
        onnodeclick={({ node }) => goto(`/knowledge/${node.id}`)}
      >
        <Controls />
        <Background />
      </SvelteFlow>
    {:else if !loading}
      <div class="flex items-center justify-center h-full">
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
          Keine verbundenen Knoten gefunden.
        </p>
      </div>
    {/if}
  </div>
</div>
