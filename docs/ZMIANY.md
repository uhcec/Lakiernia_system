# Lista zmian — kod vs. jak fabryka ma działać

Znalezione podczas przeglądu opartego na kodzie z właścicielem **2026-06-26**. Każdy punkt: co kod robi
teraz (`plik:linia`), czego chce właściciel i dlaczego. Potwierdzone zachowanie: `docs/SPECYFIKACJA.md`.

| # | Typ | Tytuł |
|---|-----|-------|
| 1 | bug | Poprawka nie może gubić pin/pilne ✅ |
| 2 | UX | Uwidocznić drugi, osobny przebieg Decoral |
| 3 | zmiana | Gotowe zlecenia wychodzą z kolejki (zwalniają pozycję) ✅ |
| 4 | zmiana | Kierownik ustala długość zmiany (bez doradzania) ✅ |
| 5 | zmiana | Koszt zmiany koloru tylko wg wielkości (bez kierunku) ✅ |
| 6 | zmiana | Dwie reguły układania (termin → kolor) ✅ |
| 7 | zmiana | Wywalić zgadywanie jasności z kodu RAL ✅ |
| 8 | zmiana | Oznaczać kolory nieśledzone zamiast cichego OK ✅ |
| 9 | zmiana | Zapisywać faktyczną długość zmiany dla „dobrego dnia" ✅ |
| 10 | zmiana | Uwidocznić czujkę przecieku ilości ✅ |
| 18 | funkcja | Generowanie WZ (wydanie z magazynu) dla grupy gotowych zleceń ✅ |
| 22 | zmiana | Zużycie farby na automacie na grupę farby, podział wg m² ✅ |
| 23 | zmiana | Ostatnie zlecenie grupy czeka na wpis zużycia; kolejka pakowania; polskie komunikaty ✅ |

*(Uwaga: pozycje #11–#17 dodano tylko w angielskim `docs/CHANGES.md` (przegląd 2026-07-11) — nie przetłumaczono ich jeszcze tutaj.)*

---

### #1 — Poprawka nie może gubić pin/pilne  *(bug)* — ✅ ZROBIONE 2026-06-26
- **Teraz:** gdy poprawka na pakowaniu odsyła zlecenie do planowania (to samo zlecenie wraca), kasuje `planning_priority` (pin/pilne) razem z linią i pozycją. `app/process/service.py:2237-2240`
- **Cel:** zlecenie ma zachować pin/pilne przez rundę poprawkową.
- **Uwaga:** baza dopuszcza blokadę planowania tylko na zleceniu zaplanowanym (`app/work_orders/models.py:71-74`), więc odesłane (niezaplanowane) zlecenie nie może jej dosłownie trzymać — zamiar priorytetu trzeba zapamiętać i ponownie nałożyć przy ponownym zaplanowaniu.
- **Zrobione:** dodano `work_orders.pending_planning_priority` (migracja `20260626_0042`, bez constraintu). Replan-in-place parkuje tam żywy `planning_priority` przed wyczyszczeniem; `assign_plan` przywraca go (i czyści parking) przy ponownym zaplanowaniu. Test regresyjny `test_correction_round_remembers_and_restores_pin_NA_CHANGES1`. `app/process/service.py`, `app/manager/service.py`, `app/work_orders/models.py`.

### #2 — Uwidocznić drugi, osobny przebieg Decoral  *(UX)*
- **Teraz:** gdy poprawione sztuki wracają po już zrobionym Decoralu korzenia, zakładają świeżą partię Decoral — poprawny, ale łatwy do przeoczenia „drugi przebieg". `app/process/service.py:2060-2091`
- **Cel:** pokazać operatorowi jasno, że to osobny, drugi przebieg Decoral na dosłanych sztukach. Logika zostaje; to kwestia prezentacji.

### #3 — Gotowe zlecenia wychodzą z kolejki  *(zmiana)* — ✅ ZROBIONE 2026-06-26
- **Teraz:** zakończone (gotowe) zlecenie trzyma linię + pozycję i zostaje w kolejce jako blok na końcu; rozbudowana logika „odsuwania" tym zarządza. `app/manager/service.py:1498-1519`, `2094-2176`
- **Cel:** po zakończeniu zlecenie **opuszcza aktywną kolejkę linii i zwalnia pozycję**. Wtedy cała mechanika odsuwania jest zbędna.
- **Przed wdrożeniem:** sprawdzić, co polega na tym, że gotowe zostają w kolejce (tablica kierownika, statystyki).
- **Zrobione:** poluzowano inwariant do „pozycja wymaga linii" (linia może istnieć bez pozycji) — migracja `20260626_0043`. Przy finalizacji zlecenie zwalnia pozycję + zamek planowania, ale zachowuje linię (statystyki cięte po linii dalej działają); zakończone korekty-dzieci też zwalniają pozycje. Usunięto całą maszynerię odsuwania (`_get_completed_work_orders_requiring_trailing`, `_temporarily_move_queue_rows_out_of_the_way`, `_trail_completed_work_orders`, `_sort_queue_rows`) i jej 3 wywołania. **Decyzja właściciela** (2026-06-26): gotowe znikają też z widoków stanowisk operatora. `app/process/service.py`, `app/manager/service.py`, `app/work_orders/models.py`.

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

### #8 — Oznaczać kolory nieśledzone zamiast cichego OK  *(zmiana)* — ✅ ZROBIONE 2026-06-26
- **Teraz:** kolor bez historii stanu (tylko placeholder 0 kg) traktowany po cichu jako „OK" — planer nic nie twierdzi. `app/manager/paint_feasibility.py:120-133`
- **Cel:** pokazać go jako osobny widoczny stan („brak wprowadzonego stanu — wprowadź") zamiast cichego OK. (Nie da się twardo blokować na nieznanym — ale nie ma być niewidoczne.)
- **Zrobione:** dodano `PaintFeasibilityStatus.STOCK_NOT_ENTERED`. Zlecenie z kolorem bez wiersza stanu lub tylko z placeholderem 0 kg dostaje ten status (lista `stock_not_entered_order_ids`); nigdy nie jest twardo blokowane. Zlecenie bez koloru zostaje OK. `app/manager/paint_feasibility.py`, `app/manager/schemas.py`, `app/manager/service.py`.

### #9 — Zapisywać faktyczną długość zmiany dla „dobrego dnia"  *(zmiana)* — ✅ ZROBIONE 2026-06-26
- **Teraz:** każdy miniony dzień mierzony względem długiego dnia (800 m²/14 h), bo faktyczna długość zmiany tego dnia nie jest zapisywana. `app/manager/service.py:805-818`
- **Cel:** zapisywać faktyczną długość zmiany per dzień i mierzyć „dobry dzień" względem niej. (Łączy się z #4.)
- **Zrobione:** nowa tabela + model `day_shift_lengths` (migracja `20260626_0044`); endpointy `GET/PUT /manager/day-shift-length?day=…` do odczytu/zapisu długości zmiany dnia (audytowane). `get_good_day_stats` mierzy każdy dzień względem zapisanej zmiany (próg 800/500, godziny 14/8), domyślnie LONG gdy brak. `app/manager/models.py`, `app/manager/repository.py`, `app/manager/service.py`, `app/manager/router.py`, `app/manager/schemas.py`.

### #10 — Uwidocznić czujkę przecieku ilości  *(zmiana)* — ✅ ZROBIONE 2026-06-26
- **Teraz:** przy domykaniu, gdy zaliczone sztuki ≠ całość, zlecenie jest wyrównywane do całości, a ostrzeżenie trafia **tylko do logu technicznego serwera**; żaden człowiek go nie widzi. Sprawdzone na żywo 2026-06-26: przeciek 7/10 domknął się po cichu do 10/10, tylko z wpisem w logu. `app/process/service.py:2343-2350`
- **Cel:** przeciek to sygnał błędu wyżej — zostawić czujkę, ale uczynić ją **widoczną dla człowieka** (np. flaga na zleceniu), żeby dało się zbadać, zamiast cichego domknięcia. Model ilości ma w ogóle nie dopuszczać przecieków; to jest siatka bezpieczeństwa.
- **Zrobione:** dodano trwałą flagę `work_orders.quantity_leak_flagged` (migracja `20260626_0041`), ustawianą w czujce przy domykaniu, wystawioną w `WorkOrderRead` (biuro + kierownik) oraz zdarzenie audytu SYSTEM `work_order.quantity_leak_detected`. Zlecenie nadal domyka się do całości (żeby robota nie utknęła), ale przeciek nie jest już cichy. `app/process/service.py`, `app/work_orders/models.py`, `app/work_orders/schemas.py`.

### #18 — Generowanie WZ (wydanie z magazynu)  *(funkcja, 2026-07-11)* — ✅ ZROBIONE 2026-07-11
- **Cel:** biuro chce przycisk „Generuj WZ", który w dowolnej chwili tworzy dokument wydania (PDF) dla wybranej grupy gotowych zleceń jednego klienta (domyka dawną pozycję z listy zadań „WZ + wydanie klientowi").
- **Decyzje właściciela (2026-07-11):** najpierw klient → zaznaczenie jego zleceń GOTOWYCH i jeszcze niewydanych; wiersze automatycznie z danych zlecenia (liczby profili/akcesoriów + RAL; zlecenie bez znanego podziału → jeden wiersz „Elementy"); **jedyne** pole ręczne to liczba załadowanych „Kosze dłużycowe"; w NR ZAMÓWIENIA **oba** numery (klienta i nasz); adres odbiorcy zostaje pusty (dopisywany ręcznie); numer WZ automatyczny rocznie „kolejny/rok" (1/2026…); **bez** zapisywania dokumentów (jednorazowy wydruk, dziury przy ponownym druku akceptowane); wygenerowanie WZ **nie** oznacza zleceń jako wydane (osobny krok).
- **Zrobione:** szablon `app/static/templates/wydanie_z_magazynu.xlsx` (zbudowany z pliku właściciela, czcionki/ramki 1:1, przez `scripts/build_wz_template.py`); `WorkOrderService.generate_wz_document` + `WzNumberAllocator` + tabela `wz_number_counters` (migracja `20260711_0045`); endpoint `POST /work-orders/wz-document` (tylko biuro); front `GenerateWzModal` + przycisk „Generuj WZ" na liście biura. Wspólny konwerter Excel→PDF sparametryzowano (wyróżnienie D6 karty jakości za `emphasize_cell=`), a nieudany render zwraca to samo kontrolowane polskie 503 co karta jakości (#17) i cofa numer WZ. Testy w `tests/test_wz_document.py`; układ obejrzany na realnym renderze. Zob. `docs/DECISIONS.md` (2026-07-11 — #18) i `docs/REVIEW_LEDGER.md` #8. `app/work_orders/service.py`, `app/work_orders/wz_number_allocator.py`, `app/work_orders/models.py`, `app/work_orders/schemas.py`, `app/work_orders/router.py`, `frontend/src/components/GenerateWzModal.tsx`, `frontend/src/pages/WorkOrdersListPage.tsx`, `frontend/src/api/workOrdersApi.ts`.

### #21 — Reset administracyjny ukończonego zlecenia czyni je niewidocznym na obu listach planowania  *(błąd, znaleziony na żywo 2026-07-11, naprawa odłożona — właściciel prosił, żeby tylko zapisać)*
- **Teraz:** `ProcessService.administrative_reset` (`app/process/service.py:537-594`) resetuje wiersze
  etapów, partie, `completed_quantity` i flagę przecieku, ale celowo **zachowuje plan**
  (`production_type` + `queue_position` nietknięte) — docstring zakłada, że zlecenie jest przez to
  „znów zaplanowane" (`app/process/service.py:543-544`). To prawda tylko wtedy, gdy zlecenie wciąż
  trzymało pozycję w kolejce. Gdy resetujemy zlecenie **po ukończeniu**, finalizacja już zwolniła slot
  (`queue_position` → NULL, linia zostaje — ZMIANY #3/#12), więc po resecie ma ustawione
  `production_type`, a `queue_position` = NULL. `get_display_status` zwraca wtedy `TO_BE_PLANNED`
  (`_is_planned` wymaga **obu** niepustych, `app/process/service.py:1218-1219`), ale **żadna** lista
  planowania go nie zwraca: zapytanie niezaplanowanych wymaga `production_type IS NULL`
  (`app/manager/repository.py:80-81`), a zapytanie zaplanowanych wymaga `queue_position IS NOT NULL`
  (`app/manager/repository.py:98-99`). Efekt: zlecenie znika z „Do zaplanowania" i z kolejki
  zaplanowanych — dokładnie objaw właściciela na zleceniu **0001** (reset 2026-07-11 ~21:20, po tym jak
  ~21:16 doszło do PACKING DONE). Zlecenie nie jest utracone (nadal czytelne pod `GET /work-orders/1`),
  tylko niemożliwe do zaplanowania z tablicy kierownika.
- **Cel:** decyzja właściciela co do kształtu naprawy (NIE zrobione — właściciel prosił tylko o zapis).
  Warianty: (a) przy resecie, jeśli zlecenie ma linię, ale nie ma pozycji, wyczyścić też
  `production_type` (i ewentualny `planning_priority`), by wróciło do prawdziwej puli niezaplanowanych i
  pokazało się w „Do zaplanowania" — zgodnie z tym, czego właściciel tu oczekiwał; albo (b) dopisać je z
  powrotem do kolejki jego linii (przywrócić `queue_position`), by trafiło do kolejki zaplanowanych,
  zgodnie z intencją docstringa „zachowuje plan". Tak czy inaczej rozważyć zamknięcie stanu limbo
  linia-jest/pozycja-NULL/niekompletne, żeby żadne zlecenie nie mogło wpaść między dwa zapytania list.

### #22 — Zużycie farby na automacie na grupę farby, podział wg m²  *(zmiana, prośba właściciela 2026-10-09)* — ✅ ZROBIONE 2026-10-09
- **Było:** stanowisko Produkcja automat wpisywało zużycie farby **na każde zlecenie** (kartony − resztka)
  po starcie zawieszania; raz a dobrze; pakowania nie dało się zakończyć bez tego wpisu.
- **Cel (właściciel):** zlecenia w tej samej farbie tworzą grupę; zużycie wpisuje się raz po całej grupie,
  a nie na zlecenie — zużycia na jedno zlecenie nie da się zmierzyć (operator nie wymienia kartonów między
  zleceniami w tej samej farbie). Szczegóły i każda poddecyzja: `docs/DECISIONS.md` (2026-10-09 — #22).
- **Zrobione:** grupy tworzą się same z kolejności zawieszania na automacie; jeden wpis (raz a dobrze) na
  grupę na stanowisku Produkcja automat, gdy jej zlecenia skończyły zawieszanie; jeden ruch magazynowy na
  grupę; kg dzielone na zlecenia wg m²; pakowanie nie czeka na farbę; otwarta grupa niczego nie blokuje i
  świeci się na czerwono (stanowisko + panel kierownika), gdy farba jest już zmieniona. Migracja
  `20261009_0046`. Testy `tests/test_paint_runs_changes22.py`, frontend `PaintRunsPanel`. Sprawdzone na
  działającym backendzie. SPECYFIKACJA §3/§4/§10 zaktualizowana.

### #23 — Ostatnie zlecenie grupy czeka na wpis zużycia; kolejka pakowania  *(zmiana + błąd, właściciel 2026-10-09)* — ✅ ZROBIONE 2026-10-09
- **Znalezione:** odtworzenie testu właściciela z dziennika (zdarzenia 57-75): (1) zakleszczenie pakowania —
  zwolnione stanowisko po 0001 wzięło 0009 (dopiero zawieszane) zamiast czekającego 0005, więc 0005 nie
  mogło się spakować, a 0009 skończyć zawieszania aż do „drugiego stanowiska”; (2) grupy 3 nie dało się
  zamknąć — farba miała 0 kg na stanie; (3) angielski komunikat dla operatora.
- **Decyzje właściciela:** (a) zwolnione pakowanie → zlecenie czekające najdłużej; (b) zasada linii automatu
  zostaje; (c) bez stanu farby wpis dalej odrzucany, stan widoczny od razu; nowe: ostatnie zlecenie grupy nie
  może się zamknąć bez wpisu zużycia, a linia ma iść dalej.
- **Zrobione:** zaparkowane pakowanie ostatniego zlecenia (zamyka się samo po wpisie, albo od razu, gdy
  dołączy zlecenie w tej samej farbie), zaparkowane zwalnia stanowisko i linię; kolejka pakowania wg
  czekania; stan farby na karcie grupy; polskie komunikaty. Migracja `20261009_0047`. Testy w
  `tests/test_paint_runs_changes22.py`. Odtworzony przebieg właściciela na kopii bazy: bez obejścia.

### #24 — Ilość zgłoszona a przyjęta zostaje widoczna; nadwyżka dokładana do zlecenia  *(zmiana, właściciel 2026-10-15)* — ✅ ZROBIONE 2026-10-15
- **Znalezione (na żywo, zlecenie 0002 · RAL 9005 · 14 m² · Aluminco):** zgłoszono 14 (12 profili + 2
  akcesoria), przygotowanie policzyło 10. Wg D5 zlecenie zamknęło się jako 10/10, a jedyny ślad „14” był w
  dzienniku, którego żaden ekran nie czyta; dotychczasowy znaczek „RÓŻNICA” liczył od już przepisanej
  całości, więc znikał akurat przy zamknięciu. Nadwyżka (więcej sztuk niż zgłoszono) była odrzucana.
- **Decyzje właściciela:** reszta bez zmian; pokazać status „MNIEJ NIŻ ZGŁOSZONO: 10 z 14” (wariant A); ta
  sama zasada na plus, a nadwyżkę dokładamy do zlecenia; metry zostają jak zgłoszone (biuro się tym zajmie);
  biuro/kierownik mogą odhaczyć „wyjaśnione” (znaczek znika z list, linijka w szczegółach zostaje), z
  możliwością cofnięcia.
- **Zrobione:** zgłoszona ilość i podział zapisane na zleceniu przy pierwszym przepisaniu; różnica liczona
  od zgłoszonej; nadwyżka powiększa zlecenie i partię przy zakończeniu przygotowania (tylko zwykłe
  przyjęcie); `PATCH /work-orders/{id}/quantity-discrepancy` (biuro/kierownik), zapisuje stanowisko, czas i
  audyt. Znaczek na liście biura (wcześniej nie miała znaczków ostrzegawczych), w panelu kierownika i w
  szczegółach; linijka „Zgłoszono · Przyjęto · Brak/Nadwyżka” + przycisk. Migracja `20261015_0048`
  (odtwarza zgłoszoną ilość z dziennika — 0002 od razu pokazuje „10 z 14”). Testy
  `tests/test_declared_quantity_changes24.py` + `frontend/tests/workOrderDisplay.test.ts`. Sprawdzone na
  żywym serwerze: 0002 odtworzone; zlecenie na automacie 14→16 przez czekanie na zużycie farby zamknęło
  się GOTOWE 16/16, bez flagi przecieku, 14 m². SPECYFIKACJA §4; DECISIONS 2026-10-15.

### #25 — Niedobór na Decoralu zalicza nieistniejące sztuki  *(błąd, znaleziony 2026-10-15 przy #24)* — ✅ ZROBIONE 2026-10-15
- **Teraz:** zlecenie DECORAL, gdzie przygotowanie policzyło mniej niż zgłoszono (5 zgłoszone, 3 policzone,
  3 spakowane OK), kończy przebieg Decoral zaliczając wielkość partii (`completed += current_active_quantity`
  w `finish_stage`, gałąź DECORAL_PRODUCTION) — partia dalej ma 5, więc zlecenie zamyka się GOTOWE **5/5**,
  choć sztuk jest 3; przepisanie D5 się nie uruchamia, flaga przecieku też nie. Odtworzone testem
  jednorazowym 2026-10-15. Zlecenia RAL nie są dotknięte. Od #24 znaczek i tak pokazuje „MNIEJ NIŻ
  ZGŁOSZONO: 3 z 5”, ale liczba sztuk zlecenia — i to, co z niej drukowane, np. „Elementy” na WZ — mówi 5.
- **Chcemy:** zaliczyć tylko sztuki, które przyjechały (zmniejszyć partię do policzonej przed Decoralem albo
  zaliczać `min(partia, policzone)`), żeby zlecenie domknęło się ścieżką D5 na 3. Najpierw test regresji z
  poprawkami Decoral.
- **Zrobione (właściciel: „napraw to od razu”):** przyczyną była partia, nie samo zaliczanie na Decoralu — po
  przygotowaniu partia dalej miała zgłoszoną wielkość. Zakończenie przygotowania ustawia teraz partię na
  policzoną liczbę w obie strony (`_apply_intake_count`, które robi też dokładanie nadwyżki z #24); ponowne
  liczenie ją wyrównuje. Testy `..._CHANGES25` w `tests/test_declared_quantity_changes24.py` — padały przed
  poprawką, przechodzą po niej.

### #26 — Gotowe zlecenie można było zaplanować ponownie (zombie w kolejce)  *(błąd, znaleziony przez generator scenariuszy 2026-10-15)* — ✅ ZROBIONE 2026-10-15
- **Było:** plan gotowego zlecenia przechodził i dawał mu pozycję w kolejce, wbrew ZMIANIE #3 (gotowe zlecenie
  schodzi z kolejki) — także dla zwykłego 6/6, niezależnie od #24/#25. Przesuwanie i przypinanie już
  odrzucały gotowe zlecenia, planowanie nie.
- **Zrobione:** planowanie odrzuca gotowe zlecenie (409, polski komunikat). Test regresji
  `test_completed_order_cannot_be_planned_again_CHANGES26`; generator scenariuszy przechodzi.

### #27 — Zawieszanie pogrupowane po farbie  *(zmiana, szkic właściciela z tablicy 2026-10-15)* — ✅ ZROBIONE 2026-10-15
- **Było:** zawieszanie używało wspólnego ekranu etapów — duża karta na zlecenie (pozycja, status, etykiety,
  m²/farba/sztuki, rysunki, postęp partii, opis poprawki) i filtry Wszystkie/Zwykłe/Poprawki.
- **Chcemy (właściciel):** zwarta lista pogrupowana po farbie — nagłówek RAL · producent · kod farby,
  wiersze firma · m² · numer · Szczegóły · Rozpocznij. Odpowiedzi: bez pola mat/połysk (wynika z kodu
  farby); grupy idą za kolejką kierownika (a); przycisk przy każdym zleceniu; bez podsumowania grupy;
  kolejność wg kolejki; wiersz wg mojej propozycji (sztuki + POPRAWKA/NIEPEŁNE w wierszu, rysunki pod
  Szczegóły, zakończone zwinięte z Cofnij, bez filtrów).
- **Zrobione:** osobny `HangingPage` (pozostałe stanowiska bez zmian) + `groupHangingQueue` (kolejne
  zlecenia z tą samą farbą = RAL + producent + kod; bez kodu → nie grupujemy). Gdy jedno się wiesza,
  pozostałe „Rozpocznij” są wyszarzone „Zawieszanie zajęte” (backend i tak odmawia — 409 sprawdzone na
  żywo). Zostawione też etykiety PRZEMALOWANKA/OCYNK/DECORAL (były na starej karcie); usunięte AUTOMAT
  (tu wszystko jest automatem). Testy `frontend/tests/hangingGroups.test.ts`; zrzuty z działającej aplikacji.

### #28 — Cofnięcie startu zawieszania zostawia pakowanie „w trakcie” i zajęte miejsce pakowania  *(błąd, znaleziony 2026-10-15 przy #27)* — OTWARTE
- **Teraz:** dla zlecenia na automat cofnięcie zawieszania z „w trakcie” (`reopen_stage` → NOT_STARTED)
  wraca zawieszanie i wyjmuje zlecenie z grupy farby, ale pakowanie (ruszyło przy starcie zawieszania)
  zostaje „w trakcie”, a miejsce pakowania zostaje zajęte. Widziane na żywo na 0001 (baza deweloperska).
  Z ekranu zawieszania nieosiągalne (w trakcie jest tylko „Zakończ”); przez API tak.
- **Chcemy:** prawdopodobnie cofnąć też pakowanie i zwolnić miejsce — najpierw zapytać właściciela, czy na
  hali start zawieszania w ogóle da się „odwołać” (naprawić czy zabronić). Najpierw test regresji.
