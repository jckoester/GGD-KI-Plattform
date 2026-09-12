<script>
    // Selbstverwaltung persönlicher Zugangstoken im Profil.
    //
    // Der Klartext ist **einmal** zu haben, direkt nach dem Anlegen. Deshalb steht er
    // hier in einem eigenen, auffälligen Block statt in der Liste: Wer ihn wegklickt,
    // bekommt ihn nicht wieder, und das muss man sehen, bevor man klickt.
    import { onMount } from "svelte";
    import { KeyRound, Copy, Check, Trash2, Plus } from "lucide-svelte";
    import {
        createToken,
        getTokenScopes,
        getTokens,
        revokeToken,
    } from "$lib/api.js";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import InfoBanner from "$lib/components/InfoBanner.svelte";
    import WarningBanner from "$lib/components/WarningBanner.svelte";
    import StepUpDialog from "$lib/components/StepUpDialog.svelte";

    let tokens = $state([]);
    let scopes = $state([]);
    let maxTage = $state(365);
    let laden = $state(true);
    let fehler = $state(null);

    let formularOffen = $state(false);
    let name = $state("");
    let gewaehlt = $state(new Set());
    let gueltigBis = $state("");
    let sendet = $state(false);

    // Der frisch erzeugte Klartext. `null`, sobald der Block geschlossen wird.
    let frisch = $state(null);
    let kopiert = $state(false);

    let stepUpOffen = $state(false);

    async function laden_() {
        laden = true;
        try {
            const [liste, auskunft] = await Promise.all([getTokens(), getTokenScopes()]);
            tokens = liste;
            scopes = auskunft.scopes;
            maxTage = auskunft.max_tage;
            if (!gueltigBis) gueltigBis = auskunft.vorschlag_gueltig_bis;
        } catch (e) {
            fehler = e.message;
        } finally {
            laden = false;
        }
    }

    onMount(laden_);

    function umschalten(key) {
        const neu = new Set(gewaehlt);
        if (neu.has(key)) neu.delete(key);
        else neu.add(key);
        gewaehlt = neu;
    }

    const kannAnlegen = $derived(
        name.trim().length > 0 && gewaehlt.size > 0 && gueltigBis && !sendet,
    );

    async function anlegen() {
        if (!kannAnlegen) return;
        sendet = true;
        fehler = null;
        try {
            const antwort = await createToken({
                name: name.trim(),
                scopes: [...gewaehlt],
                gueltigBis,
            });
            frisch = antwort.token;
            kopiert = false;
            formularOffen = false;
            name = "";
            gewaehlt = new Set();
            await laden_();
        } catch (e) {
            if (e.stepUpRequired) {
                // Nicht als Fehler zeigen: Das Backend verlangt nur eine frische
                // Anmeldung, die Eingaben bleiben stehen und werden danach wiederholt.
                stepUpOffen = true;
            } else {
                fehler = e.message;
            }
        } finally {
            sendet = false;
        }
    }

    async function nachStepUp() {
        stepUpOffen = false;
        await anlegen();
    }

    async function kopieren() {
        try {
            await navigator.clipboard.writeText(frisch);
            kopiert = true;
        } catch {
            kopiert = false;
        }
    }

    async function widerrufen(eintrag) {
        if (!confirm(`Zugang „${eintrag.name}" wirklich beenden?`)) return;
        try {
            await revokeToken(eintrag.id);
            await laden_();
        } catch (e) {
            fehler = e.message;
        }
    }

    function datum(wert) {
        return wert ? new Date(wert).toLocaleDateString("de-DE") : "—";
    }

    function zustand(eintrag) {
        if (eintrag.revoked_at) return { text: "beendet", matt: true };
        if (new Date(eintrag.expires_at) <= new Date())
            return { text: "abgelaufen", matt: true };
        return { text: `gültig bis ${datum(eintrag.expires_at)}`, matt: false };
    }
</script>

<h2 class="text-base font-semibold mb-1 text-light-tx-2 dark:text-dark-tx-2">
    Zugangstoken
</h2>
<p class="text-sm mb-3 text-light-tx-2 dark:text-dark-tx-2">
    Für Programme außerhalb des Browsers, die auf Ihre Unterrichtsplanung oder Ihre
    Bausteine zugreifen sollen. Ein Token kann nicht chatten und nichts verwalten.
</p>

{#if fehler}
    <ErrorBanner message={fehler} />
{/if}

{#if frisch}
    <div
        class="mb-4 rounded-lg border border-light-gr dark:border-dark-gr bg-light-gr-bg dark:bg-dark-gr-bg p-3"
    >
        <p class="text-sm font-medium mb-2 text-light-tx dark:text-dark-tx">
            Das Token wird nur dieses eine Mal angezeigt.
        </p>
        <div class="flex items-center gap-2">
            <code
                class="flex-1 break-all rounded bg-light-bg dark:bg-dark-bg px-2 py-1 text-xs text-light-tx dark:text-dark-tx"
                >{frisch}</code
            >
            <button
                class="flex items-center gap-1 rounded px-2 py-1 text-sm border border-light-ui-3 dark:border-dark-ui-3 text-light-tx dark:text-dark-tx"
                onclick={kopieren}
            >
                {#if kopiert}<Check size={14} />Kopiert{:else}<Copy size={14} />Kopieren{/if}
            </button>
        </div>
        <button
            class="mt-2 text-sm underline text-light-tx-2 dark:text-dark-tx-2"
            onclick={() => (frisch = null)}>Ich habe es gesichert</button
        >
    </div>
{/if}

{#if laden}
    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">Lädt…</p>
{:else}
    {#if tokens.length === 0}
        <InfoBanner message="Sie haben noch keine Zugangstoken angelegt." />
    {:else}
        <ul class="mb-4 flex flex-col gap-2">
            {#each tokens as eintrag (eintrag.id)}
                {@const z = zustand(eintrag)}
                <li
                    class="flex items-start gap-3 rounded-lg border border-light-ui-3 dark:border-dark-ui-3 p-3"
                    class:opacity-60={z.matt}
                >
                    <KeyRound size={16} class="mt-0.5 shrink-0" />
                    <div class="min-w-0 flex-1">
                        <p class="text-sm font-medium text-light-tx dark:text-dark-tx">
                            {eintrag.name}
                        </p>
                        <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                            {eintrag.scopes.join(" · ")}
                        </p>
                        <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                            {z.text} · zuletzt benutzt: {datum(eintrag.last_used_at)}
                        </p>
                    </div>
                    {#if !eintrag.revoked_at}
                        <button
                            class="shrink-0 rounded p-1 text-light-re dark:text-dark-re"
                            title="Zugang beenden"
                            aria-label="Zugang {eintrag.name} beenden"
                            onclick={() => widerrufen(eintrag)}
                        >
                            <Trash2 size={16} />
                        </button>
                    {/if}
                </li>
            {/each}
        </ul>
    {/if}

    {#if formularOffen}
        <div
            class="rounded-lg border border-light-ui-3 dark:border-dark-ui-3 p-3 flex flex-col gap-3"
        >
            <label class="text-sm text-light-tx dark:text-dark-tx">
                Name
                <input
                    class="mt-1 w-full rounded border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg px-2 py-1 text-sm"
                    bind:value={name}
                    placeholder="z. B. MacBook Obsidian"
                    maxlength="80"
                />
            </label>

            <fieldset>
                <legend class="text-sm text-light-tx dark:text-dark-tx mb-1">
                    Berechtigungen
                </legend>
                <div class="flex flex-col gap-1">
                    {#each scopes as s (s.key)}
                        <label class="flex items-center gap-2 text-sm text-light-tx dark:text-dark-tx">
                            <input
                                type="checkbox"
                                checked={gewaehlt.has(s.key)}
                                onchange={() => umschalten(s.key)}
                            />
                            {s.label}
                        </label>
                    {/each}
                </div>
            </fieldset>

            <label class="text-sm text-light-tx dark:text-dark-tx">
                Gültig bis
                <input
                    type="date"
                    class="mt-1 block rounded border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg px-2 py-1 text-sm"
                    bind:value={gueltigBis}
                />
            </label>
            <WarningBanner
                message={`Ein Token gilt höchstens ${maxTage} Tage. Wer es verliert, legt ein neues an — wiederherstellen lässt es sich nicht.`}
            />

            <div class="flex gap-2">
                <button
                    class="rounded bg-primary dark:bg-primary-dark px-3 py-1 text-sm text-white disabled:opacity-50"
                    disabled={!kannAnlegen}
                    onclick={anlegen}
                >
                    {sendet ? "Wird angelegt…" : "Token anlegen"}
                </button>
                <button
                    class="rounded px-3 py-1 text-sm border border-light-ui-3 dark:border-dark-ui-3 text-light-tx dark:text-dark-tx"
                    onclick={() => (formularOffen = false)}>Abbrechen</button
                >
            </div>
        </div>
    {:else}
        <button
            class="flex items-center gap-1 rounded px-3 py-1 text-sm border border-light-ui-3 dark:border-dark-ui-3 text-light-tx dark:text-dark-tx"
            onclick={() => (formularOffen = true)}
        >
            <Plus size={14} /> Neues Token
        </button>
    {/if}
{/if}

{#if stepUpOffen}
    <StepUpDialog
        action="create_token"
        resourceId=""
        onSuccess={nachStepUp}
        onCancel={() => (stepUpOffen = false)}
    />
{/if}
