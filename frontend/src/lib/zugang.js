import { get } from "svelte/store";

import { getMe } from "$lib/api.js";
import { user } from "$lib/stores/user.js";

/**
 * Die angemeldete Person für Wächter in `+page.js` — wartet, statt `null` zu melden.
 *
 * ⚠️ **Warum es das braucht (0.27, Schritt 9):** Den Store `user` füllen die Layouts im
 * `onMount`, also **nach** den `load`-Funktionen der Seiten. Ein Wächter mit `get(user)` sah
 * deshalb beim Neuladen oder über einen Link `null` und schickte Admins weg — nach `/` oder
 * `/assistants`. Über die Seitenleiste ging es, weil der Store dann schon gefüllt war.
 *
 * Ist der Store leer, holt diese Funktion `/auth/me` selbst und füllt ihn (dieselbe Form wie
 * die Layouts; die Einstellungen ergänzt das Layout danach). Gleichzeitige Aufrufe teilen
 * sich eine Anfrage. Scheitert sie, ist das Ergebnis `null` — der Wächter leitet dann um,
 * und das Layout schickt eine nicht angemeldete Person ohnehin zur Anmeldung.
 *
 * @param {{ holen?: () => Promise<object> }} [optionen]  für Tests
 * @returns {Promise<object|null>}
 */
let laufend = null;

export async function nutzer({ holen = getMe } = {}) {
  const da = get(user);
  if (da) return da;
  laufend ??= holen()
    .then((me) => {
      if (!get(user)) {
        user.set({
          ...me,
          display_name:
            me.display_name ?? globalThis.sessionStorage?.getItem("display_name") ?? me.pseudonym,
        });
      }
      return get(user);
    })
    .catch(() => null)
    .finally(() => {
      laufend = null;
    });
  return laufend;
}

/** Hat die angemeldete Person eine dieser Rollen? */
export async function hatRolle(...rollen) {
  const n = await nutzer();
  return (n?.roles ?? []).some((r) => rollen.includes(r));
}
