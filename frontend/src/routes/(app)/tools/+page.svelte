<script>
    import { onMount } from "svelte";
    import { goto } from "$app/navigation";
    import { getAssistants } from "$lib/api.js";
    import { isToolAssistant } from "$lib/tools.js";
    import { subjectMap } from "$lib/stores/subjects.js";
    import { Wrench, Bot, Loader2 } from "lucide-svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";

    let assistants = $state([]);
    let loading = $state(true);
    let error = $state(null);

    const AUDIENCE_LABELS = {
        all: "Alle",
        student: "Schüler:innen",
        teacher: "Lehrkräfte",
    };

    function getAudienceLabel(audience) {
        return AUDIENCE_LABELS[audience] || audience || "";
    }

    onMount(async () => {
        try {
            const data = await getAssistants();
            // Nur artefakterzeugende Werkzeug-Assistenten; die Sichtbarkeit
            // (audience/Zeitfenster/Scope) filtert bereits das Backend.
            assistants = (data.items ?? []).filter(isToolAssistant);
        } catch (err) {
            error = err.message ?? "Fehler beim Laden der Werkzeuge";
        } finally {
            loading = false;
        }
    });
</script>

<div class="h-full overflow-y-auto p-6">
    <div class="max-w-4xl mx-auto">
        <div class="flex items-center gap-2 mb-2 text-light-tx dark:text-dark-tx">
            <Wrench class="w-6 h-6" />
            <h1 class="text-2xl font-semibold">Werkzeuge</h1>
        </div>
        <p class="mb-6 text-sm text-light-tx-2 dark:text-dark-tx-2">
            Assistenten, die Inhalte erzeugen — etwa Bilder. Wähle ein Werkzeug, um
            einen Chat damit zu starten.
        </p>

        {#if loading}
            <div class="flex items-center justify-center py-12">
                <div
                    class="flex flex-col items-center gap-2 text-light-tx-2 dark:text-dark-tx-2"
                >
                    <Loader2 class="w-6 h-6 animate-spin" />
                    <p>Werkzeuge werden geladen...</p>
                </div>
            </div>
        {:else if error}
            <ErrorBanner message={error} />
        {:else if assistants.length === 0}
            <div class="text-center py-12 text-light-tx-3 dark:text-dark-tx-3">
                <p class="text-lg">Derzeit sind keine Werkzeuge für dich verfügbar.</p>
            </div>
        {:else}
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {#each assistants as assistant}
                    {@const subjectColor =
                        assistant.subject_id != null
                            ? ($subjectMap[assistant.subject_id]?.color ?? null)
                            : null}
                    <div
                        class="relative group bg-light-bg-2 dark:bg-dark-bg-2
                               border border-light-ui-3 dark:border-dark-ui-3
                               rounded-lg overflow-hidden"
                    >
                        <!-- Farbiger Top-Streifen (nur wenn Fach mit Farbe) -->
                        {#if subjectColor}
                            <span
                                class="block h-[3px] w-full"
                                style="background-color: {subjectColor}"
                            ></span>
                        {/if}

                        <!-- Hauptklickbereich → Chat -->
                        <button
                            onclick={() =>
                                goto(`/chat?assistant_id=${assistant.id}`)}
                            class="w-full text-left p-4 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                        >
                            <div class="flex items-start gap-3">
                                <Bot
                                    class="w-5 h-5 text-light-bl dark:text-dark-bl shrink-0 mt-0.5"
                                />
                                <div class="flex-1 min-w-0">
                                    <div class="flex items-center gap-2 flex-wrap">
                                        <span
                                            class="font-medium text-light-tx dark:text-dark-tx"
                                        >
                                            {assistant.name}
                                        </span>
                                        {#if assistant.audience}
                                            <span
                                                class="text-xs px-1.5 py-0.5 rounded-full
                                                 bg-light-ui-3 dark:bg-dark-ui-3
                                                 text-light-tx-2 dark:text-dark-tx-2"
                                            >
                                                {getAudienceLabel(
                                                    assistant.audience,
                                                )}
                                            </span>
                                        {/if}
                                    </div>
                                    {#if assistant.description}
                                        <p
                                            class="text-sm mt-1 text-light-tx-2 dark:text-dark-tx-2 line-clamp-2"
                                        >
                                            {assistant.description}
                                        </p>
                                    {/if}
                                    {#if assistant.tags && assistant.tags.length > 0}
                                        <div class="flex flex-wrap gap-1 mt-2">
                                            {#each assistant.tags as tag}
                                                <span
                                                    class="text-xs px-1.5 py-0.5 rounded-full
                                                     bg-light-ui-2 dark:bg-dark-ui-2
                                                     text-light-tx-3 dark:text-dark-tx-3"
                                                >
                                                    {tag}
                                                </span>
                                            {/each}
                                        </div>
                                    {/if}
                                </div>
                            </div>
                        </button>
                    </div>
                {/each}
            </div>
        {/if}
    </div>
</div>
