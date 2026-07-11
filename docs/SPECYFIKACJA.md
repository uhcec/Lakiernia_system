# System lakierni — specyfikacja domenowa (odtworzona)

**Status:** odtworzona z kodu i przejrzana punkt po punkcie z właścicielem **2026-06-26**.
**Metoda (wg `CLAUDE.md`):** każda linijka jest oparta na kodzie (`plik:linia`) **i** potwierdzona przez
właściciela. `✅` = potwierdzone jako zgodne z fabryką. `⚠️ ZMIANA #n` = kod tak robi dzisiaj, ale
właściciel chce to zmienić — patrz `docs/ZMIANY.md`; **nie traktuj obecnego zachowania jako docelowego.**

Ten plik opisuje **co kod robi dzisiaj**. To nowa baza prawdy, zastępująca skasowaną dokumentację.

---

## 1. Model danych i niezmienniki

- ✅ Zlecenie ma dodatnią ilość; ilość zakończona mieści się między 0 a całkowitą. `app/work_orders/models.py:52-54`
- ✅ Zlecenie „zaplanowane" = ma **pozycję w kolejce**; pozycja wymaga linii, ale linia może istnieć **bez** pozycji — gotowe zlecenie opuszcza aktywną kolejkę (pozycja → NULL), zachowując linię (ZMIANA #3). `app/work_orders/models.py:61-64`
- ✅ Zlecenie niekompletne po przyjeździe nie może być zaplanowane. `app/work_orders/models.py:65-68`
- ✅ Pozycja w kolejce jest unikalna **per linia** (ręczna/automat); pozycja 1 istnieje na obu liniach niezależnie. `app/work_orders/models.py:97-105`
- ✅ Blokada planowania (pin/pilne) może istnieć tylko na zleceniu zaplanowanym. `app/work_orders/models.py:71-74`
- ✅ Gdy znane są ilości profili i akcesoriów, muszą sumować się do całkowitej. `app/work_orders/models.py:75-86`
- ✅ Folię Decoral można przypisać tylko zleceniu DECORAL. `app/work_orders/models.py:87-90`
- ✅ Zlecenie poprawkowe musi mieć rodzica i żyje w przestrzeni kolejki CORRECTIONS. `app/work_orders/models.py:91-96`
- ✅ Zlecenie ma w danej chwili co najwyżej jedną aktywną partię. `app/process/models.py:69-75`
- ✅ Pięć etapów (przygotowanie powierzchni, zawieszanie, produkcja, produkcja Decoral, pakowanie); trzy statusy (nie rozpoczęte, w trakcie, zakończone). `app/process/enums.py:82-97`
- ✅ Powłoka = RAL/DECORAL; produkcja = ręczna/automat; rodzaj = standard/przemalowanka. `app/process/enums.py:47-62`, `app/shared/enums.py:69-71`
- ✅ Przejścia etapów zapisywane są w stałym dzienniku (tylko dopisywanie; zasila statystyki). Dziś każda akcja idzie pod **wspólną tożsamością stacji** — nie ma loginu osoby; pole „kto" zostawione na przyszłość. `app/process/models.py:95-126`

## 2. Przyjęcie (biuro)

- ✅ Numer zlecenia = jeden **globalny licznik 4-cyfrowy** (`0001`, `0002`…), **nie** resetowany rocznie. `app/work_orders/number_allocator.py:11-39`
- ✅ Wymagane przy tworzeniu: klient, RAL + kod farby + producent, technologia, data przyjęcia, **data odbioru**, powierzchnia (>0). `app/work_orders/schemas.py:154-177`
- ✅ Ilość domyślnie 1. `app/work_orders/schemas.py:157`
- ✅ Dla profili i akcesoriów podajesz **albo** ilość, **albo** „do policzenia na produkcji", nigdy oba/żadne. `app/work_orders/schemas.py:128-132`
- ✅ Utworzenie zlecenia zapisuje **migawkę stanu farby** (kg w tej chwili). `app/work_orders/service.py:202-206`
- ✅ Tylko biuro tworzy zlecenia / zarządza załącznikami / odznacza „kompletne"; biuro lub kierownik edytuje. `app/work_orders/service.py:637-642`, `258-262`
- ✅ Lista biura **nie pokazuje** poprawek „P…". `app/work_orders/service.py:371-374`
- ✅ Status zlecenia jest **wyliczany** z postępu, nigdy ustawiany ręcznie. `app/work_orders/service.py:166-174`
- ✅ „Po terminie" = data odbioru przed dziś ORAZ zlecenie jeszcze nie gotowe. `app/work_orders/service.py:793-797`
- ✅ „Wydane klientowi" można ustawić tylko dla gotowego zlecenia. `app/work_orders/service.py:447-457`
- ✅ Załączniki: tylko PDF / PNG / JPG, limit rozmiaru z konfiguracji. `app/work_orders/service.py:150-154`

## 3. Przepływ etapów i trasa

- ✅ Trasa wynika z powłoki + linii: przygotowanie → (zawieszanie, chyba że ręczna) → produkcja → pakowanie → (Decoral, jeśli DECORAL). `app/process/service.py:88-102`
- ✅ Ręczna nie ma zawieszania; automat nie ma produkcji (linia maluje sama). `app/process/service.py:96-98`, `1450-1454`
- ✅ Przemalowanka pomija przygotowanie powierzchni; poprawki pomijają przygotowanie. `app/process/service.py:1467-1469`, `1461-1465`
- ✅ Dozwolone ruchy statusu: nie rozpoczęte→w trakcie; w trakcie→{zakończone, nie rozpoczęte}; zakończone→{w trakcie, nie rozpoczęte}. `app/process/service.py:1290-1299`
- ✅ Etap nie ruszy, dopóki poprzedni nie jest zakończony. `app/process/service.py:1301-1308`
- ✅ Zlecenia w pełni gotowego nie da się cofnąć przez otwarcie wcześniejszego etapu — do tego służy poprawka. `app/process/service.py:1284-1288`
- ✅ „Cofnij" cofa etap o jeden poziom; zablokowane, gdy brak aktywnych sztuk. `app/process/service.py:507-523`
- ✅ Automat: przy starcie zawieszania pakowanie od razu wchodzi „w trakcie" — pakowanie idzie równolegle z linią. `app/process/service.py:223-233`
- ✅ Pakowanie automatu można obrabiać gdy zawieszanie trwa, ale zakończyć dopiero gdy zawieszanie skończone i zarejestrowano farbę. `app/process/service.py:1524-1548`, `697-700`
- ✅ Każda akcja etapu jest przypisana do swojej stacji. `app/process/service.py:1413-1427`
- ✅ Przygotowanie powierzchni i pakowanie są **fizycznie wspólne** dla obu linii; ich kolejność wyliczana osobno (nie z pozycji kolejki) i opisana etykietą linii. `app/process/service.py:279-358`
- ✅ Kolejność przygotowania: następna linia z **mniejszym** buforem „przygotowane-ale-niemalowane" (w sztukach); remis → automat. `app/process/shared_stage.py:49-89`

## 4. Ilości i liczenie

- ✅ Zakończenie przygotowania **wymaga** policzenia; >0 i ≤ aktywnej ilości. `app/process/service.py:2547-2550@def _ensure_surface_preparation_counted_quantity`, `2529-2545@def _store_surface_preparation_counted_quantity`
- ✅ Policzona liczba z przygotowania staje się **„rzeczywiście przyjętą"** — pakowanie musi się z nią zgodzić. `app/process/service.py:2724-2751@actual received`
- ✅ **(ZMIANA #12 zrobiona 2026-07-11, decyzja właściciela D5)** **niedobór przy przyjęciu** (przygotowanie liczy mniej niż zamówiono) to legalne zakończenie: przy domknięciu zlecenie jest **przedefiniowane na policzoną ilość** („staje się zleceniem na 3 sztuki"), a pierwotnie zamówiona ilość zostaje w zdarzeniu audytu `work_order.total_quantity_redefined` — zamówione-vs-przyjęte żyje w audycie, nie na zleceniu. `app/process/service.py:2358-2377@total_quantity_redefined`, `2452-2481@def _is_settled_intake_undercount`
- ✅ Policzona przy pakowaniu musi równać się rzeczywistej z przygotowania (a w rundzie poprawkowej — wielkości partii poprawkowej). `app/process/service.py:722-733`
- ✅ Na pakowaniu: dobre + do-poprawki = policzone. `app/process/service.py:714-720`
- ✅ Zużycie farby pokazywane na zleceniu to suma kg z całego łańcucha poprawek. `app/process/service.py:2556`

## 5. Poprawki i Decoral

Na zleceniu DECORAL są dwa punkty kontroli, bo dwie rzeczy mogą się zepsuć:

- **Brak farby — na PAKOWANIU (przed Decoralem).** Złe sztuki stają się osobnym **dzieckiem „P…"** (które wraca **pomalować od nowa**); korzeń dostaje **znacznik „N"**; dobre sztuki korzenia **od razu idą na Decoral**. ✅ `app/process/service.py:1986-2049`
- **Brak folii — na/po DECORALU.** **Brak dziecka** — wracają tylko złe sztuki jako **to samo zlecenie** (jak RAL, z przemalowaniem podkładu), bez numeru „P". ✅ `app/process/service.py:954-967`

Szczegóły:
- ✅ Trzy rodzaje poprawki w jednym punkcie decyzyjnym: poprawione od razu (tylko statystyka), to samo zlecenie wraca, dziecko „P". `app/process/enums.py:113-123`, `app/process/service.py:1864-1879`
- ✅ „Poprawione od razu" zapisuje tylko statystykę — bez dziecka i partii; sztuki liczą się jako dobre, zlecenie kończy się jak jest. `app/process/service.py:1881-1909`
- ✅ **(ZMIANA #1 zrobiona 2026-06-26)** „to samo zlecenie wraca" nadal kasuje *żywy* zamek (nie może być na niezaplanowanym zleceniu), ale teraz **pamięta** intencję pin/pilne w `pending_planning_priority` i **przywraca** ją przy ponownym zaplanowaniu. `app/process/service.py:2237-2245`, `app/manager/service.py:1399-1404@pending_planning_priority`
- ✅ Numery poprawek od **korzenia**: `P{korzeń}`, potem `P{korzeń}-2`, `-3`… niezależnie od zagnieżdżenia. `app/process/service.py:2101-2123`
- ✅ Dziecko poprawkowe dziedziczy farbę/kolor/klienta/daty/powierzchnię i jest zawsze rodzaju STANDARD. (Rodzaj nie wpływa na pominięcie przygotowania — to wynika z bycia poprawką.) `app/process/service.py:2125-2169`, `1461-1465`
- ✅ Jest dokładnie **jeden przebieg Decoral, na korzeniu**; sztuki w pełni poprawionego dziecka wracają na Decoral korzenia, a dziecko zamyka się bez własnego Decoralu. `app/process/service.py:2001-2021`, `2093-2099`
- ✅ Zwrócone sztuki **dorastają** do trwającej partii Decoral korzenia (przyp. 1); jeśli Decoral korzenia był już zrobiony — zakładają **nową** partię Decoral i Decoral otwiera się ponownie (przyp. 2). `app/process/service.py:2060-2091`
  - ⚠️ **ZMIANA #2** — przyp. 2 (drugi, osobny przebieg Decoral) jest poprawny, ale ma być **wyraźnie widoczny** dla operatora.
- ✅ Zaplanowanie poprawki z góry oznacza wszystkie etapy przed jej etapem powrotu jako zakończone (nie startuje od zera). `app/process/service.py:1852-1857`, `1438-1448`
- ✅ Etap powrotu: automat → zawieszanie; inaczej produkcja. `app/process/service.py:1429-1436`
- ✅ Znacznik „N" = zlecenie DECORAL z otwartymi dziećmi-poprawkami (nie zamknie się, póki nie wrócą). Gaśnie, gdy dziecko wróci. `app/process/service.py:2400-2407`
- ✅ Powód: kategoria ≤64 znaki, notatka ≤500; wymagany gdy są złe sztuki, zabroniony gdy ich nie ma; podział profile/akcesoria musi sumować się do liczby złych. `app/process/service.py:1356-1404`

## 6. Zakończenie

- ✅ RAL, pakowanie bez poprawki: zlecenie zalicza dobre sztuki, partia główna się zamyka. `app/process/service.py:790-795`
- ✅ DECORAL, pakowanie bez poprawki **nie kończy** zlecenia — sztuki idą na Decoral. `app/process/service.py:806-811`
- ✅ Zakończenie Decoralu (bez poprawki) zalicza dobre sztuki. `app/process/service.py:980-986`
- ✅ GOTOWE = wszystkie sztuki zaliczone (zakończone = całość) ORAZ brak aktywnych ORAZ wszystkie dzieci-poprawki gotowe. `app/process/service.py:2496-2501@def _is_complete_for_display`
- ✅ Domykanie idzie w górę po rodzicach — zamknięcie ostatniego dziecka domyka korzeń. `app/process/service.py:2339-2431@def _finalize_completion_chain_if_ready`
- ✅ **(ZMIANA #12 zrobiona 2026-07-11)** **rozliczony niedobór przy przyjęciu** (wszystkie policzone sztuki zaliczone, mniej niż zamówiono) domyka się jak każde zakończenie: przedefiniowanie na policzoną ilość (patrz §4), zwolnienie pozycji w kolejce, **bez flagi przecieku** — to ścieżka pobłogosławiona przez właściciela, nie przeciek. `app/process/service.py:2452-2481@def _is_settled_intake_undercount`
- ✅ **(ZMIANA #10 zrobiona 2026-06-26)** jeśli sztuki „przeciekną" (zaliczone ≠ całość przy domknięciu, a różnica **nie** jest rozliczonym niedoborem przy przyjęciu), zlecenie nadal jest wyrównywane do całości (żeby się domknęło), ale teraz jest **widoczne dla człowieka**: trwała flaga `quantity_leak_flagged` na zleceniu (w read-modelach) + zdarzenie audytu SYSTEM `work_order.quantity_leak_detected`, nie tylko log techniczny. `app/process/service.py:2379-2406@quantity_leak_flagged = True`, `app/work_orders/models.py:150-154`
- ✅ Zakończone dziecko-poprawka jest oznaczane jako „poprawka historyczna". `app/process/service.py:2503-2504@def is_historical_correction`
- ✅ Pierwszeństwo statusu: niekompletne → gotowe → do zaplanowania → (status partii) → czeka na poprawki → pierwszy niezakończony etap. `app/process/service.py:1132-1164`

## 7. Sloty pakowania i blokady zasobów

- ✅ N stanowisk pakowania (konfigurowalne); **domyślnie N = 2**. `app/process/resource_locks.py:154-158`, `app/core/config.py:45`
- ✅ Domyślnie jedno stanowisko naraz; tylko zlecenie **ręczne** otwiera 2. slot (override lub zakończenie); automat zawsze trzyma jedno stanowisko. `app/process/resource_locks.py:177-230`
- ✅ Zlecenie automatyczne **rezerwuje slot pakowania przy starcie zawieszania** (żeby ręczne nie zablokowało niewstrzymywalnej linii). `app/process/resource_locks.py:237-247`
- ✅ Drugie automatyczne **czeka po cichu** (bez 2. slotu). `app/process/resource_locks.py:188-216`
- ✅ Zlecenie może zwolnić stanowisko bez kończenia (zła pozycja); nie zwolni cudzego. `app/process/service.py:607-643`
- ✅ Zawieszanie to zasób na jedno zlecenie; linia automatyczna to zasób na jedno zlecenie (od zawieszania-zakończonego do pakowania-zakończonego). `app/process/resource_locks.py:88-103`, `321-338`
- ✅ Kierownik widzi to jako powód blokady („Zawieszanie zajęte" / „Linia automatyczna zajęta"). `app/process/service.py:1189-1211`
- ✅ Przeterminowane blokady są automatycznie zwalniane, gdy właściciel już nie zajmuje zasobu. `app/process/resource_locks.py:169-175`, `251-273`
- ✅ Model zakłada jeden worker backendu. `app/process/resource_locks.py:1-20`

## 8. Kolejka planowania

- ✅ Tylko kierownik planuje / przegląda statystyki. `app/manager/service.py:1922-1935@allowed_station_ids={StationId.MANAGER}`
- ✅ Planowanie wymaga zlecenia niezaplanowanego i nie niekompletnego. `app/manager/service.py:1377-1380@Cannot plan incomplete order`
- ✅ Kierownik **wybiera linię przy planowaniu**; zaplanowanie **jako automat** jest twardo blokowane, gdy mierzony kolor jest poza magazynem / nie starcza (ręcznej się nie sprawdza). `app/manager/service.py:1382-1397@_assert_paint_available_for_automatic`, `1324-1366@def _assert_paint_available_for_automatic`
- ✅ Planowanie bez podanej pozycji dopisuje na **koniec aktywnej kolejki** linii. `app/manager/service.py:1387-1393@_next_active_queue_position_for_line`
- ✅ **(ZMIANA #3 zrobiona 2026-06-26)** przy zakończeniu zlecenie **wychodzi z aktywnej kolejki linii i zwalnia pozycję** (zachowując linię); maszynerię odsuwania/trailing usunięto. Zakończone korekty-dzieci też zwalniają pozycje, gdy root się finalizuje. `app/process/service.py:2408-2440@release_queue_slot`
- ✅ **(ZMIANA #13 zrobiona 2026-07-11)** pozycja „zajęta" tylko przez zlecenie nie-gotowe; GOTOWE zlecenie wciąż trzymające pozycję (dane sprzed ZMIANY #12) jest przy sprawdzeniu **zwalniane od ręki** (audyt `manager.stale_queue_slot_released`) zamiast kolidować na indeksie unikalności. `app/manager/service.py:1961-1996@stale_queue_slot_released`
- ✅ **(ZMIANA #13 zrobiona 2026-07-11)** kolizja pozycji przy flushu zwraca kontrolowane **409** („pozycja zajęta"), nie surowe 500 — przy planowaniu, zmianie pozycji i zmianie linii. `app/manager/service.py:1408-1421@except IntegrityError`
- ✅ Zmiana linii zablokowana po starcie zawieszania/produkcji; przełączenie dopisuje na koniec i kasuje pin. `app/manager/service.py:1557-1577@work_order.planning_priority = None`
- ✅ Przeciąganie kolejki ma ochronę przed nieświeżymi danymi i musi obejmować wszystkie aktywne zlecenia tej linii, tylko tej linii, bez duplikatów. `app/manager/service.py:1631-1668@must include all active planned work orders`
- ✅ PIN = przypnij do slotu; PILNE = na przód; brak = swobodnie przestawialne. `app/shared/enums.py:78-92`
- ✅ „Ułóż automatycznie" tylko **proponuje**; kierownik zatwierdza. `app/manager/service.py:1859-1871@without committing anything`

## 9. Liczby planera

- ✅ Próg opłacalności: 800 m² (długi dzień) / 500 m² (krótki). `app/manager/capacity.py:33-36`
- ✅ Zmiany: długa = 07:00–21:00 (14 h), krótka = 07:00–15:00 (8 h). `app/manager/capacity.py:32-38`
- ✅ Pasmo prędkości kabiny 60–100 m²/h, używany środek **80**. `app/manager/capacity.py:41-43`
- ✅ **(ZMIANA #4 zrobiona 2026-06-26; front podłączony 2026-06-27)** długość zmiany **ustawia kierownik per dzień** (LONG/SHORT) z tablicy kabiny; jest zapisywana w `day_shift_lengths` i czytana per dzień, napędzając plan — zarówno próg/godziny dnia, **jak i** wypełnienie (krótki dzień ma mniejszy limit netto, mieści mniej i spycha nadmiar dalej). Dzień bez ustawienia domyślnie LONG; doradzanie wg m² (w tym dawne per-dniowe `display_shift_for` wyliczane z obłożenia) usunięto. `app/manager/service.py:1102-1106@shift_by_day` (plan per dzień), `855-861@shift_by_day` (dobry dzień per dzień), `app/manager/placement.py:134-198`
- ✅ Koszt zmiany koloru **tylko wg wielkości**: następne ≤100 m² → 15 min; >100 m² → 30 min. `app/manager/capacity.py:48-52`, `app/manager/capacity.py:82-97`
  - ✅ **(ZMIANA #5 zrobiona 2026-06-26)** czynnik **kierunku** koloru (jasny→ciemny taniej) usunięto — zmiana koloru kosztuje swoje pasmo wielkości niezależnie od kierunku.
- ✅ Próg 100 m² to ten sam co próg farby/odzysku. `app/manager/capacity.py:53`
- ✅ Horyzont planowania = **3 dni robocze** (dziś + dwa), domyślny i twardy limit. `app/manager/service.py:173-177@_MAX_PLAN_HORIZON_WORKING_DAYS`
- ✅ Kalendarz: pon–pt robocze, sob/niedz wolne, brak świąt. `app/manager/placement.py:40-45`
- ✅ Dzień 0 skracany proporcjonalnie do godzin pozostałych w zmianie. `app/manager/placement.py:205-216`
- ✅ Układanie: najwcześniejszy termin pierwszy, w dni ograniczone pułapem netto; zlecenie większe od dnia stoi samo i jest oznaczone „przekracza pułap"; zlecenie po terminie / poza horyzontem oznaczone „nie zdąży". `app/manager/placement.py:134-284`
- ✅ **(ZMIANA #6 zrobiona 2026-06-26)** Tylko **2** reguły układania — **termin → kolor** (domyślna kolejność); regułę „maks. przerób" usunięto. `app/manager/enums.py:4-43`, `app/manager/scheduler.py:42-57`
- ✅ **(ZMIANA #7 zrobiona 2026-06-26)** zgadywanie „jasności" z kodu RAL (i zamiatanie jasny→ciemny) **usunięto**; planowanie kolorów w dniu to teraz **grupowanie identycznych kolorów** (grupy alfabetycznie wg tożsamości koloru), koszt = liczba zmian × pasmo wielkości. `app/manager/colour.py:48-69`
- ✅ Sugestia linii: małe (≤100 m²) **i** kolor-sierota → ręczna; inaczej automat; kierownik nadpisuje. `app/manager/colour.py:128-150`
- ✅ Wykonalność farby: BLOKADA (mierzony kolor poza/nie starcza na pierwsze), OSTRZEŻENIE (skończy się dalej, albo kolor ręczny niepewny), inaczej OK. `app/manager/paint_feasibility.py:85-98`
  - ✅ **(ZMIANA #8 zrobiona 2026-06-26)** zlecenie z kolorem **nieśledzonym** (brak stanu — brak wiersza lub tylko placeholder 0 kg) ma teraz osobny stan **STOCK_NOT_ENTERED** (lista `stock_not_entered_order_ids`), zamiast cichego OK; nigdy nie jest twardo blokowane. Zlecenie bez koloru zostaje OK. `app/manager/paint_feasibility.py:29-37`, `116-175`

## 10. Magazyn farby

- ✅ Prognoza zapotrzebowania = powierzchnia ÷ 4 jeśli < 100 m², inaczej ÷ 6, zaokrąglone do pełnych kg. `app/work_orders/schemas.py:308-312`
- ✅ Niedobór = prognoza − stan (w górę), pokazywany gdy prognoza > stan. `app/work_orders/schemas.py:315-328`
- ✅ Zużycie automatu: tylko automat, po starcie zawieszania, wymaga kodu farby, **raz a dobrze** (bez edycji po zapisie; korekta ręczną korektą biura). `app/process/service.py:847-864`
- ✅ Zapis zużycia zdejmuje farbę ze stanu; błąd, gdy nie starcza. `app/paints/service.py:130-153`
- ✅ Kolor „śledzony" tylko z realną historią ruchów (nie placeholder 0 kg). `app/paints/service.py:155-159`
- ✅ Typy ruchów: saldo otwarcia, dostawa, zużycie automatu, korekta ręczna; dostawy/korekty tylko biuro. `app/shared/enums.py:95-99`

## 11. Statystyki

- ✅ Przerób (m²) przypisywany do **dnia zakończenia pakowania**; poprawki **wykluczone** (ich sztuki policzono już na rodzicu — bez podwójnego liczenia). `app/manager/service.py:253-346@WorkOrder.is_correction == False`
- ✅ Przebieg Decoral to **osobna, dodatkowa** seria m² w dniu jego zakończenia. `app/manager/service.py:387-421@decoral_done_events`
- ✅ Każda statystyka produkcji cięta dwojako naraz: wg metody (ręczna/automat) i powłoki (RAL/Decoral). `app/manager/service.py:149-156@_COATING_SEGMENTS`
- ✅ „Zdarzenie poprawki" ma jedną wspólną definicję łączącą partie poprawkowe + dzieci „P" + poprawione od razu. `app/manager/repository.py:105-128`
- ✅ Czas cyklu = najświeższy zakończony przebieg etapu; czas wiodący = pierwszy start → zakończenie pakowania. `app/manager/service.py:454-671@def get_cycle_time_stats`
- ✅ Starzenie WIP = zlecenia aktualnie „w trakcie", liczone od ostatniego wejścia w trakcie. `app/manager/service.py:672-763@def get_work_in_progress_aging`
- ✅ **(ZMIANA #9 zrobiona 2026-06-26)** długość zmiany per dzień jest **zapisywana** (`day_shift_lengths`, ustawia kierownik) i wyznacza próg 800/500 + godziny 14/8 dnia — używana przez **oba**: miarę „dobrego dnia" **i** plan przyszłości (ZMIANA #4); dzień bez zapisu domyślnie LONG. `app/manager/service.py:884-898@floor_m2(day_shift)`, `app/manager/models.py` (`DayShiftLength`)
