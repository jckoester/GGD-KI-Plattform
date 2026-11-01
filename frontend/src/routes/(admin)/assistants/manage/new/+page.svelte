<script>
  import { goto } from "$app/navigation";
  import { onMount } from "svelte";
  onMount(() => goto("/assistants/manage/neu", { replaceState: true }));
</script>
