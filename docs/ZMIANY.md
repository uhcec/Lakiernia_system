# Lista zmian — kod vs. jak fabryka ma działać

Znalezione podczas przeglądu opartego na kodzie z właścicielem **2026-06-26**. Każdy punkt: co kod robi
teraz (`plik:linia`), czego chce właściciel i dlaczego. Potwierdzone zachowanie: `docs/SPECYFIKACJA.md`.

| # | Typ | Tytuł |
|---|-----|-------|
| 1 | bug | Poprawka nie może gubić pin/pilne |
| 2 | UX | Uwidocznić drugi, osobny przebieg Decoral |
| 3 | zmiana | Gotowe zlecenia wychodzą z kolejki (zwalniają pozycję) |
| 4 | zmiana | Kierownik ustala długość zmiany (bez doradzania) ✅ |
| 5 | zmiana | Koszt zmiany koloru tylko wg wielkości (bez kierunku) ✅ |
| 6 | zmiana | Dwie reguły układania (termin → kolor) ✅ |
| 7 | zmiana | Wywalić zgadywanie jasności z kodu RAL ✅ |
| 8 | zmiana | Oznaczać kolory nieśledzone zamiast cichego OK |
| 9 | zmiana | Zapisywać faktyczną długość zmiany dla „dobrego dnia" |
| 10 | zmiana | Uwidocznić czujkę przecieku ilości |

---

### #1 — Poprawka nie może gubić pin/pilne  *(bug)*
- **Teraz:** gdy poprawka na pakowaniu odsyła zlecenie do planowania (to samo zlecenie wraca), kasuje `planning_priority` (pin/pilne) razem z linią i pozycją. `app/process/service.py:2237-2240`
- **Cel:** zlecenie ma zachować pin/pilne przez rundę poprawkową.
- **Uwaga:** baza dopuszcza blokadę planowania tylko na zleceniu zaplanowanym (`app/work_orders/models.py:71-74`), więc odesłane (niezaplanowane) zlecenie nie może jej dosłownie trzymać — zamiar priorytetu trzeba zapamiętać i ponownie nałożyć przy ponownym zaplanowaniu.

### #2 — Uwidocznić drugi, osobny przebieg Decoral  *(UX)*
- **Teraz:** gdy poprawione sztuki wracają po już zrobionym Decoralu korzenia, zakładają świeżą partię Decoral — poprawny, ale łatwy do przeoczenia „drugi przebieg". `app/process/service.py:2060-2091`
- **Cel:** pokazać operatorowi jasno, że to osobny, drugi przebieg Decoral na dosłanych sztukach. Logika zostaje; to kwestia prezentacji.

### #3 — Gotowe zlecenia wychodzą z kolejki  *(zmiana)*
- **Teraz:** zakończone (gotowe) zlecenie trzyma linię + pozycję i zostaje w kolejce jako blok na końcu; rozbudowana logika „odsuwania" tym zarządza. `app/manager/service.py:1498-1519`, `2094-2176`
- **Cel:** po zakończeniu zlecenie **opuszcza aktywną kolejkę linii i zwalnia pozycję**. Wtedy cała mechanika odsuwania jest zbędna.
- **Przed wdrożeniem:** sprawdzić, co polega na tym, że gotowe zostają w kolejce (tablica kierownika, statystyki).

### #4 — Kierownik ustala długość zmiany  *(zmiana)* — ✅ ZROBIONE 2026-06-26
- **Teraz:** gdy długość zmiany jest pominięta, system doradza długą/krótką wg dostępnej gotowej roboty. `app/manager/capacity.py:165-171`
- **Cel:** wywalić doradzanie; kierownik ustala długość dnia (długi/krótki) jawnie.
- **Zrobione:** usunięto `advise_shift_length`; `get_day_capacity`/`get_multi_day_plan` przy pominiętej długości domyślnie biorą LONG zamiast doradzać z m². Wywalono bezużyteczne już pole `shift_advised` z `DayCapacityRead`/`MultiDayPlanRead` (oraz nieużywane pole w `manager.ts`). `app/manager/capacity.py`, `app/manager/service.py`, `app/manager/schemas.py`.

### #5 — Koszt zmiany koloru tylko wg wielkości  *(zmiana)* — ✅ ZROBIONE 2026-06-26
- **Teraz:** koszt = pasmo wielkości (≤100 m² → 15 min, >100 m² → 30 min) skalowane **kierunkiem** koloru (jasny→ciemny pół, ciemny→jasny pełne). `app/manager/capacity.py:127-147`, `app/manager/colour.py:157-175`
- **Cel:** wywalić kierunek; zmiana koloru kosztuje pasmo wielkości niezależnie od kierunku.
- **Zrobione:** usunięto `CHANGEOVER_LIGHT_TO_DARK_FACTOR` i parametr `light_to_dark` z `changeover_minutes_for_transition`; koszt to teraz tylko pasmo wielkości następnego zlecenia. Wdrożone razem z #7. `app/manager/capacity.py`, `app/manager/colour.py`.

### #6 — Dwie reguły układania (termin → kolor)  *(zmiana)* — ✅ ZROBIONE 2026-06-26
- **Teraz:** trzy reguły — KOLOR, TERMIN, „maks. przerób" (najpierw największy run jednego koloru) — domyślnie kolor → termin → maks. przerób. `app/manager/enums.py:4-51`
- **Cel:** tylko **dwie** reguły (termin, kolor), domyślnie **termin → kolor**; wywalić „maks. przerób".
- **Zrobione:** usunięto `ScheduleRuleKey.CHANGEOVER` i jego wpis w katalogu oraz gałąź sortowania/`_colour_group_totals`; domyślna kolejność to teraz termin → kolor. Stare configi z kluczem `"changeover"` degradują się łagodnie (nieznane klucze są pomijane). `app/manager/enums.py`, `app/manager/scheduler.py`.

### #7 — Wywalić zgadywanie jasności z kodu RAL  *(zmiana)* — ✅ ZROBIONE 2026-06-26
- **Teraz:** jasność koloru przybliżana z kodu RAL (pierwsza cyfra + ręczne nadpisania) pod zamiatanie jasny→ciemny. `app/manager/colour.py:43-102`
- **Cel:** usunąć. Razem z #5 planowanie kolorów w ciągu dnia sprowadza się do **grupowania identycznych kolorów** (koszt = liczba zmian × 15/30 min wg wielkości).
- **Zrobione:** skasowano `ral_lightness` i tablice `_RAL_*`; `light_to_dark_order` → `group_identical_colours` (grupy alfabetycznie wg tożsamości koloru, „bez koloru" na końcu). Pola `ral_code` w `ColourOrderable`/`SequencedOrder`/`AutomaticPassObservation` (już martwe) usunięto. `app/manager/colour.py`, `app/manager/measurement.py`, `app/manager/service.py`.

### #8 — Oznaczać kolory nieśledzone zamiast cichego OK  *(zmiana)*
- **Teraz:** kolor bez historii stanu (tylko placeholder 0 kg) traktowany po cichu jako „OK" — planer nic nie twierdzi. `app/manager/paint_feasibility.py:120-133`
- **Cel:** pokazać go jako osobny widoczny stan („brak wprowadzonego stanu — wprowadź") zamiast cichego OK. (Nie da się twardo blokować na nieznanym — ale nie ma być niewidoczne.)

### #9 — Zapisywać faktyczną długość zmiany dla „dobrego dnia"  *(zmiana)*
- **Teraz:** każdy miniony dzień mierzony względem długiego dnia (800 m²/14 h), bo faktyczna długość zmiany tego dnia nie jest zapisywana. `app/manager/service.py:805-818`
- **Cel:** zapisywać faktyczną długość zmiany per dzień i mierzyć „dobry dzień" względem niej. (Łączy się z #4.)

### #10 — Uwidocznić czujkę przecieku ilości  *(zmiana)*
- **Teraz:** przy domykaniu, gdy zaliczone sztuki ≠ całość, zlecenie jest wyrównywane do całości, a ostrzeżenie trafia **tylko do logu technicznego serwera**; żaden człowiek go nie widzi. Sprawdzone na żywo 2026-06-26: przeciek 7/10 domknął się po cichu do 10/10, tylko z wpisem w logu. `app/process/service.py:2343-2350`
- **Cel:** przeciek to sygnał błędu wyżej — zostawić czujkę, ale uczynić ją **widoczną dla człowieka** (np. flaga na zleceniu), żeby dało się zbadać, zamiast cichego domknięcia. Model ilości ma w ogóle nie dopuszczać przecieków; to jest siatka bezpieczeństwa.
