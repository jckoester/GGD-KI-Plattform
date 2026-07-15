<script>
    import { onMount } from "svelte";
    import { getAdminUsers, revokeUserSessions } from "$lib/api.js";
    import { Users, ArrowLeft, ShieldOff, Search } from "lucide-svelte";
    import LoadingBanner from "$lib/components/LoadingBanner.svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import SuccessBanner from "$lib/components/SuccessBanner.svelte";
    import InfoBanner from "$lib/components/InfoBanner.svelte";

    let users = $state([]);
    let loading = $state(true);
    let error = $state(null);

    let roleFilter = $state("");
    let search = $state("");
    let confirming = $state(null); // pseudonym, für den die Bestätigung offen ist
    let revoking = $state(null); // pseudonym, dessen Revoke gerade läuft
    let actionError = $state(null);
    let actionSuccess = $state(null);

    const ELEVATED = new Set(["admin", "review"]);

    let filtered = $derived(
        users.filter(
            (u) =>
                (!roleFilter || u.roles.includes(roleFilter)) &&
                (!search || u.pseudonym.toLowerCase().includes(search.toLowerCase())),
        ),
    );

    onMount(async () => {
        try {
            const data = await getAdminUsers();
            users = data.users;
        } catch (e) {
            error = e.message;
        } finally {
            loading = false;
        }
    });

    function fmtDate(iso) {
        if (!iso) return "—";
        return new Date(iso).toLocaleString("de-DE", {
            dateStyle: "medium",
            timeStyle: "short",
        });
    }

    async function revoke(pseudonym) {
        revoking = pseudonym;
        actionError = null;
        actionSuccess = null;
        try {
            const res = await revokeUserSessions(pseudonym);
            const u = users.find((x) => x.pseudonym === pseudonym);
            if (u) u.revoked_all_before = res.revoked_all_before;
            users = [...users];
            actionSuccess = `Alle Sitzungen beendet. Der Nutzer muss sich neu anmelden; dabei werden die Rollen neu bewertet.`;
        } catch (e) {
            actionError = e.message;
        } finally {
            revoking = null;
            confirming = null;
        }
    }
</script>

<button
    onclick={() => history.back()}
    class="flex items-center gap-1 mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx transition-colors"
>
    <ArrowLeft class="w-4 h-4" /> Zurück
</button>

<div class="max-w-4xl mx-auto py-4 space-y-5">
    <div class="flex items-center gap-2 text-light-tx dark:text-dark-tx">
        <Users class="w-6 h-6" />
        <h1 class="text-2xl font-semibold">Nutzer & Sitzungen</h1>
    </div>

    <InfoBanner
        message="Wurde einer Person im Schulkonto eine Rolle entzogen (z. B. Admin), wirkt das erst beim nächsten Login. Über „Sitzungen beenden“ werden alle aktiven Sitzungen sofort ungültig — die Person muss sich neu anmelden, wobei die Rollen neu bewertet werden."
    />

    {#if actionError}<ErrorBanner message={actionError} />{/if}
    {#if actionSuccess}<SuccessBanner message={actionSuccess} />{/if}

    {#if loading}
        <LoadingBanner message="Nutzer werden geladen…" />
    {:else if error}
        <ErrorBanner message={error} />
    {:else}
        <!-- Filter -->
        <div class="flex flex-wrap items-center gap-3">
            <label class="flex items-center gap-2 text-sm text-light-tx-2 dark:text-dark-tx-2">
                Rolle:
                <select
                    bind:value={roleFilter}
                    class="bg-light-bg-2 dark:bg-dark-bg-2 border border-light-ui-3 dark:border-dark-ui-3 rounded px-2 py-1 text-light-tx dark:text-dark-tx"
                >
                    <option value="">alle</option>
                    <option value="admin">admin</option>
                    <option value="review">review</option>
                    <option value="teacher">teacher</option>
                    <option value="student">student</option>
                </select>
            </label>
            <div class="flex items-center gap-2 text-sm">
                <Search class="w-4 h-4 text-light-tx-2 dark:text-dark-tx-2" />
                <input
                    bind:value={search}
                    placeholder="Pseudonym suchen…"
                    class="bg-light-bg-2 dark:bg-dark-bg-2 border border-light-ui-3 dark:border-dark-ui-3 rounded px-2 py-1 text-light-tx dark:text-dark-tx"
                />
            </div>
            <span class="text-sm text-light-tx-2 dark:text-dark-tx-2 ml-auto">
                {filtered.length} von {users.length}
            </span>
        </div>

        {#if filtered.length === 0}
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">Keine Nutzer gefunden.</p>
        {:else}
            <div class="overflow-x-auto border border-light-ui-3 dark:border-dark-ui-3 rounded-lg">
                <table class="w-full text-sm">
                    <thead class="bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx-2 dark:text-dark-tx-2">
                        <tr>
                            <th class="text-left font-medium px-3 py-2">Pseudonym</th>
                            <th class="text-left font-medium px-3 py-2">Rollen</th>
                            <th class="text-left font-medium px-3 py-2">Klasse</th>
                            <th class="text-left font-medium px-3 py-2">Letzter Login</th>
                            <th class="text-right font-medium px-3 py-2">Aktion</th>
                        </tr>
                    </thead>
                    <tbody>
                        {#each filtered as u (u.pseudonym)}
                            <tr class="border-t border-light-ui-3 dark:border-dark-ui-3">
                                <td class="px-3 py-2">
                                    <span
                                        class="font-mono text-xs text-light-tx dark:text-dark-tx"
                                        title={u.pseudonym}
                                    >
                                        {u.pseudonym.slice(0, 12)}…
                                    </span>
                                    {#if u.revoked_all_before}
                                        <span
                                            class="ml-2 text-xs text-light-tx-2 dark:text-dark-tx-2"
                                            title={"Sitzungen beendet am " + fmtDate(u.revoked_all_before)}
                                        >
                                            (beendet)
                                        </span>
                                    {/if}
                                </td>
                                <td class="px-3 py-2">
                                    <div class="flex flex-wrap gap-1">
                                        {#each u.roles as r}
                                            <span
                                                class="px-1.5 py-0.5 rounded text-xs border {ELEVATED.has(r)
                                                    ? 'border-primary text-light-bl dark:text-dark-bl bg-primary/10'
                                                    : 'border-light-ui-3 dark:border-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2'}"
                                            >
                                                {r}
                                            </span>
                                        {/each}
                                    </div>
                                </td>
                                <td class="px-3 py-2 text-light-tx-2 dark:text-dark-tx-2">
                                    {u.grade ?? "—"}
                                </td>
                                <td class="px-3 py-2 text-light-tx-2 dark:text-dark-tx-2">
                                    {fmtDate(u.last_login_at)}
                                </td>
                                <td class="px-3 py-2 text-right">
                                    {#if confirming === u.pseudonym}
                                        <span class="inline-flex items-center gap-2">
                                            <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">Sicher?</span>
                                            <button
                                                onclick={() => revoke(u.pseudonym)}
                                                disabled={revoking === u.pseudonym}
                                                class="text-xs px-2 py-1 rounded bg-light-re dark:bg-dark-re text-white disabled:opacity-50"
                                            >
                                                {revoking === u.pseudonym ? "…" : "Ja, beenden"}
                                            </button>
                                            <button
                                                onclick={() => (confirming = null)}
                                                class="text-xs px-2 py-1 rounded border border-light-ui-3 dark:border-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2"
                                            >
                                                Abbrechen
                                            </button>
                                        </span>
                                    {:else}
                                        <button
                                            onclick={() => (confirming = u.pseudonym)}
                                            class="inline-flex items-center gap-1 text-xs px-2 py-1 rounded border border-light-ui-3 dark:border-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx transition-colors"
                                        >
                                            <ShieldOff class="w-3.5 h-3.5" /> Sitzungen beenden
                                        </button>
                                    {/if}
                                </td>
                            </tr>
                        {/each}
                    </tbody>
                </table>
            </div>
        {/if}
    {/if}
</div>
