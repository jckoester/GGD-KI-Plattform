<script>
    /**
     * „Als Schüler:in ansehen" (0.29, ADR-016): Jahrgang und, wahlweise, eine eigene
     * Unterrichtsgruppe wählen. Danach lädt die Seite neu — mit dem Vorschau-Token sieht
     * die App aus wie für eine Schüler:in dieses Jahrgangs und dieser Gruppe.
     */
    import { Eye, Loader2 } from "lucide-svelte";
    import Dialog from "./Dialog.svelte";
    import ErrorBanner from "./ErrorBanner.svelte";
    import { betreteVorschau } from "$lib/api.js";
    import { STUDENT_GRADES } from "$lib/grades.js";
    import { onMount } from "svelte";
    import { myGroups, refreshMyGroups } from "$lib/stores/myGroups.js";
    import { vorschauGruppen, zielNachEintritt } from "$lib/vorschau.js";

    let { vorgabe = {}, onclose = () => {} } = $props();

    const gruppen = $derived(vorschauGruppen($myGroups));
    // Einmal beim Öffnen vorbelegen — danach gehört die Auswahl der Lehrkraft.
    // svelte-ignore state_referenced_locally
    let gruppeId = $state(vorgabe.gruppeId ?? "");
    // svelte-ignore state_referenced_locally
    let jahrgang = $state(vorgabe.jahrgang ?? STUDENT_GRADES[0]);
    let laeuft = $state(false);
    let fehler = $state(null);

    // Das Admin-Layout lädt die eigenen Gruppen nicht — der Dialog holt sie selbst.
    onMount(() => refreshMyGroups());

    function gruppeGewaehlt() {
        // Die Gruppe kennt ihren Jahrgang — dann soll er nicht widersprechen.
        const g = gruppen.find((x) => String(x.id) === String(gruppeId));
        if (g?.jahrgang && STUDENT_GRADES.includes(g.jahrgang)) jahrgang = g.jahrgang;
    }

    async function starten() {
        laeuft = true;
        fehler = null;
        try {
            await betreteVorschau({
                jahrgang: Number(jahrgang),
                gruppeId: gruppeId === "" ? null : Number(gruppeId),
                assistentId: vorgabe.assistentId ?? null,
            });
            // Ganze Seite neu: Jeder Store soll die Schülersicht laden, nicht nur einige.
            window.location.assign(zielNachEintritt(vorgabe.assistentId ?? null));
        } catch (e) {
            fehler = e.message;
            laeuft = false;
        }
    }

    const feld =
        "w-full rounded border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx px-2 py-1.5";
</script>

<Dialog open onClose={onclose} titelId="vorschau-titel" breite="max-w-md">
    <h2 id="vorschau-titel" class="text-lg font-semibold text-light-tx dark:text-dark-tx flex items-center gap-2">
        <Eye class="w-5 h-5" />
        {vorgabe.assistentId ? "Als Schüler:in testen" : "Als Schüler:in ansehen"}
    </h2>
    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-2">
        Du siehst die App eine Stunde lang so, wie eine Schüler:in sie sieht, und kannst
        alles ausprobieren. Ändern lässt sich in der Vorschau nichts; Chats aus der Vorschau
        stehen danach in einer eigenen Liste und werden nach 30 Tagen gelöscht.
    </p>

    {#if fehler}
        <div class="mt-3"><ErrorBanner message={fehler} /></div>
    {/if}

    <div class="mt-4 space-y-3 text-sm text-light-tx-2 dark:text-dark-tx-2">
        <label class="block">
            Unterrichtsgruppe
            <select bind:value={gruppeId} onchange={gruppeGewaehlt} class="{feld} mt-1">
                <option value="">ohne Gruppe</option>
                {#each gruppen as g (g.id)}
                    <option value={g.id}>{g.name}</option>
                {/each}
            </select>
            <span class="block text-xs mt-1">
                Mit Gruppe siehst du auch, was du für sie freigegeben hast, und ihren Unterricht.
            </span>
        </label>
        <label class="block">
            Klasse
            <select bind:value={jahrgang} class="{feld} mt-1">
                {#each STUDENT_GRADES as stufe (stufe)}
                    <option value={stufe}>{stufe}</option>
                {/each}
            </select>
        </label>
    </div>

    <div class="flex justify-end gap-2 mt-5">
        <button onclick={onclose} disabled={laeuft}
            class="px-4 py-2 bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx rounded-lg hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 disabled:opacity-50">
            Abbrechen
        </button>
        <button onclick={starten} disabled={laeuft}
            class="px-4 py-2 bg-primary dark:bg-primary-dark text-white rounded-lg flex items-center gap-2 disabled:opacity-50">
            {#if laeuft}<Loader2 class="w-4 h-4 animate-spin" />{:else}<Eye class="w-4 h-4" />{/if}
            Vorschau starten
        </button>
    </div>
</Dialog>
