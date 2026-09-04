import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { get } from "svelte/store"

vi.mock("$lib/api.js", () => ({ getSchoolYear: vi.fn() }))

import { getSchoolYear } from "$lib/api.js"

/** Frisches Modul je Test — der Store puffert absichtlich über seine Lebensdauer. */
async function frisch() {
  vi.resetModules()
  return import("./schoolYear.js")
}

beforeEach(() => vi.mocked(getSchoolYear).mockReset())
afterEach(() => vi.restoreAllMocks())

const ANTWORT = {
  schuljahr: "2026/27",
  beginn: "2026-09-14",
  ende: "2027-07-28",
  halbjahreswechsel: "2027-02-05",
}

describe("alsTagMonat", () => {
  it("macht aus dem ISO-Datum eine Knopfbeschriftung", async () => {
    const { alsTagMonat } = await frisch()
    expect(alsTagMonat("2027-07-28")).toBe("28.07.")
  })

  it("verträgt null — dann steht dort nichts", async () => {
    const { alsTagMonat } = await frisch()
    expect(alsTagMonat(null)).toBe("")
    expect(alsTagMonat(undefined)).toBe("")
  })
})

describe("passtZumSchuljahr", () => {
  it("gleiches Jahr — der Knopf erscheint", async () => {
    const { passtZumSchuljahr } = await frisch()
    expect(passtZumSchuljahr("2026/27", ANTWORT)).toBe(true)
  })

  it("verträgt beide Schreibweisen", async () => {
    // ⚠️ Der Fall, an dem ein Stringvergleich stillschweigend scheiterte: Die Config
    // schreibt `2026/27`, die Formularvorgabe `2026/2027`. Der Knopf verschwände dann
    // auf Dauer, ohne dass jemand den Grund sähe.
    const { passtZumSchuljahr } = await frisch()
    expect(passtZumSchuljahr("2026/2027", ANTWORT)).toBe(true)
  })

  it("anderes Jahr — der Knopf verschwindet", async () => {
    const { passtZumSchuljahr } = await frisch()
    expect(passtZumSchuljahr("2028/29", ANTWORT)).toBe(false)
    expect(passtZumSchuljahr("2025/26", ANTWORT)).toBe(false)
  })

  it("leeres Feld ist kein Widerspruch", async () => {
    const { passtZumSchuljahr } = await frisch()
    expect(passtZumSchuljahr("", ANTWORT)).toBe(true)
    expect(passtZumSchuljahr(null, ANTWORT)).toBe(true)
    expect(passtZumSchuljahr("keine Ahnung", ANTWORT)).toBe(true)
  })

  it("ohne geladenes Schuljahr kein Knopf", async () => {
    const { passtZumSchuljahr } = await frisch()
    expect(passtZumSchuljahr("2026/27", null)).toBe(false)
    expect(passtZumSchuljahr("2026/27", {})).toBe(false)
  })
})

describe("ladeSchuljahr", () => {
  it("füllt den Store aus der Antwort", async () => {
    vi.mocked(getSchoolYear).mockResolvedValue(ANTWORT)
    const { ladeSchuljahr, schoolYear, schuljahresEnde } = await frisch()

    expect(get(schuljahresEnde)).toBe(null)
    await ladeSchuljahr()
    expect(get(schoolYear)).toEqual(ANTWORT)
    expect(get(schuljahresEnde)).toBe("2027-07-28")
  })

  it("fragt nur einmal, auch wenn zwei Formulare gleichzeitig laden", async () => {
    vi.mocked(getSchoolYear).mockResolvedValue(ANTWORT)
    const { ladeSchuljahr } = await frisch()

    await Promise.all([ladeSchuljahr(), ladeSchuljahr(), ladeSchuljahr()])
    expect(getSchoolYear).toHaveBeenCalledTimes(1)
  })

  it("bleibt bei null, wenn die Anfrage scheitert", async () => {
    // Wichtiger als es aussieht: Der Knopf hängt an diesem Wert. Ein erfundenes
    // Ersatzdatum wäre schlimmer als kein Knopf — es sähe aus wie eine Auskunft.
    vi.mocked(getSchoolYear).mockRejectedValue(new Error("offline"))
    const { ladeSchuljahr, schuljahresEnde } = await frisch()

    await expect(ladeSchuljahr()).resolves.toBe(null)
    expect(get(schuljahresEnde)).toBe(null)
  })

  it("versucht es nach einem Fehlschlag erneut", async () => {
    vi.mocked(getSchoolYear).mockRejectedValueOnce(new Error("offline"))
    vi.mocked(getSchoolYear).mockResolvedValueOnce(ANTWORT)
    const { ladeSchuljahr, schuljahresEnde } = await frisch()

    await ladeSchuljahr()
    await ladeSchuljahr()
    expect(get(schuljahresEnde)).toBe("2027-07-28")
  })
})
