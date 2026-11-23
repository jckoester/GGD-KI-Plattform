/**
 * Die Einträge der Token-Liste im Profil, getrennt (0.55, Päckchen AX Schritt 5, F11):
 *
 * - **Verbundene Programme** — Verbindungen per OAuth (`oauth_client_id`), nur die aktiven.
 *   Ein neues Verbinden ersetzt die alte Verbindung; die ersetzten und beendeten zu zeigen,
 *   füllte die Liste mit Einträgen, mit denen niemand etwas anfangen kann.
 * - **Eigene Zugangstoken** — wie bisher, auch beendete und abgelaufene (matt).
 */
export function aufteilen(eintraege, jetzt = new Date()) {
  const programme = [];
  const eigene = [];
  for (const e of eintraege) {
    if (!e.oauth_client_id) eigene.push(e);
    else if (!e.revoked_at && new Date(e.expires_at) > jetzt) programme.push(e);
  }
  return { programme, eigene };
}
