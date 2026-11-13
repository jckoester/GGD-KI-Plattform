<script>
    // Titel, Fach und Thema eines Produkts bearbeiten (0.41, Schritt 4) — an der Karte der
    // Werkstatt, später auch in der Produktansicht (Schritt 8). Gesendet wird nur, was sich
    // geändert hat (`PATCH /artifacts/{id}`).
    import { getThemenVorschlaege, updateArtefaktAngaben } from '$lib/api.js'

    let { item, faecher = [], onGespeichert = () => {}, onAbbrechen = () => {} } = $props()

    // Startwerte einmal aus dem Produkt — danach gehört das Formular der Person.
    // svelte-ignore state_referenced_locally
    let titel = $state(item.title)
    // svelte-ignore state_referenced_locally
    let fach = $state(item.subject_id == null ? '' : String(item.subject_id))
    // svelte-ignore state_referenced_locally
    let thema = $state(item.topic ?? '')
    let vorschlaege = $state([])
    let speichert = $state(false)
    let fehler = $state(null)

    const listeId = $derived(`themen-${item.id}`)

    // Vorschläge passend zum gewählten Fach: eigene Themen, für Lehrkräfte dazu die Einheiten.
    $effect(() => {
        const id = fach === '' ? null : Number(fach)
        getThemenVorschlaege(id).then((t) => {
            vorschlaege = [...(t.eigene ?? []), ...(t.einheiten ?? [])]
        })
    })

    async function speichern(event) {
        event.preventDefault()
        if (!titel.trim()) {
            fehler = 'Der Titel darf nicht leer sein.'
            return
        }
        const aenderung = {}
        if (titel.trim() !== item.title) aenderung.title = titel.trim()
        const neuesFach = fach === '' ? null : Number(fach)
        if (neuesFach !== (item.subject_id ?? null)) aenderung.subject_id = neuesFach
        const neuesThema = thema.trim() || null
        if (neuesThema !== (item.topic ?? null)) aenderung.topic = neuesThema
        if (Object.keys(aenderung).length === 0) {
            onAbbrechen()
            return
        }
        speichert = true
        fehler = null
        try {
            onGespeichert(await updateArtefaktAngaben(item.id, aenderung))
        } catch (err) {
            fehler = err.message ?? 'Angaben konnten nicht gespeichert werden.'
        } finally {
            speichert = false
        }
    }
</script>

<form onsubmit={speichern} class="flex flex-col gap-2 text-sm">
    <label class="flex flex-col gap-0.5">
        <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">Titel</span>
        <input
            bind:value={titel}
            maxlength="200"
            class="px-2 py-1 rounded border border-light-ui-3 dark:border-dark-ui-3
                   bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
        />
    </label>
    <label class="flex flex-col gap-0.5">
        <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">Fach</span>
        <select
            bind:value={fach}
            class="px-2 py-1 rounded border border-light-ui-3 dark:border-dark-ui-3
                   bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
        >
            <option value="">— ohne Fach —</option>
            {#each faecher as f (f.id)}
                <option value={String(f.id)}>{f.name}</option>
            {/each}
        </select>
    </label>
    <label class="flex flex-col gap-0.5">
        <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">Thema</span>
        <input
            bind:value={thema}
            list={listeId}
            maxlength="100"
            placeholder="z. B. Säuren und Basen"
            class="px-2 py-1 rounded border border-light-ui-3 dark:border-dark-ui-3
                   bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
        />
        <datalist id={listeId}>
            {#each vorschlaege as v (v)}
                <option value={v}></option>
            {/each}
        </datalist>
    </label>
    {#if fehler}
        <p class="text-xs text-light-re dark:text-dark-re">{fehler}</p>
    {/if}
    <div class="flex gap-2 justify-end">
        <button
            type="button"
            onclick={onAbbrechen}
            class="text-xs px-2 py-1 rounded text-light-tx-2 dark:text-dark-tx-2
                   hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
        >
            Abbrechen
        </button>
        <button
            type="submit"
            disabled={speichert}
            class="text-xs px-3 py-1 rounded bg-primary dark:bg-primary-dark text-white
                   hover:opacity-90 disabled:opacity-50"
        >
            Speichern
        </button>
    </div>
</form>
