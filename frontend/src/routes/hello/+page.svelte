<script>
  import { onMount } from 'svelte'
  import { goto } from '$app/navigation'
  import { logout, getMe } from '$lib/api.js'

  let user = null

  onMount(async () => {
    try {
      user = await getMe()
    } catch {
      goto('/')
    }
  })

  async function handleLogout() {
    await logout()
    goto('/')
  }
</script>

{#if user}
  <h1>Hallo!</h1>
  <p>Pseudonym: {user.pseudonym}</p>
  <p>Rolle: {user.role}</p>
  {#if user.grade}
    <p>Klasse: {user.grade}</p>
  {/if}
  <button on:click={handleLogout}>Abmelden</button>
{:else}
  <p>Lade…</p>
{/if}
