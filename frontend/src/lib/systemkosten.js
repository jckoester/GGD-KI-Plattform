/**
 * Die Zeile „System" unter `/budget` und `/statistics/costs` (0.12, AP3).
 *
 * Was die Plattform für sich selbst verbraucht — heute allein Einbettungen. Der Betrag
 * ist winzig; gezeigt wird er, damit „klein" gewusst und nicht angenommen wird. Er ist
 * keinem Nutzerbudget angerechnet und steht deshalb neben den Zahlen, nicht in ihnen.
 */
import { betrag } from "./kostendiagramm.js";

export const SYSTEM_BESCHREIBUNG = "Einbettungen für Suche und Import";

/** „0,0012 € in 1.234 Anfragen" — oder „keine Anfragen". */
export function systemText(eur, anfragen) {
    if (!anfragen) return "keine Anfragen";
    const wort = anfragen === 1 ? "Anfrage" : "Anfragen";
    return `${betrag(eur, "€")} in ${anfragen.toLocaleString("de-DE")} ${wort}`;
}
