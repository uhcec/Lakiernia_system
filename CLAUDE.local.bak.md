# CLAUDE.md — System Zarządzania Zleceniami Lakierni TUSZKO

## Cele biznesowe

System zastępuje papierową ewidencję zleceń w fabryce lakierniczej. Obsługuje pełny cykl zlecenia — od przyjęcia przez biuro, przez planowanie managera, etapy produkcyjne, aż do wydania klientowi.

Priorytety projektu (z `docs/WORKING_CONTRACT.md`):
- prawdziwy stan procesu ponad wygodne założenia UI
- trwałe niezmienniki biznesowe ponad optymistyczne zachowanie klienta
- przejrzyste ekrany operatorów ponad dekoracyjny interfejs
- małe zweryfikowane zmiany ponad szerokie przepisywania
- jawne decyzje ponad ukryte założenia

## Workflow aplikacji

Szczegóły: @docs/WORKFLOW.md | Pytania otwarte: @docs/WORKFLOW_VALIDATION_CHECKLIST.md | Realia fabryczne: @docs/FACTORY_USAGE_NOTES.md

### Role i panele

| Route | Stacja (`X-Station-Id`) | Rola |
|---|---|---|
| `/zlecenia` | `OFFICE` | Biuro — przyjęcie, wydanie |
| `/kierownik` | `MANAGER` | Kierownik — planowanie, kolejka |
| `/przygotowanie` | `SURFACE_PREPARATION` | Przygotowanie powierzchni |
| `/zawieszanie` | `HANGING` | Zawieszanie (automaty) |
| `/produkcja-reczna` | `MANUAL_PRODUCTION` | Produkcja ręczna |
| `/produkcja-automat` | `AUTOMATIC_PRODUCTION` | Produkcja automatyczna |
| `/pakowanie` | `PACKING` | Pakowanie / kontrola jakości |
| `/produkcja-decoral` | `DECORAL_PRODUCTION` | Produkcja Decoral |
| `/audyt` | — | Podgląd administracyjny |

### Ścieżki produkcji

```
RAL + MANUAL:     SURFACE_PREPARATION → PRODUCTION → PACKING
RAL + AUTOMATIC:  SURFACE_PREPARATION → HANGING → PACKING
DECORAL + MANUAL: SURFACE_PREPARATION → PRODUCTION → PACKING → DECORAL_PRODUCTION
DECORAL + AUTO:   SURFACE_PREPARATION → HANGING → PACKING → DECORAL_PRODUCTION
PRZEMALOWANKA:    → PRODUCTION lub HANGING → PACKING [pomija SURFACE_PREPARATION]
```

`process_status` jest backendową wartością pochodną — nigdy nie jest ręcznie edytowaną kolumną.

### Poprawki (corrections)

- Pakowanie tworzy dziecko `is_correction=true`, `queue_namespace=CORRECTIONS`
- Dziecko pomija `SURFACE_PREPARATION`; manual startuje od `PRODUCTION`, automatyczne od `HANGING`
- Rodzic czeka na zamknięcie wszystkich potomków przed `READY`
- Reguła ilościowa: `ok_quantity + correction_quantity == counted_quantity`
- Packing wymaga: powodu poprawki + podziału na profile/akcesoria
- Kategorie powodów: `niedomalowanie`, `za grubo`, `wtrącenia`, `inne`

### Reguły READY

Zlecenie jest READY tylko gdy:
1. `completed_quantity == total_quantity`
2. `current_active_quantity == 0`
3. Brak otwartych poprawek-potomków
4. Nie oznaczone jako niekompletne na przyjeciu

### Kolejka globalna

Jedna globalna kolejka dla wszystkich zaplanowanych zleceń — nie dzielona po typie produkcji ani stacji. Poprawki nie dostają automatycznego priorytetu. Zakończone/READY wiersze schodzą za aktywne pozycje planowania.

## Zasady architektury

### Stack

- **Backend:** FastAPI + SQLAlchemy (sync) + Alembic + SQLite + Uvicorn
- **Frontend:** React + TypeScript + Vite + Tailwind CSS + Lucide icons
- **Transport stacji:** nagłówek `X-Station-Id` — backend parsuje i odrzuca złe akcje 403

### Struktura katalogów

```
app/
  work_orders/   — przyjęcie, modele, schematy, serwis, workflow
  process/       — etapy produkcji, modele, serwis, repozytoria
  manager/       — planowanie, kolejka, statystyki
  paints/        — kartoteka farb, stany magazynowe, ruchy
  audit/         — zdarzenia audytowe, repozytoria, router
  shared/        — enumy, wyjątki, kontekst żądania
  database/      — baza, sesja, modele bazowe
frontend/src/
  pages/         — jedna strona = jeden panel stanowiskowy
  components/    — współdzielone komponenty UI
```

### Zasady backendowe

- `process_status` jest wyliczany z persystowanych wielkości, nie edytowany ręcznie
- Akcje etapów są **idempotentne** — powtórzenie nie aplikuje efektów dwa razy
- Równoległe żądania zakończone konfliktem zwracają `409`, nigdy `500`
- Zasoby fizyczne (`HANGING`, `AUTOMATIC_LINE`) modelowane przez blokady backendowe
- Stan magazynu farb nigdy nie może spaść poniżej zera
- Zdarzenia audytowe zapisywane **w tej samej transakcji** co mutacja

### Zasady frontendowe

- Frontend wyświetla `process_status` z backendu — **nie wylicza workflow** po stronie klienta
- Zakończone/historyczne widoki **nigdy** nie pokazują aktywnych liczników (`Postęp partii`, `current_active_quantity`)
- `X-Station-Id` pochodzi z trasy panelu — operator go nie wpisuje
- Widoki historyczne: `Poprawiono X z Y szt.` — nie `0 / X`

## Konwencje kodowania

### Backend (Python)

- Python ≥ 3.12, Pydantic v2, SQLAlchemy 2.x (sync)
- Repozytoria — dostęp do bazy; serwisy — logika biznesowa; routery — walidacja HTTP
- Migracje wyłącznie przez Alembic (`python -m alembic upgrade head`)
- Przed nową migracją: `python -m alembic check` musi przejść
- Testy w `tests/` — pytest; skupione testy przed szeroką regresją

### Frontend (TypeScript/React)

- Jeden plik strony = jeden panel stanowiskowy
- Mutacje wysyłają `X-Station-Id` przez hook API
- Nie dodawać logiki workflow po stronie klienta — trust backend
- Testy: `npm run test`; build: `npm run build`

### Nazewnictwo

- Polskie etykiety UI dla operatorów (`Zlecenia`, `Na produkcji`, `Gotowe`)
- Angielskie nazwy w kodzie, API, enumeracjach

## Ważne decyzje techniczne

### Źródło prawdy (kolejność)

1. `docs/WORKFLOW.md` — semantyka przepływu biznesowego
2. Backend: serwisy, migracje, testy — zaimplementowane zachowanie
3. Kod frontendu — wyłącznie prezentacja

Jeśli źródła się nie zgadzają — zatrzymaj się i zapytaj.

### Farby i magazyn

Szczegóły: @docs/PAINT_SYSTEM_DEFINITION_DRAFT_PL.md

- `paint_stock_snapshot_quantity_kg` na zleceniu = historyczny snapshot, **nie** live stock
- Live stock pochodzi z ruchów magazynowych (`paints/`)
- Tworzenie zlecenia **nie robi rezerwacji** stanu
- Automat wpisuje `consumed_paint_quantity_kg` — zapis natychmiast zmniejsza stan
- Pakowanie automatycznego zlecenia **zablokowane** bez wpisanego zużycia farby

### Tożsamość stacji i uprawnienia

Szczegóły: @docs/STATION_IDENTITY_AND_AUDIT.md

- Obecny model: współdzielona tożsamość przez `X-Station-Id` (rollout)
- Docelowy model: loginy produkcyjne do kontekstu stacji, indywidualne loginy biurowe
- Backend odrzuca złe akcje stacji przez `403`
- `SYSTEM` i `UNKNOWN` to tymczasowe tożsamości kompatybilności

### Ilości: profile i akcesoria

- Gdy oba znane: `profiles_quantity + accessories_quantity == total_quantity`
- Nieznany podział: `*_to_count = True`, `NULL` dla wartości
- Poprawka pakowania wymaga jawnego podziału na profile/akcesoria sumującego się do `correction_quantity`

### Typy zleceń

| `work_order_kind` | `is_ocynk` | Zachowanie |
|---|---|---|
| `STANDARD` | false | normalne zlecenie |
| `PRZEMALOWANKA` | — | pomija SURFACE_PREPARATION, brak powiązania rodzic-dziecko |
| każdy | true | oznaczone `OCYNK` na ekranach stacji, ta sama ścieżka etapów |

## Uruchamianie i weryfikacja

Pełne instrukcje: @docs/DEVELOPMENT_RUNBOOK.md

```powershell
# Backend
uvicorn app.main:app --reload          # http://127.0.0.1:8000

# Frontend
Push-Location frontend; npm run dev; Pop-Location   # http://127.0.0.1:5173

# Quality gate
python -m pytest
python -m alembic check
Push-Location frontend; npm run test; npm run build; Pop-Location
```

Seed bazy: `python scripts/reset_and_seed_dev_db.py`

## Otwarte decyzje (nie implementować bez potwierdzenia)

- Wyłączność fizyczna pakowania (`PACKING` resource lock) — szczegóły: @docs/WORKFLOW_VALIDATION_CHECKLIST.md §9
- Szablon Excel dokumentu kontroli jakości — potrzebny plik przed implementacją
- Loginy/role/sesje użytkowników — osobny projekt
- Dokument WZ dla wydania zlecenia — potrzebny szablon
- Raport farby i obsługa automatycznych poprawek w magazynie farb
