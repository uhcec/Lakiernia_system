# System lakierni — specyfikacja domenowa (odtworzona)

**Status:** odtworzona z kodu i przejrzana punkt po punkcie z właścicielem **2026-06-26**.
**Metoda (wg `CLAUDE.md`):** każda linijka jest oparta na kodzie (`plik:linia`) **i** potwierdzona przez
właściciela. `✅` = potwierdzone jako zgodne z fabryką. `⚠️ ZMIANA #n` = kod tak robi dzisiaj, ale
właściciel chce to zmienić — patrz `docs/ZMIANY.md`; **nie traktuj obecnego zachowania jako docelowego.**

Ten plik opisuje **co kod robi dzisiaj**. To nowa baza prawdy, zastępująca skasowaną dokumentację.

---

## 1. Model danych i niezmienniki

- ✅ Zlecenie ma dodatnią ilość; ilość zakończona mieści się między 0 a całkowitą. `app/work_orders/models.py:52-54`
- ✅ Zlecenie „zaplanowane" = ma **pozycję w kolejce**; pozycja wymaga linii, ale linia może istnieć **bez** pozycji — gotowe zlecenie opuszcza aktywną kolejkę (pozycja → NULL), zachowując linię (ZMIANA #3). `app/work_orders/models.py:60-63`
- ✅ Zlecenie niekompletne po przyjeździe nie może być zaplanowane. `app/work_orders/models.py:64-67`
- ✅ Pozycja w kolejce jest unikalna **per linia** (ręczna/automat); pozycja 1 istnieje na obu liniach niezależnie. `app/work_orders/models.py:96-104`
- ✅ Blokada planowania (pin/pilne) może istnieć tylko na zleceniu zaplanowanym. `app/work_orders/models.py:70-73`
- ✅ Gdy znane są ilości profili i akcesoriów, muszą sumować się do całkowitej. `app/work_orders/models.py:74-85`
- ✅ Folię Decoral można przypisać tylko zleceniu DECORAL. `app/work_orders/models.py:86-89`
- ✅ Zlecenie poprawkowe musi mieć rodzica i żyje w przestrzeni kolejki CORRECTIONS. `app/work_orders/models.py:90-95`
- ✅ Zlecenie ma w danej chwili co najwyżej jedną aktywną partię. `app/process/models.py:69-75`
- ✅ Pięć etapów (przygotowanie powierzchni, zawieszanie, produkcja, produkcja Decoral, pakowanie); trzy statusy (nie rozpoczęte, w trakcie, zakończone). `app/process/enums.py:82-97`
- ✅ Powłoka = RAL/DECORAL; produkcja = ręczna/automat; rodzaj = standard/przemalowanka. `app/process/enums.py:47-62`, `app/shared/enums.py:69-71`
- ✅ Przejścia etapów zapisywane są w stałym dzienniku (tylko dopisywanie; zasila statystyki). Dziś każda akcja idzie pod **wspólną tożsamością stacji** — nie ma loginu osoby; pole „kto" zostawione na przyszłość. `app/process/models.py:95-126`

## 2. Przyjęcie (biuro)

- ✅ Numer zlecenia = jeden **globalny licznik 4-cyfrowy** (`0001`, `0002`…), **nie** resetowany rocznie. `app/work_orders/number_allocator.py:11-39`
- ✅ Wymagane przy tworzeniu: klient, RAL + kod farby + producent, technologia, data przyjęcia, **data odbioru**, powierzchnia (>0). `app/work_orders/schemas.py:154-177`
- ✅ Ilość domyślnie 1. `app/work_orders/schemas.py:157`
- ✅ Dla profili i akcesoriów podajesz **albo** ilość, **albo** „do policzenia na produkcji", nigdy oba/żadne. `app/work_orders/schemas.py:128-132`
- ✅ Utworzenie zlecenia zapisuje **migawkę stanu farby** (kg w tej chwili). `app/work_orders/service.py:231@capture_work_order_snapshot`
- ✅ Tylko biuro tworzy zlecenia / zarządza załącznikami / odznacza „kompletne"; biuro lub kierownik edytuje. `app/work_orders/service.py:923@_ensure_office_station_action`, `288@aktualizacja zlecenia`
- ✅ Lista biura **nie pokazuje** poprawek „P…". `app/work_orders/service.py:402@not item.is_correction`
- ✅ Status zlecenia jest **wyliczany** z postępu, nigdy ustawiany ręcznie. `app/work_orders/service.py:196@def derive_status`
- ✅ „Po terminie" = data odbioru przed dziś ORAZ zlecenie jeszcze nie gotowe. `app/work_orders/service.py:1082@work_order.planned_pickup_date < date.today()`
- ✅ „Wydane klientowi" można ustawić tylko dla gotowego zlecenia. `app/work_orders/service.py:487@Only READY work orders`
- ✅ Załączniki: tylko PDF / PNG / JPG, limit rozmiaru z konfiguracji. `app/work_orders/service.py:171@ALLOWED_ATTACHMENT_TYPES`
- ✅ **(ZMIANA #18 zrobione 2026-07-11) WZ (wydanie z magazynu):** biuro generuje PDF wydania dla grupy gotowych zleceń **jednego** klienta — wiersze to liczby profili/akcesoriów + RAL każdego zlecenia (zlecenie bez znanego podziału daje jeden wiersz „Elementy"), plus opcjonalna ręczna pozycja „Kosze dłużycowe"; adres odbiorcy zostaje pusty (dopisywany ręcznie). Różni klienci lub zlecenia niegotowe są odrzucane; na hoście bez Excela zwraca kontrolowane polskie **503** jak karta jakości. `app/work_orders/service.py:705@def generate_wz_document`, `746@różnych klientów`, `779@Kosze dłużycowe`
- ✅ Numery WZ idą rocznie „kolejny/rok" (np. 1/2026); numer jest pobierany dopiero gdy PDF się wygeneruje (nieudany render cofa numer). Dokument WZ **nie** jest zapisywany (brak rejestru / ponownego druku z tym samym numerem), a jego wygenerowanie **nie** oznacza zleceń jako wydane — to osobny krok. `app/work_orders/wz_number_allocator.py:23@def allocate`, `app/work_orders/service.py:730@wz_number_allocator.allocate`
- ✅ **(ZMIANA #17 zrobiona 2026-07-11)** biuro pobiera **kartę kontroli jakości** jako PDF: szablon Excela z repo (`app/static/templates/karta_kontroli_jakosci.xlsx`) wypełniony numerem zlecenia / klientem / farbą, renderowany do PDF przez **sterowanie Excelem po COM** — świadome ograniczenie hostingu (decyzje właściciela D1/D6: karta w formacie Excela jest wymagana, a produkcja działa na **hoście Windows z Excelem**; trwały worker trzyma jedną instancję Excela). Na hoście bez Excela (np. deweloperski VPS z Linuksem) endpoint odpowiada kontrolowanym polskim **503**, nigdy surowym 500. `app/work_orders/service.py:666@def generate_quality_control_document`, `app/work_orders/service.py:65@class _ExcelPdfConverter`, `app/work_orders/router.py:110-128@quality-control-document`, `app/shared/exceptions.py:50-57@DocumentGenerationUnavailableError`

## 3. Przepływ etapów i trasa

- ✅ Trasa wynika z powłoki + linii: przygotowanie → (zawieszanie, chyba że ręczna) → produkcja → pakowanie → (Decoral, jeśli DECORAL). `app/process/service.py:89-105`
- ✅ Ręczna nie ma zawieszania; automat nie ma produkcji (linia maluje sama). `app/process/service.py:99-101`, `1545-1549`
- ✅ Przemalowanka pomija przygotowanie powierzchni; poprawki pomijają przygotowanie. `app/process/service.py:1590-1592`, `1549-1550`
- ✅ Dozwolone ruchy statusu: nie rozpoczęte→w trakcie; w trakcie→{zakończone, nie rozpoczęte}; zakończone→{w trakcie, nie rozpoczęte}. `app/process/service.py:1423-1432`
- ✅ Etap nie ruszy, dopóki poprzedni nie jest zakończony. `app/process/service.py:1434-1441`
- ✅ Zlecenia w pełni gotowego nie da się cofnąć przez otwarcie wcześniejszego etapu — do tego służy poprawka. `app/process/service.py:1417-1421`
- ✅ **(ZMIANA #14 zrobiona 2026-07-11)** **zakończony etap odmawia startu/cofnięcia, gdy dowolny późniejszy etap jest w trakcie lub zakończony** (409, polski komunikat dla operatora) — jego zapisany licznik zasila już walidację dalszych etapów, więc restart w locie przepisałby „rzeczywiście przyjętą" liczbę. Ponowne liczenie **zanim** ruszy dalszy etap pozostaje dozwolone. `app/process/service.py:1538-1555@Nie można cofnąć zakończonego etapu`
- ✅ **(ZMIANA #14 zrobiona 2026-07-11)** wyjście awaryjne: **reset administracyjny** (role z decyzji właściciela: biuro/kierownik, admin omija) cofa naprawdę zablokowane zlecenie na początek trasy — etapy „nie rozpoczęte", liczniki wyczyszczone, świeża aktywna partia MAIN na zamówioną ilość, flaga przecieku skasowana, plan (linia+pozycja) zostaje, audyt `work_order.administrative_reset`. Odmawia zleceniom powiązanym z poprawkami (rodzic z dziećmi lub sama poprawka). `app/process/service.py:616-701@def administrative_reset`, `app/work_orders/router.py:90-97@administrative-reset`
- ✅ „Cofnij" cofa etap o jeden poziom; zablokowane, gdy brak aktywnych sztuk. `app/process/service.py:568-584`
- ✅ Automat: przy starcie zawieszania pakowanie od razu wchodzi „w trakcie" — pakowanie idzie równolegle z linią. `app/process/service.py:279-289`
- ✅ **(ZMIANA #28 zrobiona 2026-10-15, właściciel)** cofnięcie tego startu zawieszania cofa też pakowanie do „nie rozpoczęte”, więc stanowisko pakowania się zwalnia (i przechodzi na czekające zlecenie automatu). `app/process/service.py:297-309@CHANGES #28: undoing`
- ✅ **(ZMIANA #22 zrobiona 2026-10-09)** Pakowanie automatu można obrabiać gdy zawieszanie trwa, ale zakończyć dopiero gdy zawieszanie skończone; zużycie farby nie blokuje już pakowania każdego zlecenia — czeka na nie tylko **ostatnie zlecenie grupy farby** (§10, ZMIANA #23). `app/process/service.py:875@Trzeba zakończyć zawieszanie automatu przed pakowaniem`, `1727-1744@def _packing_completion_block_reason`
- ✅ Każda akcja etapu jest przypisana do swojej stacji. `app/process/service.py:1546-1560`
- ✅ **(ZMIANA #27 zrobiona 2026-10-15, szkic właściciela z tablicy)** **stanowisko zawieszania** pokazuje kolejkę jako zwarte wiersze **pogrupowane po farbie**: nagłówek „RAL · producent · kod farby” (bez osobnego pola mat/połysk — wynika z kodu farby), wiersz „firma · m² · numer zlecenia · sztuki · Szczegóły · Rozpocznij”. Grupa = zlecenia stojące **jedno po drugim w kolejce kierownika** z tą samą farbą (ta sama tożsamość co grupa farby; właściciel wybrał to zamiast zbierania koloru z całej kolejki, więc zawieszanie nigdy nie zmienia planu); zlecenia bez kodu farby nie są grupowane. Przycisk przy każdym zleceniu; „Rozpocznij” jest wyszarzone z powodem, gdy zlecenie nie może ruszyć (**ZMIANA #29**: „Zawieszanie zajęte” przy N = 1, „Zawieszanie pełne (n/N)”, „Na zawieszaniu inna farba”); wiszące zlecenie ma też „Cofnij start” (z potwierdzeniem, ZMIANA #28/#29). Etykiety w wierszu: POPRAWKA, NIEPEŁNE, PRZEMALOWANKA, OCYNK, DECORAL; rysunki/załączniki/opis poprawki pod „Szczegóły”; zakończone zwinięte na dole z „Cofnij”. Bez podsumowania grupy (właściciel). `frontend/src/utils/hangingGroups.ts:50@export function groupHangingQueue`, `frontend/src/utils/hangingGroups.ts:35@export function getHangingStartBlock`, `frontend/src/pages/HangingPage.tsx:31@function getRowBadges`
- ✅ Przygotowanie powierzchni i pakowanie są **fizycznie wspólne** dla obu linii; ich kolejność wyliczana osobno (nie z pozycji kolejki) i opisana etykietą linii. `app/process/service.py:337-416`
- ✅ Kolejność przygotowania: następna linia z **mniejszym** buforem „przygotowane-ale-niemalowane" (w sztukach); remis → automat. `app/process/shared_stage.py:49-89`

## 4. Ilości i liczenie

- ✅ Zakończenie przygotowania **wymaga** policzenia; >0, a ≤ aktywnej ilości na partii śledzonej/poprawkowej — przy pierwszym (zwykłym) przygotowaniu zlecenia od ZMIANY #24 może przekroczyć ilość zgłoszoną (niżej). `app/process/service.py:2823-2826@def _ensure_surface_preparation_counted_quantity`, `app/process/service.py:2797-2817@def _store_surface_preparation_counted_quantity`
- ✅ Policzona liczba z przygotowania staje się **„rzeczywiście przyjętą"** — pakowanie musi się z nią zgodzić. `app/process/service.py:3041-3068@actual received`
- ✅ **(ZMIANA #12 zrobiona 2026-07-11, decyzja właściciela D5; podział kategorii naprawiony 2026-07-11)** **niedobór przy przyjęciu** (przygotowanie liczy mniej niż zamówiono) to legalne zakończenie: przy domknięciu zlecenie jest **przedefiniowane na policzoną ilość** („staje się zleceniem na 3 sztuki"), a pierwotnie zamówiona ilość (wraz z zadeklarowanym podziałem profile/akcesoria) zostaje w zdarzeniu audytu `work_order.total_quantity_redefined`. **Od ZMIANY #24 (właściciel 2026-10-15)** ilość zgłoszona jest też trzymana **na zleceniu** (niżej) — sam ślad w audycie okazał się w praktyce niewidoczny (zlecenie 0002: zgłoszono 14, przyjechało 10, nic na ekranie). Zadeklarowany **podział profile/akcesoria jest przedefiniowany razem z całością** (CHECK w bazie wiąże ich sumę z totalem): zlecenie jednokategoriowe zachowuje kategorię (10 profili policzone na 8 → 8 profili), podział mieszany spada do **„do przeliczenia"** — ta sama polityka co przy partiach poprawkowych. `app/process/service.py:2604-2641@total_quantity_redefined`, `app/process/service.py:2736-2745@def _is_settled_intake_undercount`, `app/process/service.py:2536-2561@def _derive_category_fields_for_operational_quantity`
- ✅ **(ZMIANA #25 zrobiona 2026-10-15)** od zakończenia przygotowania aktywna partia zlecenia ma **dokładnie policzoną liczbę sztuk** (mniej lub więcej; ponowne liczenie ją wyrównuje), więc każdy dalszy etap — także przebieg DECORAL, który zalicza partię — liczy tylko to, co przyjechało; niedobór na Decoralu (3 z 5) domyka się teraz ścieżką D5 jako 3/3 zamiast 5/5. `app/process/service.py:2843@active_batch.quantity = counted_quantity`
- ✅ **(ZMIANA #24 zrobiona 2026-10-15, właściciel)** **nadwyżka przy przyjęciu** (przygotowanie liczy więcej niż zgłoszono) jest **dokładana do zlecenia**: przy zakończeniu przygotowania `total_quantity` i aktywna partia stają się policzoną ilością, więc pakowanie, poprawki i Decoral idą jak zwykłe zlecenie na N sztuk i domyka się bez flagi przecieku. Podział profile/akcesoria jak przy niedoborze (jedna kategoria zostaje, mieszany → do przeliczenia); **m² się nie zmienia** (właściciel: biuro się tym zajmie); audyt `work_order.total_quantity_increased`. Tylko pierwsze, zwykłe przygotowanie zlecenia — partie śledzone/poprawkowe zachowują limit ≤. `app/process/service.py:2824-2867@def _apply_intake_count`, `app/process/service.py:2816@and not allow_intake_overcount`
- ✅ **(ZMIANA #24 zrobiona 2026-10-15, właściciel)** **zgłoszone a przyjęte zostaje na zleceniu:** przy pierwszym przedefiniowaniu `total_quantity` przez system (niedobór przy domknięciu, nadwyżka przy zakończeniu przygotowania) ilość zgłoszona przez klienta i podział profile/akcesoria są zapisywane w `declared_*` (kolejne przedefiniowania ich nie nadpisują). `surface_preparation_quantity_difference` w read-modelach = policzone − **zgłoszone**, więc nie spada do 0 przy domknięciu zlecenia. `app/process/service.py:221-228@def _remember_declared_quantity`, `app/process/service.py:189-195@def get_surface_preparation_quantity_difference`
- ✅ **(ZMIANA #24 zrobiona 2026-10-15, właściciel)** lista biura, panel kierownika i szczegóły zlecenia pokazują **„MNIEJ NIŻ ZGŁOSZONO: 10 z 14” / „WIĘCEJ NIŻ ZGŁOSZONO: 16 z 14”** (przyjęto z zgłoszono), dopóki **biuro lub kierownik** nie kliknie **„Wyjaśnione z klientem”** w szczegółach (można cofnąć; zapisuje stanowisko + czas, w audycie). Wyjaśniona różnica znika z list; linijka „Zgłoszono · Przyjęto · Brak/Nadwyżka” w szczegółach zostaje na zawsze. Stanowiska produkcyjne nie mogą odhaczać. `frontend/src/utils/workOrderDisplay.ts:67@export function getQuantityDiscrepancyBadge`, `frontend/src/components/OfficeWorkOrdersTable.tsx:60@getQuantityDiscrepancyBadge`, `app/work_orders/service.py:517-528@wyjaśnianie różnicy ilości`
- ✅ Policzona przy pakowaniu musi równać się rzeczywistej z przygotowania (a w rundzie poprawkowej — wielkości partii poprawkowej). `app/process/service.py:783-794`
- ✅ Na pakowaniu: dobre + do-poprawki = policzone. `app/process/service.py:775-781`
- ✅ Zużycie farby pokazywane na zleceniu to suma kg z całego łańcucha poprawek — od ZMIANY #22 suma udziałów (wg m²) zlecenia w zamkniętych grupach farby (0, dopóki jego grupa jest otwarta). `app/process/service.py:2983@get_consumed_paint_kg_for_work_orders`, `app/paints/repository.py:69@def sum_allocated_consumption_kg`

## 5. Poprawki i Decoral

Na zleceniu DECORAL są dwa punkty kontroli, bo dwie rzeczy mogą się zepsuć:

- **Brak farby — na PAKOWANIU (przed Decoralem).** Złe sztuki stają się osobnym **dzieckiem „P…"** (które wraca **pomalować od nowa**); korzeń dostaje **znacznik „N"**; dobre sztuki korzenia **od razu idą na Decoral**. ✅ `app/process/service.py:2110-2173`
- **Brak folii — na/po DECORALU.** **Brak dziecka** — wracają tylko złe sztuki jako **to samo zlecenie** (jak RAL, z przemalowaniem podkładu), bez numeru „P". ✅ `app/process/service.py:1094-1117`

Szczegóły:
- ✅ Trzy rodzaje poprawki w jednym punkcie decyzyjnym: poprawione od razu (tylko statystyka), to samo zlecenie wraca, dziecko „P". `app/process/enums.py:113-123`, `app/process/service.py:1988-2003`
- ✅ „Poprawione od razu" zapisuje tylko statystykę — bez dziecka i partii; sztuki liczą się jako dobre, zlecenie kończy się jak jest. `app/process/service.py:2005-2033`
- ✅ **(ZMIANA #1 zrobiona 2026-06-26)** „to samo zlecenie wraca" nadal kasuje *żywy* zamek (nie może być na niezaplanowanym zleceniu), ale teraz **pamięta** intencję pin/pilne w `pending_planning_priority` i **przywraca** ją przy ponownym zaplanowaniu. `app/process/service.py:2361-2369`, `app/manager/service.py:1408-1413@pending_planning_priority`
- ✅ Numery poprawek od **korzenia**: `P{korzeń}`, potem `P{korzeń}-2`, `-3`… niezależnie od zagnieżdżenia. `app/process/service.py:2225-2247`
- ✅ Dziecko poprawkowe dziedziczy farbę/kolor/klienta/daty/powierzchnię i jest zawsze rodzaju STANDARD. (Rodzaj nie wpływa na pominięcie przygotowania — to wynika z bycia poprawką.) `app/process/service.py:2249-2293`, `1549-1550`
- ✅ Jest dokładnie **jeden przebieg Decoral, na korzeniu**; sztuki w pełni poprawionego dziecka wracają na Decoral korzenia, a dziecko zamyka się bez własnego Decoralu. `app/process/service.py:2125-2145`, `2179-2185`
- ✅ Zwrócone sztuki **dorastają** do trwającej partii Decoral korzenia (przyp. 1); jeśli Decoral korzenia był już zrobiony — zakładają **nową** partię Decoral i Decoral otwiera się ponownie (przyp. 2). `app/process/service.py:2184-2215`
  - ⚠️ **ZMIANA #2** — przyp. 2 (drugi, osobny przebieg Decoral) jest poprawny, ale ma być **wyraźnie widoczny** dla operatora.
- ✅ Zaplanowanie poprawki z góry oznacza wszystkie etapy przed jej etapem powrotu jako zakończone (nie startuje od zera). `app/process/service.py:1976-1981`, `1533-1543`
- ✅ Etap powrotu: automat → zawieszanie; inaczej produkcja. `app/process/service.py:1562-1569`
- ✅ Znacznik „N" = zlecenie DECORAL z otwartymi dziećmi-poprawkami (nie zamknie się, póki nie wrócą). Gaśnie, gdy dziecko wróci. `app/process/service.py:2522-2529`
- ✅ Powód: kategoria ≤64 znaki, notatka ≤500; wymagany gdy są złe sztuki, zabroniony gdy ich nie ma; podział profile/akcesoria musi sumować się do liczby złych. `app/process/service.py:1489-1537`

## 6. Zakończenie

- ✅ RAL, pakowanie bez poprawki: zlecenie zalicza dobre sztuki, partia główna się zamyka. `app/process/service.py:854-858`
- ✅ DECORAL, pakowanie bez poprawki **nie kończy** zlecenia — sztuki idą na Decoral. `app/process/service.py:870-875`
- ✅ Zakończenie Decoralu (bez poprawki) zalicza dobre sztuki. `app/process/service.py:1117-1119`
- ✅ GOTOWE = wszystkie sztuki zaliczone (zakończone = całość) ORAZ brak aktywnych ORAZ wszystkie dzieci-poprawki gotowe. `app/process/service.py:2760-2765@def _is_complete_for_display`
- ✅ Domykanie idzie w górę po rodzicach — zamknięcie ostatniego dziecka domyka korzeń. `app/process/service.py:2585-2695@def _finalize_completion_chain_if_ready`
- ✅ **(ZMIANA #12 zrobiona 2026-07-11)** **rozliczony niedobór przy przyjęciu** (wszystkie policzone sztuki zaliczone, mniej niż zamówiono) domyka się jak każde zakończenie: przedefiniowanie na policzoną ilość (patrz §4), zwolnienie pozycji w kolejce, **bez flagi przecieku** — to ścieżka pobłogosławiona przez właściciela, nie przeciek. `app/process/service.py:2736-2745@def _is_settled_intake_undercount`
- ✅ **(ZMIANA #10 zrobiona 2026-06-26)** jeśli sztuki „przeciekną" (zaliczone ≠ całość przy domknięciu, a różnica **nie** jest rozliczonym niedoborem przy przyjęciu), zlecenie nadal jest wyrównywane do całości (żeby się domknęło), ale teraz jest **widoczne dla człowieka**: trwała flaga `quantity_leak_flagged` na zleceniu (w read-modelach) + zdarzenie audytu SYSTEM `work_order.quantity_leak_detected`, nie tylko log techniczny. `app/process/service.py:2643-2670@quantity_leak_flagged = True`, `app/work_orders/models.py:148-152`
- ✅ Zakończone dziecko-poprawka jest oznaczane jako „poprawka historyczna". `app/process/service.py:2771-2772@def is_historical_correction`
- ✅ Pierwszeństwo statusu: niekompletne → gotowe → do zaplanowania → (status partii) → czeka na poprawki → pierwszy niezakończony etap. `app/process/service.py:1265-1297`

## 7. Sloty pakowania i blokady zasobów

- ✅ N stanowisk pakowania (konfigurowalne); **domyślnie N = 2**. `app/process/resource_locks.py:163-167`, `app/core/config.py:45`
- ✅ Domyślnie jedno stanowisko naraz; tylko zlecenie **ręczne** otwiera 2. slot (override lub zakończenie); automat zawsze trzyma jedno stanowisko. `app/process/resource_locks.py:216-269` **(ZMIANA #23, decyzja (a) 2026-10-09)** zwolnione stanowisko dostaje zlecenie z automatu, które czeka najdłużej (pierwsze skończyło zawieszanie) — wcześniej brało je zlecenie, które dopiero *zaczęło* zawieszanie, i linia się zakleszczała do czasu „drugiego stanowiska” (widziane na żywo 2026-10-09). `app/process/resource_locks.py:259-286@def _hand_free_station_to_waiting_automatic`
- ✅ Zlecenie automatyczne **rezerwuje slot pakowania przy starcie zawieszania** (żeby ręczne nie zablokowało niewstrzymywalnej linii). `app/process/resource_locks.py:277-287`
- ✅ Drugie automatyczne **czeka po cichu** (bez 2. slotu). `app/process/resource_locks.py:227-255`
- ✅ Zlecenie może zwolnić stanowisko bez kończenia (zła pozycja); nie zwolni cudzego. `app/process/service.py:668-704`
- ✅ **(ZMIANA #29 zrobiona 2026-10-15, właściciel)** na zawieszaniu może być **do N zleceń naraz**; N to ustawienie, które zmienia **kierownik (i admin)** w zakładce **„Ustawienia”** (domyślnie **1** = dawna zasada jednego zlecenia; 1–20; zapis w audycie `settings.updated`). Zlecenia wieszane razem muszą mieć **tę samą farbę** (RAL + producent + kod — kabina maluje jednym kolorem). Odmowy: „Zawieszanie jest zajęte przez inne zlecenie.” (N = 1), „Zawieszanie pełne: …” (N > 1), „Na zawieszaniu wisi inna farba (…)”. *Uwaga:* dawna zasada jednego zlecenia nie miała zapisanego powodu z fabryki — potwierdzenie (b) z 2026-10-09 dotyczyło tylko zasady linii poniżej. `app/process/resource_locks.py:161-178@def hanging_start_block`, `app/shop_settings/service.py:15@def get_hanging_max_active_orders`
- ✅ Linia automatyczna to zasób na jedno zlecenie (od zawieszania-zakończonego do pakowania-zakończonego): następne zlecenie nie zakończy zawieszania, dopóki poprzednie nie jest spakowane — potwierdzone ponownie przez właściciela (b) 2026-10-09. **(ZMIANA #29, właściciel (b) 2026-10-15)** wyjątek: zlecenia **wieszane razem** (jedno zaczęte, gdy drugie jeszcze się wieszało — wspólne belki) mogą razem zakończyć zawieszanie; zlecenie zaczęte po zakończeniu zawieszania poprzedniego nadal czeka. Drugi wyjątek to zaparkowane ostatnie zlecenie grupy (ZMIANA #23, §10), które nie trzyma ani linii, ani stanowiska. Komunikaty blokad są po polsku. `app/process/resource_locks.py:423@def _hung_together`, `app/process/resource_locks.py:203@def _acquire_automatic_line`
- ✅ Kierownik widzi to jako powód blokady („Zawieszanie zajęte” / „Na zawieszaniu inna farba” (ZMIANA #29) / „Linia automatyczna zajęta”). `app/process/service.py:1452@HANGING_OTHER_PAINT`
- ✅ Przeterminowane blokady są automatycznie zwalniane, gdy właściciel już nie zajmuje zasobu. `app/process/resource_locks.py:178-184`, `291-313`
- ✅ Model zakłada jeden worker backendu. `app/process/resource_locks.py:1-20`

## 8. Kolejka planowania

- ✅ Tylko kierownik planuje / przegląda statystyki. `app/manager/service.py:1926-1939@allowed_station_ids={StationId.MANAGER}`
- ✅ Planowanie wymaga zlecenia niezaplanowanego i nie niekompletnego. `app/manager/service.py:1377-1380@Cannot plan incomplete order`
- ✅ Kierownik **wybiera linię przy planowaniu**; zaplanowanie **jako automat** jest twardo blokowane, gdy mierzony kolor jest poza magazynem / nie starcza (ręcznej się nie sprawdza). `app/manager/service.py:1386-1401@_assert_paint_available_for_automatic`, `1324-1366@def _assert_paint_available_for_automatic`
- ✅ Planowanie bez podanej pozycji dopisuje na **koniec aktywnej kolejki** linii. `app/manager/service.py:1391-1397@_next_active_queue_position_for_line`
- ✅ **(ZMIANA #3 zrobiona 2026-06-26)** przy zakończeniu zlecenie **wychodzi z aktywnej kolejki linii i zwalnia pozycję** (zachowując linię); maszynerię odsuwania/trailing usunięto. Zakończone korekty-dzieci też zwalniają pozycje, gdy root się finalizuje. `app/process/service.py:2655-2687@release_queue_slot`
- ✅ **(ZMIANA #26 zrobiona 2026-10-15)** gotowego zlecenia **nie można ponownie zaplanować** — wcześniej plan dawał mu nową pozycję w kolejce (zombie); przesuwanie i przypinanie już odrzucały gotowe zlecenia. `app/manager/service.py:1381-1384@nie można go ponownie zaplanować`
- ✅ **(ZMIANA #13 zrobiona 2026-07-11; pokrycie dopisywania/zmiany linii naprawione 2026-07-11)** pozycja „zajęta" tylko przez zlecenie nie-gotowe; GOTOWE zlecenie wciąż trzymające pozycję (dane sprzed ZMIANY #12) jest przy sprawdzeniu **zwalniane od ręki** (audyt `manager.stale_queue_slot_released`) zamiast kolidować na indeksie unikalności. Uzdrowienie obejmuje **każdą** ścieżkę lądującą na pozycji: jawnie wybraną pozycję, wyliczony slot dopisania przy planowaniu bez pozycji i dopisanie przy zmianie linii (slot dopisania jest liczony z *pominięciem* GOTOWYCH posiadaczy, więc trafia dokładnie w pozycję zombie). `app/manager/service.py:1973-2008@stale_queue_slot_released`, `app/manager/service.py:1397-1402@_next_active_queue_position_for_line`, `app/manager/service.py:1580-1583@same zombie heal as assign_plan`
- ✅ **(ZMIANA #13 zrobiona 2026-07-11)** kolizja pozycji przy flushu zwraca kontrolowane **409** („pozycja zajęta"), nie surowe 500 — przy planowaniu, zmianie pozycji i zmianie linii. `app/manager/service.py:1417-1430@except IntegrityError`
- ✅ Zmiana linii zablokowana po starcie zawieszania/produkcji; przełączenie dopisuje na koniec i kasuje pin. `app/manager/service.py:1566-1589@work_order.planning_priority = None`
- ✅ Przeciąganie kolejki ma ochronę przed nieświeżymi danymi i musi obejmować wszystkie aktywne zlecenia tej linii, tylko tej linii, bez duplikatów. `app/manager/service.py:1643-1680@must include all active planned work orders`
- ✅ PIN = przypnij do slotu; PILNE = na przód; brak = swobodnie przestawialne. `app/shared/enums.py:78-92`
- ✅ „Ułóż automatycznie" tylko **proponuje**; kierownik zatwierdza. `app/manager/service.py:1871-1883@without committing anything`

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

- ✅ Prognoza zapotrzebowania = powierzchnia ÷ 4 jeśli < 100 m², inaczej ÷ 6, zaokrąglone do pełnych kg. `app/work_orders/schemas.py:339@total_area_m2 < 100`
- ✅ Niedobór = prognoza − stan (w górę), pokazywany gdy prognoza > stan. `app/work_orders/schemas.py:343-356@ROUND_CEILING`
- ✅ **(ZMIANA #22 zrobiona 2026-10-09)** Zużycie farby na automacie wpisuje się **raz na grupę farby**, nie na zlecenie. Grupa = zlecenia na automacie w **tej samej farbie** (RAL + producent + kod farby) zawieszane **jedno po drugim**: przy starcie zawieszania zlecenie dołącza do najnowszej grupy, jeśli jest ona otwarta i ma tę samą farbę, w przeciwnym razie zaczyna nową — zmiana farby kończy grupę, a ta sama farba po zamkniętej grupie zaczyna nową. Poprawki dołączają jak zwykłe zlecenia. Cofnięcie startu zawieszania wyjmuje zlecenie z otwartej grupy (pusta grupa znika). `app/process/service.py:254@CHANGES #22: automatic hanging drives`, `app/process/paint_runs.py:130-165@def join_on_hanging_start`, `137@latest.closed_at is None`, `167@def leave_on_hanging_undo`
- ✅ **(ZMIANA #22)** Zużycie grupy wpisuje stanowisko Produkcja automat (pobrane kartony − resztka), gdy żadne zlecenie z grupy nie jest już w zawieszaniu; **raz a dobrze** (pomyłkę poprawia biuro ręczną korektą stanu). Zdejmuje farbę ze stanu **jednym** ruchem dla całej grupy i dzieli kg na zlecenia **wg m²** (powierzchnia sztuki z pierwotnego zlecenia × sztuki zawieszone w tym przebiegu; gramy, ostatnie zlecenie bierze resztę). Za mało farby na stanie → polski komunikat, nic się nie zapisuje. `app/process/paint_runs.py:190-244@def record_consumption`, `203@RUN_HANGING_IN_PROGRESS_ERROR`, `201@RUN_ALREADY_RECORDED_ERROR`, `216@Za mało farby`, `101-115@def allocate_by_area`, `315-326@def _pass_area_m2`, `app/paints/service.py:133@def record_paint_run_consumption`
- ✅ **(ZMIANA #23 zrobiona 2026-10-09)** Na wpis zużycia czeka tylko **ostatnie zlecenie otwartej grupy**: gdy pakowacz kliknie „Zakończ”, pakowanie zostaje **zaparkowane** (sprawdzone, ale nie zamknięte — „Spakowane … zamknie się samo”), a system zamyka je z liczbami pakowacza zaraz po wpisie zużycia. „Ostatnie” = żadne inne zlecenie grupy nie jest już w drodze (zawieszanie zaczęte, pakowanie niezamknięte); jeśli potem zacznie się zawieszanie zlecenia w tej samej farbie, zaparkowane przestaje być ostatnie i zamyka się od razu. Zaparkowane zlecenie zwalnia stanowisko pakowania i linię automatu, więc następna farba wisi dalej (właściciel: „ma iść dalej”). `app/process/service.py:910-938@CHANGES #23 (owner, 2026-10-09): the LAST`, `225@CHANGES #23: a same-paint order joining`, `999@def _complete_parked_packings`, `app/process/paint_runs.py:247-267@def holding_run_for`, `269@def park_packing`, `app/process/resource_locks.py:455@if self.is_held_for_paint`, `392@if self.is_held_for_paint`, `frontend/src/components/PackingWorkOrdersPage.tsx:694@!workOrder.can_complete_packing && workOrder.packing_blocked_reason`
- ✅ **(ZMIANA #23, decyzja (c))** Wpis bez stanu farby nadal odrzucany; karta grupy pokazuje stan farby i od razu mówi, że biuro musi go najpierw wpisać. `frontend/src/components/PaintRunsPanel.tsx:205@run.paint_stock_kg <= 0`
- ✅ **(ZMIANA #22)** Poza tym jednym czekającym zleceniem otwarta grupa **niczego nie blokuje** na hali (decyzja właściciela 2026-10-09). Grupa, której farba jest już zmieniona (nie najnowsza), świeci się na czerwono na stanowisku Produkcja automat i w panelu kierownika, dopóki ktoś nie wpisze jej zużycia. `frontend/src/components/PaintRunsPanel.tsx:24@!run.is_current`, `125-126@mode === "alarm"`, `frontend/src/pages/ManagerPanelPage.tsx:1329@PaintRunsPanel mode="alarm"`
- ✅ Kolor „śledzony" tylko z realną historią ruchów (nie placeholder 0 kg). `app/paints/service.py:154-158`
- ✅ Typy ruchów: saldo otwarcia, dostawa, zużycie automatu, korekta ręczna; dostawy/korekty tylko biuro. `app/shared/enums.py:95-99`

## 11. Statystyki

- ✅ Przerób (m²) przypisywany do **dnia zakończenia pakowania**; poprawki **wykluczone** (ich sztuki policzono już na rodzicu — bez podwójnego liczenia). `app/manager/service.py:253-346@WorkOrder.is_correction == False`
- ✅ Przebieg Decoral to **osobna, dodatkowa** seria m² w dniu jego zakończenia. `app/manager/service.py:387-421@decoral_done_events`
- ✅ Każda statystyka produkcji cięta dwojako naraz: wg metody (ręczna/automat) i powłoki (RAL/Decoral). `app/manager/service.py:149-156@_COATING_SEGMENTS`
- ✅ „Zdarzenie poprawki" ma jedną wspólną definicję łączącą partie poprawkowe + dzieci „P" + poprawione od razu. `app/manager/repository.py:105-128`
- ✅ Czas cyklu = najświeższy zakończony przebieg etapu; czas wiodący = pierwszy start → zakończenie pakowania. `app/manager/service.py:454-671@def get_cycle_time_stats`
- ✅ Starzenie WIP = zlecenia aktualnie „w trakcie", liczone od ostatniego wejścia w trakcie. `app/manager/service.py:672-763@def get_work_in_progress_aging`
- ✅ **(ZMIANA #9 zrobiona 2026-06-26)** długość zmiany per dzień jest **zapisywana** (`day_shift_lengths`, ustawia kierownik) i wyznacza próg 800/500 + godziny 14/8 dnia — używana przez **oba**: miarę „dobrego dnia" **i** plan przyszłości (ZMIANA #4); dzień bez zapisu domyślnie LONG. `app/manager/service.py:884-898@floor_m2(day_shift)`, `app/manager/models.py` (`DayShiftLength`)
