<script>
  import { page } from '$app/stores'
  import { goto } from '$app/navigation'
  import { CONTENT_TYPES, CATEGORY_LABELS, SCOPE_DEFAULTS } from '$lib/taxonomy.js'
  import { createContextNode } from '$lib/api.js'
  import { user } from '$lib/stores/user.js'
  import { myTeachingGroups } from '$lib/stores/myGroups.js'
  import { subjects } from '$lib/stores/subjects.js'

  // ── Query-Param-Defaults ────────────────────────────────────────────────
  const preGroupId = $page.url.searchParams.get('group_id')
  const preSubjectSlug = $page.url.searchParams.get('subject_slug')
  const preReadScope = $page.url.searchParams.get('read_scope') ?? 'school'

  // ── Formularfelder ──────────────────────────────────────────────────────
  let title = $state('')
  let category = $state('')
  let contentType = $state('')
  let content = $state('')
  let readScope = $state(preReadScope)
  let writeScope = $state('private')
  let readScopeGroupId = $state(preGroupId ? Number(preGroupId) : null)
  let writeScopeGroupId = $state(preGroupId ? Number(preGroupId) : null)
  let validUntil = $state('')
  let schuljahr = $state(currentSchuljahr())
  let subjectId = $state(null)
  let minGrade = $state(null)
  let maxGrade = $state(null)
  let metadata = $state('{}')

  // Validierung für Jahrgangsstufen
  const gradeError = $derived(
    minGrade && maxGrade && Number(minGrade) > Number(maxGrade)
      ? 'Von-Wert muss kleiner oder gleich Bis-Wert sein'
      : null
  )

  // Strukturierte Metadaten
  let signatur = $state({
    name: '',
    sprache: 'arduino_cpp',
    parameter: [],
    rueckgabe: { typ: '', beschreibung: '' }
  })
  let schaltzeichen = $state({
    beschreibung: '',
    norm: '',
    kennung: '',
    svg: ''
  })

  let saving = $state(false)
  let errors = $state({})

  // ── Rollen ──────────────────────────────────────────────────────────────
  const isAdmin = $derived($user?.roles?.includes('admin') ?? false)
  const isTeacher = $derived($user?.roles?.includes('teacher') ?? false)

  // ── Content-Type-Optionen je Category ──────────────────────────────────
  const contentTypeOptions = $derived(
    category ? (CONTENT_TYPES[category] ?? []) : []
  )

  // ── Scope-Defaults bei Category-/Typ-Wechsel setzen ────────────────────
  $effect(() => {
    if (!contentType) return
    const [defRead, defWrite] = SCOPE_DEFAULTS[contentType] ?? ['school', 'private']
    if (!preReadScope || preReadScope === 'school') readScope = defRead
    writeScope = defWrite
  })

  // ── Zulässige write_scope-Optionen je Rolle ─────────────────────────────
  const writeScopes = $derived.by(() => {
    const all = ['private', 'group', 'subject', 'school']
    if (isAdmin) return all
    return ['private', 'group', 'subject']
  })

  // ── Schuljahr-Hilfsfunktion ─────────────────────────────────────────────
  function currentSchuljahr() {
    const now = new Date()
    const year = now.getFullYear()
    return now.getMonth() >= 7 ? `${year}/${year + 1}` : `${year - 1}/${year}`
  }

  function schuljahresEnde() {
    const year = parseInt(schuljahr.split('/')[1] ?? new Date().getFullYear() + 1)
    return `${year}-07-31`
  }

  // ── Metadata zusammenbauen ──────────────────────────────────────────────
  function buildMetadata() {
    if (category === 'concept' && contentType === 'funktion') {
      return { signatur }
    }
    if (category === 'concept' && contentType === 'bauteil') {
      return { schaltzeichen }
    }
    try {
      return JSON.parse(metadata)
    } catch {
      return {}
    }
  }

  // ── Parameter-Manipulation ────────────────────────────────────────────
  function addParameter() {
    signatur.parameter = [...signatur.parameter, { name: '', typ: '', beschreibung: '' }]
  }

  function removeParameter(index) {
    signatur.parameter = signatur.parameter.filter((_, i) => i !== index)
  }

  function updateParameter(index, field, value) {
    signatur.parameter[index][field] = value
    signatur.parameter = [...signatur.parameter]
  }

  // ── Speichern ──────────────────────────────────────────────────────────
  async function save() {
    errors = {}
    if (!title.trim()) errors.title = 'Pflichtfeld'
    if (!category) errors.category = 'Pflichtfeld'
    if (!contentType) errors.contentType = 'Pflichtfeld'
    if (gradeError) {
      errors.grade = gradeError
      return
    }
    if (Object.keys(errors).length > 0) return

    saving = true
    try {
      const payload = {
        title: title.trim(),
        category,
        content_type: contentType,
        content: content.trim() || null,
        metadata: buildMetadata(),
        read_scope: readScope,
        write_scope: writeScope,
        read_scope_group_id: ['subject', 'group'].includes(readScope) ? readScopeGroupId : null,
        write_scope_group_id: ['subject', 'group'].includes(writeScope) ? writeScopeGroupId : null,
        valid_until: validUntil || null,
        schuljahr: schuljahr || null,
        subject_id: subjectId,
        min_grade: minGrade ? Number(minGrade) : null,
        max_grade: maxGrade ? Number(maxGrade) : null,
      }
      const created = await createContextNode(payload)
      goto(`/knowledge/${created.id}`)
    } catch (e) {
      if (e.status === 422) {
        errors.general = e.message
      } else {
        errors.general = e.message
      }
    } finally {
      saving = false
    }
  }

  // ── Group-Optionen für Selects ────────────────────────────────────────
  const groupOptions = $derived(
    $myTeachingGroups.map(g => ({ id: g.id, name: g.name, subject_id: g.subject_id }))
  )
</script>

<div class="h-full overflow-y-auto p-6 max-w-2xl">
  <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx mb-6">Neuen Knoten anlegen</h1>

  <form onsubmit={e => { e.preventDefault(); save() }} class="space-y-6">
    <!-- Titel -->
    <div>
      <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
        Titel *
      </label>
      <input
        type="text"
        bind:value={title}
        class="w-full px-3 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
               bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
               focus:outline-none focus:border-primary dark:focus:border-primary-dark"
        placeholder="z. B. Lehrplan Informatik Sek II"
      />
      {#if errors.title}
        <p class="mt-1 text-sm text-light-re dark:text-dark-re">{errors.title}</p>
      {/if}
    </div>

    <!-- Kategorie -->
    <div>
      <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
        Kategorie *
      </label>
      <select
        bind:value={category}
        onchange={() => { contentType = '' }}
        class="w-full px-3 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
               bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
      >
        <option value="">-- Bitte wählen --</option>
        {#each Object.entries(CATEGORY_LABELS) as [cat, label]}
          <option value={cat}>{label}</option>
        {/each}
      </select>
      {#if errors.category}
        <p class="mt-1 text-sm text-light-re dark:text-dark-re">{errors.category}</p>
      {/if}
    </div>

    <!-- Typ -->
    {#if category}
      <div>
        <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
          Typ *
        </label>
        <select
          bind:value={contentType}
          class="w-full px-3 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                 bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
        >
          <option value="">-- Bitte wählen --</option>
          {#each contentTypeOptions as ct}
            <option value={ct}>{ct}</option>
          {/each}
        </select>
        {#if errors.contentType}
          <p class="mt-1 text-sm text-light-re dark:text-dark-re">{errors.contentType}</p>
        {/if}
      </div>
    {/if}

    <!-- Inhalt -->
    {#if contentType}
      <div>
        <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
          Inhalt
        </label>
        <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mb-1">
          Markdown wird unterstützt
        </p>
        <textarea
          bind:value={content}
          rows="6"
          class="w-full px-3 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                 bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                 focus:outline-none focus:border-primary dark:focus:border-primary-dark"
          placeholder="Beschreibe den Knoten (Markdown möglich)..."
        ></textarea>
      </div>
    {/if}

    <!-- Strukturierte Metadaten: Funktion -->
    {#if category === 'concept' && contentType === 'funktion'}
      <div class="border border-light-ui-3 dark:border-dark-ui-3 rounded-lg p-4">
        <h3 class="text-sm font-semibold text-light-tx dark:text-dark-tx mb-3">
          Funktionssignatur
        </h3>
        <div class="space-y-3">
          <div>
            <label class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1">
              Funktionsname
            </label>
            <input
              type="text"
              bind:value={signatur.name}
              class="w-full px-2 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
              placeholder="z. B. berechneDurchschnitt"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1">
              Sprache
            </label>
            <select
              bind:value={signatur.sprache}
              class="w-full px-2 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
            >
              <option value="arduino_cpp">Arduino C++</option>
              <option value="python">Python</option>
              <option value="javascript">JavaScript</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1">
              Parameter
            </label>
            {#if signatur.parameter.length === 0}
              <p class="text-xs text-light-tx-3 dark:text-dark-tx-3 italic mb-2">
                Keine Parameter definiert
              </p>
            {/if}
            {#each signatur.parameter as param, index (index)}
              <div class="flex gap-2 items-end mb-2">
                <input
                  type="text"
                  value={param.name}
                  oninput={e => updateParameter(index, 'name', e.target.value)}
                  class="flex-1 px-2 py-1 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                         bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
                  placeholder="Name"
                />
                <input
                  type="text"
                  value={param.typ}
                  oninput={e => updateParameter(index, 'typ', e.target.value)}
                  class="flex-1 px-2 py-1 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                         bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
                  placeholder="Typ"
                />
                <input
                  type="text"
                  value={param.beschreibung}
                  oninput={e => updateParameter(index, 'beschreibung', e.target.value)}
                  class="flex-1 px-2 py-1 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                         bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
                  placeholder="Beschreibung"
                />
                <button
                  type="button"
                  onclick={() => removeParameter(index)}
                  class="px-2 py-1 text-xs text-light-re dark:text-dark-re
                         hover:bg-light-re/10 dark:hover:bg-dark-re/10 rounded"
                >
                  ×
                </button>
              </div>
            {/each}
            <button
              type="button"
              onclick={addParameter}
              class="text-xs text-primary dark:text-dark-bl underline"
            >
              + Parameter hinzufügen
            </button>
          </div>
          <div>
            <label class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1">
              Rückgabetyp
            </label>
            <input
              type="text"
              bind:value={signatur.rueckgabe.typ}
              class="w-full px-2 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
              placeholder="z. B. int"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1">
              Rückgabebeschreibung
            </label>
            <input
              type="text"
              bind:value={signatur.rueckgabe.beschreibung}
              class="w-full px-2 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
              placeholder="z. B. Der berechnete Durchschnittswert"
            />
          </div>
        </div>
      </div>
    {/if}

    <!-- Strukturierte Metadaten: Bauteil -->
    {#if category === 'concept' && contentType === 'bauteil'}
      <div class="border border-light-ui-3 dark:border-dark-ui-3 rounded-lg p-4">
        <h3 class="text-sm font-semibold text-light-tx dark:text-dark-tx mb-3">
          Schaltzeichen
        </h3>
        <div class="space-y-3">
          <div>
            <label class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1">
              Beschreibung
            </label>
            <textarea
              bind:value={schaltzeichen.beschreibung}
              rows="2"
              class="w-full px-2 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
              placeholder="Beschreibung des Bauteils für das Embedding"
            ></textarea>
          </div>
          <div>
            <label class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1">
              Norm
            </label>
            <input
              type="text"
              bind:value={schaltzeichen.norm}
              class="w-full px-2 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
              placeholder="z. B. DIN EN IEC 60617"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1">
              Kennung
            </label>
            <input
              type="text"
              bind:value={schaltzeichen.kennung}
              class="w-full px-2 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
              placeholder="z. B. R, LED, U"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1">
              SVG (optional)
            </label>
            <textarea
              bind:value={schaltzeichen.svg}
              rows="4"
              class="w-full px-2 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                     font-family:monospace"
              placeholder="Inline SVG-Code"
            ></textarea>
          </div>
        </div>
      </div>
    {/if}

    <!-- Generisches JSON-Feld für andere Typen -->
    {#if category && contentType && !['funktion', 'bauteil'].includes(contentType)}
      <div>
        <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
          Metadaten (JSON)
        </label>
        <textarea
          bind:value={metadata}
          rows="4"
          class="w-full px-3 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                 bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                 font-family:monospace"
          placeholder="{{}}"
        ></textarea>
      </div>
    {/if}

    <!-- Erweiterte Einstellungen -->
    <details class="border-t border-light-ui-3 dark:border-dark-ui-3 pt-4">
      <summary class="cursor-pointer text-sm font-medium text-light-tx-2 dark:text-dark-tx-2">
        Erweiterte Einstellungen
      </summary>
      <div class="mt-4 space-y-4">
        <!-- Lese-Scope -->
        <div>
          <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
            Lese-Sichtbarkeit
          </label>
          <select
            bind:value={readScope}
            class="w-full px-3 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                   bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
          >
            <option value="private">Privat</option>
            <option value="group">Gruppe</option>
            <option value="subject">Fach</option>
            <option value="school">Schule</option>
          </select>
        </div>

        <!-- Gruppen-Auswahl für read_scope -->
        {#if ['subject', 'group'].includes(readScope)}
          <div>
            <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
              {readScope === 'group' ? 'Gruppe' : 'Fachgruppe'}
            </label>
            <select
              bind:value={readScopeGroupId}
              class="w-full px-3 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
            >
              <option value={null}>-- Keine Auswahl --</option>
              {#each groupOptions as group}
                <option value={group.id}>{group.name}</option>
              {/each}
            </select>
          </div>
        {/if}

        <!-- Schreib-Scope -->
        <div>
          <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
            Schreib-Sichtbarkeit
          </label>
          <select
            bind:value={writeScope}
            class="w-full px-3 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                   bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
          >
            {#each writeScopes as scope}
              <option value={scope}>{scope}</option>
            {/each}
          </select>
        </div>

        <!-- Gruppen-Auswahl für write_scope -->
        {#if ['subject', 'group'].includes(writeScope)}
          <div>
            <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
              {writeScope === 'group' ? 'Gruppe' : 'Fachgruppe'}
            </label>
            <select
              bind:value={writeScopeGroupId}
              class="w-full px-3 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
            >
              <option value={null}>-- Keine Auswahl --</option>
              {#each groupOptions as group}
                <option value={group.id}>{group.name}</option>
              {/each}
            </select>
          </div>
        {/if}

        <!-- Ablaufdatum -->
        <div>
          <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
            Ablaufdatum
          </label>
          <div class="flex gap-2 items-center">
            <input
              type="date"
              bind:value={validUntil}
              class="px-3 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
            />
            <button
              type="button"
              onclick={() => { validUntil = schuljahresEnde() }}
              class="text-xs px-2 py-1.5 rounded-md bg-light-ui-2 dark:bg-dark-ui-2
                     text-light-tx dark:text-dark-tx hover:bg-light-ui-3 dark:hover:bg-dark-ui-3"
            >
              Schuljahresende (31.07.)
            </button>
          </div>
        </div>

        <!-- Schuljahr -->
        <div>
          <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
            Schuljahr
          </label>
          <input
            type="text"
            bind:value={schuljahr}
            class="w-full px-3 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                   bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
            placeholder="z. B. 2024/2025"
          />
        </div>

        <!-- Fach und Jahrgangsstufen - nur für knowledge-Knoten -->
        {#if category === 'knowledge'}
          <!-- Fachzuordnung -->
          <div class="space-y-1">
            <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
              Fach
            </label>
            <select
              bind:value={subjectId}
              class="w-full px-3 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
            >
              <option value={null}>— fächerübergreifend —</option>
              {#each $subjects as s (s.id)}
                <option value={s.id}>{s.name}</option>
              {/each}
            </select>
          </div>

          <!-- Jahrgangsstufen -->
          <div class="space-y-1">
            <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
              Jahrgangsstufe
            </label>
            <div class="flex items-center gap-2">
              <input
                type="number" min="1" max="13"
                bind:value={minGrade}
                placeholder="von"
                class="w-20 px-3 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
              />
              <span class="text-light-tx-2 dark:text-dark-tx-2 text-sm">–</span>
              <input
                type="number" min="1" max="13"
                bind:value={maxGrade}
                placeholder="bis"
                class="w-20 px-3 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
              />
              <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                (leer = alle Stufen)
              </span>
            </div>
            {#if gradeError}
              <p class="text-xs text-light-re dark:text-dark-re mt-1">{gradeError}</p>
            {/if}
          </div>
        {/if}
      </div>
    </details>

    <!-- Buttons -->
    <div class="flex gap-3 pt-4">
      <button
        type="submit"
        disabled={saving}
        class="px-4 py-2 text-sm rounded-md bg-primary dark:bg-primary-dark
               text-white font-medium hover:opacity-90 transition-opacity
               disabled:opacity-50"
      >
        {saving ? 'Speichern…' : 'Speichern'}
      </button>
      <button
        type="button"
        onclick={() => history.back()}
        class="px-4 py-2 text-sm rounded-md text-light-tx dark:text-dark-tx
               hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
      >
        Abbrechen
      </button>
    </div>

    <!-- Fehler -->
    {#if errors.general}
      <div class="mt-4 p-3 text-sm text-light-re dark:text-dark-re
                  bg-light-re/10 dark:bg-dark-re/10 rounded-md">
        {errors.general}
      </div>
    {/if}
  </form>
</div>
