<script>
    import { branding } from "$lib/branding.js";
    import {
        ExternalLink,
        Scale,
        Link,
        Users,
        BookOpen,
        GitBranch,
        ShieldCheck,
        ShieldBan,
    } from "lucide-svelte";

    // Bibliotheken-Tabelle
    const frontendLibs = [
        { name: "SvelteKit", version: "^2.0.0", license: "MIT" },
        { name: "Tailwind CSS", version: "^4.2.2", license: "MIT" },
        { name: "marked", version: "^18.0.2", license: "MIT" },
        { name: "highlight.js", version: "^11.11.1", license: "BSD-3-Clause" },
        { name: "lucide-svelte", version: "^1.0.1", license: "ISC" },
    ];

    const backendLibs = [
        { name: "FastAPI", version: "", license: "MIT" },
        { name: "SQLAlchemy", version: "", license: "MIT" },
        { name: "Pydantic", version: "", license: "MIT" },
        { name: "LiteLLM", version: "", license: "MIT" },
        { name: "Alembic", version: "", license: "MIT" },
        { name: "httpx", version: "", license: "BSD-3-Clause" },
        { name: "pdfminer.six", version: "", license: "MIT" },
    ];

    const authors = [{ name: "Jan Köster", github: "jckoester" }];

    const repository = "https://github.com/jckoester/GGD-KI-Plattform/";
</script>

<div class="h-full overflow-y-auto">
    <div class="max-w-2xl mx-auto py-8 px-4">
        <!-- Header -->
        <div class="mb-8">
            <div class="flex items-center gap-3 mb-2">
                {#if branding.logo_url_light || branding.logo_url_dark}
                    {#if branding.logo_url_light}
                        <img
                            src={branding.logo_url_light}
                            alt="Logo"
                            class="h-8 w-auto dark:hidden"
                        />
                    {/if}
                    {#if branding.logo_url_dark}
                        <img
                            src={branding.logo_url_dark}
                            alt="Logo"
                            class="h-8 w-auto hidden dark:block"
                        />
                    {/if}
                {:else}
                    <div
                        class="w-8 h-8 rounded-full bg-primary flex items-center justify-center
                           text-white text-xs font-bold select-none"
                    >
                        {initials(branding.name)}
                    </div>
                {/if}
                <div>
                    <h1
                        class="text-2xl font-semibold text-light-tx dark:text-dark-tx"
                    >
                        {branding.name}
                    </h1>
                    <span class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                        Version {__APP_VERSION__}
                    </span>
                </div>
            </div>
        </div>

        <!-- Kurzbeschreibung -->
        <section class="mb-8">
            <p class="text-light-tx-2 dark:text-dark-tx-2 leading-relaxed">
                Die {branding.name}-Plattform ist eine selbstgehostete
                KI-Zugangsplattform für Schulen. Sie ermöglicht den sicheren und
                datenschutzkonformen Zugriff auf große Sprachmodelle (LLMs) für
                Schüler:innen und Lehrkräfte.
            </p>
        </section>

        <!-- Links -->
        <section class="mb-8">
            <h2
                class="text-lg font-semibold mb-4 text-light-tx dark:text-dark-tx"
            >
                <Link class="w-5 h-5 inline-block mr-2" />
                Links
            </h2>
            <div class="space-y-3">
                <a
                    href={repository}
                    class="flex items-center gap-2 text-light-bl dark:text-dark-bl hover:underline"
                    target="_blank"
                >
                    <ExternalLink class="w-4 h-4" />
                    GitHub-Repository
                </a>
                <a
                    href="/help"
                    class="flex items-center gap-2 text-light-bl dark:text-dark-bl hover:underline"
                >
                    <ExternalLink class="w-4 h-4" />
                    Hilfe
                </a>
            </div>
        </section>

        <!-- Datenschutz-Hinweis -->
        <section class="mb-8">
            <h2
                class="text-lg font-semibold mb-4 text-light-tx dark:text-dark-tx"
            >
                <ShieldBan class="w-5 h-5 inline-block mr-2" />

                Datenschutz
            </h2>
            <p class="text-light-tx-2 dark:text-dark-tx-2 leading-relaxed">
                Die Kommunikation mit KI-Modellen erfolgt ausschließlich über
                einen selbst betriebenen LiteLLM-Proxy. Dabei werden keine
                personenbezogenen Nutzerdaten (Name, Anmeldedaten, Klasse o. ä.)
                an externe Anbieter übermittelt — lediglich der Inhalt der
                Konversation.
            </p>
        </section>

        <!-- Autoren -->
        <section class="mb-8">
            <h2
                class="text-lg font-semibold mb-4 text-light-tx dark:text-dark-tx"
            >
                <Users class="w-5 h-5 inline-block mr-2" />
                Autoren
            </h2>
            <ul class="space-y-2">
                {#each authors as author}
                    <li class="text-light-tx-2 dark:text-dark-tx-2">
                        {#if author.github}
                            <a
                                href="https://github.com/{author.github}"
                                class="hover:text-light-bl dark:hover:text-dark-bl"
                                target="_blank"
                            >
                                {author.name}
                            </a>
                        {:else}
                            {author.name}
                        {/if}
                    </li>
                {/each}
            </ul>
        </section>

        <!-- Lizenz -->
        <section class="mb-8">
            <h2
                class="text-lg font-semibold mb-4 text-light-tx dark:text-dark-tx"
            >
                <Scale class="w-5 h-5 inline-block mr-2" />
                Lizenz
            </h2>
            <p class="text-light-tx-2 dark:text-dark-tx-2 mb-2">
                Diese Software wird unter der <strong>EUPL-1.2</strong>-Lizenz
                veröffentlicht.
            </p>
            <a
                href="https://joinup.ec.europa.eu/collection/eupl/eupl-text-eupl-12"
                class="flex items-center gap-2 text-light-bl dark:text-dark-bl hover:underline text-sm"
                target="_blank"
            >
                <ExternalLink class="w-4 h-4" />
                Offizieller Lizenztext (EUPL-1.2)
            </a>
        </section>

        <!-- Verwendete Bibliotheken -->
        <section class="mb-8">
            <h2
                class="text-lg font-semibold mb-4 text-light-tx dark:text-dark-tx"
            >
                <BookOpen class="w-5 h-5 inline-block mr-2" />
                Verwendete Bibliotheken
            </h2>

            <h3
                class="text-base font-medium mb-3 text-light-tx-2 dark:text-dark-tx-2"
            >
                Frontend
            </h3>
            <div class="overflow-x-auto mb-6">
                <table class="min-w-full text-sm">
                    <thead>
                        <tr
                            class="border-b border-light-ui-3 dark:border-dark-ui-3"
                        >
                            <th
                                class="text-left py-2 px-3 text-light-tx-2 dark:text-dark-tx-2 font-medium"
                            >
                                Bibliothek
                            </th>
                            <th
                                class="text-left py-2 px-3 text-light-tx-2 dark:text-dark-tx-2 font-medium"
                            >
                                Lizenz
                            </th>
                        </tr>
                    </thead>
                    <tbody>
                        {#each frontendLibs as lib}
                            <tr
                                class="border-b border-light-ui-3 dark:border-dark-ui-3 last:border-0"
                            >
                                <td
                                    class="py-2 px-3 text-light-tx dark:text-dark-tx"
                                >
                                    {lib.name}
                                </td>
                                <td
                                    class="py-2 px-3 text-light-tx-2 dark:text-dark-tx-2"
                                >
                                    {lib.license}
                                </td>
                            </tr>
                        {/each}
                    </tbody>
                </table>
            </div>

            <h3
                class="text-base font-medium mb-3 text-light-tx-2 dark:text-dark-tx-2"
            >
                Backend
            </h3>
            <div class="overflow-x-auto">
                <table class="min-w-full text-sm">
                    <thead>
                        <tr
                            class="border-b border-light-ui-3 dark:border-dark-ui-3"
                        >
                            <th
                                class="text-left py-2 px-3 text-light-tx-2 dark:text-dark-tx-2 font-medium"
                            >
                                Bibliothek
                            </th>
                            <th
                                class="text-left py-2 px-3 text-light-tx-2 dark:text-dark-tx-2 font-medium"
                            >
                                Lizenz
                            </th>
                        </tr>
                    </thead>
                    <tbody>
                        {#each backendLibs as lib}
                            <tr
                                class="border-b border-light-ui-3 dark:border-dark-ui-3 last:border-0"
                            >
                                <td
                                    class="py-2 px-3 text-light-tx dark:text-dark-tx"
                                >
                                    {lib.name}
                                </td>
                                <td
                                    class="py-2 px-3 text-light-tx-2 dark:text-dark-tx-2"
                                >
                                    {lib.license}
                                </td>
                            </tr>
                        {/each}
                    </tbody>
                </table>
            </div>
        </section>

        <!-- Git-Build-Referenz -->
        {#if __GIT_COMMIT__ && __GIT_COMMIT__ !== "unknown"}
            <section class="mb-8">
                <h2
                    class="text-lg font-semibold mb-4 text-light-tx dark:text-dark-tx"
                >
                    <GitBranch class="w-5 h-5 inline-block mr-2" />
                    Build-Informationen
                </h2>
                <div class="flex items-center gap-2">
                    <ShieldCheck
                        class="w-4 h-4 text-light-tx-2 dark:text-dark-tx-2"
                    />
                    <code class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                        {__GIT_COMMIT__}
                    </code>
                </div>
            </section>
        {/if}

        <!-- Footer-Links -->
        <section class="pt-8 border-t border-light-ui-3 dark:border-dark-ui-3">
            <div class="flex gap-6 text-sm">
                <a
                    href="/info/impressum"
                    class="text-light-tx-2 dark:text-dark-tx-2 hover:text-light-bl dark:hover:text-dark-bl"
                >
                    Impressum
                </a>
                <a
                    href="/info/datenschutz"
                    class="text-light-tx-2 dark:text-dark-tx-2 hover:text-light-bl dark:hover:text-dark-bl"
                >
                    Datenschutz
                </a>
            </div>
        </section>
    </div>
</div>
