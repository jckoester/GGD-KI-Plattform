<script>
    import { EllipsisVertical, Pencil, Trash2 } from "lucide-svelte";
    import { onDestroy } from "svelte";
    import { goto } from "$app/navigation";
    import { deleteConversation, renameConversation } from "$lib/api.js";
    import {
        refreshConversations,
        updateConversationTitle,
    } from "$lib/stores/conversations.js";
    import { pageTitle } from "$lib/stores/pageTitle.js";

    // syncPageTitle: nur im Chat-Header auf true setzen
    // onDeleted: optionaler Callback; wenn nicht angegeben, wird zu /chat navigiert
    let {
        conversationId,
        title,
        syncPageTitle = false,
        onDeleted = null,
        iconSize = 20,
        buttonClasses = " hover:bg-light-ui dark:hover:bg-dark-ui",
    } = $props();

    let isOpen = $state(false);
    let isRenaming = $state(false);
    let isDeleting = $state(false);
    let newTitle = $state("");
    let buttonEl = $state(null);
    let dropdownStyle = $state("");

    function openMenu() {
        if (buttonEl) {
            const rect = buttonEl.getBoundingClientRect();
            dropdownStyle = `top: ${rect.bottom + 4}px; right: ${window.innerWidth - rect.right}px;`;
        }
        isOpen = true;
    }

    function toggleMenu() {
        if (isOpen) closeMenu();
        else openMenu();
    }

    function closeMenu() {
        isOpen = false;
        isRenaming = false;
        isDeleting = false;
    }

    function handleClickOutside(event) {
        if (!event.target.closest(".menu-container")) {
            closeMenu();
        }
    }

    function startRenaming() {
        newTitle = title;
        isRenaming = true;
        isDeleting = false;
    }

    function startDeleting() {
        isDeleting = true;
        isRenaming = false;
    }

    async function confirmRename() {
        if (!newTitle.trim()) return;
        try {
            await renameConversation(conversationId, newTitle.trim());
            updateConversationTitle(conversationId, newTitle.trim());
            if (syncPageTitle) pageTitle.set(newTitle.trim());
            closeMenu();
        } catch (error) {
            console.error("Fehler beim Umbenennen:", error);
        }
    }

    async function confirmDelete() {
        try {
            await deleteConversation(conversationId);
            closeMenu();
            if (onDeleted) {
                onDeleted(conversationId);
            } else {
                await goto("/chat");
                refreshConversations();
            }
        } catch (error) {
            console.error("Fehler beim Löschen:", error);
        }
    }

    $effect(() => {
        if (isOpen) {
            setTimeout(
                () => document.addEventListener("click", handleClickOutside),
                0,
            );
        } else {
            document.removeEventListener("click", handleClickOutside);
        }
    });

    onDestroy(() => {
        document.removeEventListener("click", handleClickOutside);
    });
</script>

<div class="relative menu-container">
    <button
        bind:this={buttonEl}
        onclick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            toggleMenu();
        }}
        class="p-1 rounded-full {buttonClasses} transition-colors"
        aria-label="Konversationsmenü"
    >
        <EllipsisVertical
            size={iconSize}
            class="text-light-tx-2 dark:text-dark-tx-2"
        />
    </button>

    {#if isOpen}
        <!-- position: fixed um overflow-Clipping in Tabellen/Scrollcontainern zu vermeiden -->
        <div
            class="fixed w-52 bg-light-bg dark:bg-dark-bg rounded-lg shadow-lg border border-light-ui-2 dark:border-dark-ui-2 z-50"
            style={dropdownStyle}
        >
            {#if !isRenaming && !isDeleting}
                <div>
                    <button
                        onclick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            startRenaming();
                        }}
                        class="w-full text-left px-4 py-2 rounded-t-lg text-sm text-light-tx dark:text-dark-tx hover:bg-light-ui-3 dark:hover:bg-dark-ui flex items-center gap-2"
                    >
                        <Pencil size={14} />
                        Umbenennen
                    </button>
                    <button
                        onclick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            startDeleting();
                        }}
                        class="w-full text-left px-4 py-2 rounded-b-lg text-sm text-light-re dark:text-dark-re hover:bg-red-100 dark:hover:bg-red-900/20 flex items-center gap-2"
                    >
                        <Trash2 size={14} />
                        Löschen
                    </button>
                </div>
            {:else if isRenaming}
                <div class="p-3">
                    <input
                        bind:value={newTitle}
                        type="text"
                        maxlength="100"
                        class="w-full px-2 py-1 border border-light-ui-2 dark:border-dark-ui-2 rounded text-sm bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx focus:outline-none focus:ring-1 focus:ring-blue-500"
                        onkeydown={(e) => e.key === "Enter" && confirmRename()}
                    />
                    <div class="flex gap-2 mt-2">
                        <button
                            onclick={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                confirmRename();
                            }}
                            class="flex-1 px-3 py-1 bg-blue-500 text-white text-sm rounded hover:bg-blue-600 transition-colors"
                        >
                            Speichern
                        </button>
                        <button
                            onclick={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                closeMenu();
                            }}
                            class="flex-1 px-3 py-1 border border-light-ui-2 dark:border-dark-ui-2 text-sm rounded hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors text-light-tx dark:text-dark-tx"
                        >
                            Abbrechen
                        </button>
                    </div>
                </div>
            {:else if isDeleting}
                <div class="p-3">
                    <p class="text-sm text-light-tx dark:text-dark-tx mb-3">
                        Wirklich löschen?
                    </p>
                    <div class="flex gap-2">
                        <button
                            onclick={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                confirmDelete();
                            }}
                            class="flex-1 px-3 py-1 bg-red-500 text-white text-sm rounded hover:bg-red-600 transition-colors"
                        >
                            Ja
                        </button>
                        <button
                            onclick={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                closeMenu();
                            }}
                            class="flex-1 px-3 py-1 border border-light-ui-2 dark:border-dark-ui-2 text-sm rounded hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors text-light-tx dark:text-dark-tx"
                        >
                            Nein
                        </button>
                    </div>
                </div>
            {/if}
        </div>
    {/if}
</div>

<style>
    .menu-container {
        display: inline-block;
    }
</style>
