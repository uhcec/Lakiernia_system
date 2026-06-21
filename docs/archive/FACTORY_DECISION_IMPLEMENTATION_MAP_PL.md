> ARCHIVED — frozen historical snapshot as of 2026-06-01. Living truth lives in docs/WORKFLOW.md / docs/FACTORY_DOMAIN_MODEL.md.

# Mapa decyzji na implementacje

Status: robocza mapa po odpowiedziach fabryki z 2026-06-01. Sluzy do szybkiego przetlumaczenia potwierdzonych odpowiedzi na bezpieczne zadania techniczne.

> ⚠️ **MIGAWKA HISTORYCZNA (2026-06-01) — NIE JEST AKTUALNYM ZRODLEM PRAWDY.** Zachowana jako zapis
> decyzji z tamtego dnia. Czesc tresci jest juz nieaktualna wzgledem `docs/WORKFLOW.md` i kodu —
> weryfikuj kazda pozycje wzgledem aktualnych dokow (`docs/DOC_COHERENCE_AUDIT.md`). Znane rozbieznosci:
> sekcja 3 (dokument QC jest **zaimplementowany**), sekcja 4 (prog formuly farby to **100 m², nie 70 m²**,
> a ostrzezenie o brakach farby przy przyjeciu **dziala**), sekcja 8 (pakowanie ma juz model N stanowisk
> — `PACKING:1..N`, domyslnie 2).

Zasada pracy: jesli odpowiedz dotyczy realnej polityki fabryki, najpierw aktualizujemy `docs/WORKFLOW.md` i `docs/FACTORY_USAGE_NOTES.md`, potem dodajemy testy, potem implementujemy najmniejsza spojna zmiane.

## Jak klasyfikowac odpowiedzi

- `Decyzja kompletna`: wiadomo co ma robic system, kto wykonuje akcje, kiedy, i co z bledem/cofnieciem.
- `Decyzja czesciowa`: wiadomo kierunek, ale brakuje pola, uprawnienia, momentu w workflow albo zachowania edge-case.
- `Opinia/intuicja`: nie implementowac; przepisac na pytanie doprecyzowujace.
- `Sprzeczne z obecnym workflow`: zatrzymac, opisac konflikt z `docs/WORKFLOW.md`, zapytac uzytkownika przed kodem.

## 1. Numer zewnetrzny zlecenia

Obecnie:

- Pole istnieje, jest opcjonalne, tekstowe, nieunikalne.
- Lista biura umie szukac po fragmencie numeru.
- Poprawki dziedzicza numer zewnetrzny rodzica.

Potwierdzona decyzja po 2026-06-01:

- Brak wymaganej implementacji.
- Mozliwe drobne usprawnienie: raport/lista potencjalnych duplikatow jako narzedzie biura.
- Numer zewnetrzny zostaje opcjonalny, nieunikalny i duplikaty sa dozwolone bez ostrzezenia/blokady.

Jesli przyszla polityka zmieni numer na wymagany:

- Zmienic Pydantic create/update validation.
- Zmienic frontend create form i komunikaty.
- Dodac migracje albo precheck dla istniejacych pustych danych.
- Ustalic wyjatki: poprawki, zlecenia awaryjne, telefoniczne, stare rekordy.
- Testy: API create/patch, frontend validation, migracja dirty-data.

Jesli przyszla polityka zmieni numer na unikalny:

- Ustalic zakres: globalnie czy per klient.
- Ustalic czy puste wartosci sa dozwolone i czy wiele pustych jest OK.
- Dodac indeks unikalny odpowiedni dla SQLite/Alembic.
- Przed migracja dodac detekcje duplikatow i kontrolowany blad.
- Testy: DB constraint, API conflict, wyszukiwanie, poprawki dziedziczace numer.

Ryzyko:

- Zbyt twarda unikalnosc moze blokowac realne powtarzajace sie numery klienta.

## 2. Profile i akcesoria

Obecnie:

- Gdy oba znane: `profile + akcesoria = ilosc calkowita`.
- Kazde znane pole moze byc od `0` do `total_quantity`.
- Jesli podzial nieznany, uzywa sie `*_to_count` i `NULL`.
- Przy poprawce pakowanie zbiera osobno liczbe profili i akcesoriow do poprawki.

Status po 2026-06-01:

- Model przyjecia jest potwierdzony: profile + akcesoria = ilosc calkowita, brak innych kategorii, nieznany podzial moze byc `do policzenia`.
- Model poprawki jest zaimplementowany: przy poprawce pracownik podaje osobno ile profili i ile akcesoriow idzie do poprawki.

Wdrozone dla poprawki czesciowej:

- Request pakowania ma per-kategoria correction quantities.
- Walidacja wymaga: profile_poprawka + akcesoria_poprawka = correction_quantity.
- Tworzenie child correction przenosi dokladne wartosci.
- UI pakowania pokazuje dodatkowe pola zawsze, gdy correction quantity jest wieksze od zera.
- Testy: API, service, frontend bilans, chaos/helper payloads.

Ryzyko:

- Dodanie pol kategorii do pakowania zwieksza obciazenie operatora. Wdrozone jako jawny wymog, zeby nie zgadywac kategorii w poprawkach.

## 3. Dokument kontroli jakosci / dokument produkcyjny

Obecnie:

- Funkcja nie jest zaimplementowana.
- Wiadomo, ze fabryka ma gotowy szablon Excel.
- Dokument generuje biuro przed produkcja.
- System ma wypelnic tylko numer wewnetrzny, farbe i firme, chyba ze prawdziwy szablon pokaze dodatkowe pola do recznego wypelnienia.
- Dokument jest tylko do wydruku; zapis wygenerowanych kopii nie jest potwierdzony.

Minimum nadal potrzebne do implementacji:

- Prawdziwy plik Excel ze wzorem.
- Mapowanie konkretnych komorek: numer wewnetrzny, farba, firma.
- Decyzja, gdzie trzymamy szablon i kto moze go podmienic.
- Potwierdzenie, czy generowanie powinno zostawic slad audytu mimo braku zapisu kopii.

Sciezka dla potwierdzonego szablonu Excel:

- Najprostsza sciezka: wypelnianie pliku `.xlsx` i pobranie/wydruk; nie zapisywac kopii jako zalacznika, dopoki nie ma osobnej decyzji audytowej.
- Dodac zaleznosc tylko po sprawdzeniu biblioteki i testow.
- Testy: generowanie pliku, mapowanie pol, uprawnienia, pobieranie.

Ryzyko:

- Bez prawdziwego szablonu latwo zbudowac ladny, ale nieuzywany dokument.

## 4. Magazyn farb i zuzycie

Obecnie:

- Zlecenie ma producenta farby, RAL, kod farby i planowana ilosc farby [kg] zapisana bezposrednio na zleceniu.
- Nadal nie ma wspolnego modelu stanu magazynowego ani ruchow magazynowych.
- Automat wpisuje zuzycie farby bezposrednio na zleceniu.
- UI automatu uzywa modelu kartonow `20 kg` / `25 kg` i pozostalosci w ostatnim kartonie, a backend zapisuje netto zuzyte kg.
- Potwierdzono kg jako jednostke.
- Stan ma byc laczny dla producenta + RAL/koloru, nie per batch magazynowy.
- Przyjecie farby powinno zbierac producenta, RAL/kolor, ilosc kg, dostawce i prawdopodobnie partie jako metadane przyjecia; bez ceny, uwag i recznej daty.
- System ma wykrywac i zglaszac za mala ilosc farby.
- Zapotrzebowanie: ponizej 70 m2 -> `area_m2 / 4`; powyzej 70 m2 -> `area_m2 / 6`.
- Odpowiedz fabryki mowi, ze farba ma byc zdejmowana ze stanu po wpisaniu zlecenia wedlug zapotrzebowania.
- Zuzycie wpisuje recznie produkcja automatyczna.
- Pakowania automatycznego standardowego nie powinno dac sie zakonczyc bez wpisanego zuzycia farby.
- Automatyczne poprawki nie maja jeszcze wlasnej alokacji farby i nie sa objete obecnym hard-blockiem.

Minimum nadal potrzebne do pelnego modulu magazynu:

- Czy ruch po wpisaniu zlecenia jest twardym zdjeciem ze stanu czy rezerwacja, oraz jak rozliczamy go z pozniejszym faktycznym zuzyciem wpisanym na automacie.
- Czy brak farby jest twarda blokada, czy ostrzezenie wymagajace obejscia.
- Jak traktowac dokladnie 70 m2.
- Czy partia ma byc tylko metadana przyjecia, czy ma byc wyszukiwalna/raportowana mimo braku stocku per batch.
- Kto moze dodawac stan i kto moze korygowac pomylki magazynowe.
- Jak automatyczne poprawki maja dostawac i rozliczac farbe.

Prawdopodobny model, jesli odpowiedzi beda kompletne:

- `paint_items` albo `paint_stock_items`: producent, RAL, opcjonalna partia, jednostka.
- `paint_stock_movements`: przyjecie, zuzycie, korekta, powiazanie ze zleceniem/stacja/audytem.
- Ekran biura/magazynu do przyjecia farby.
- Ekran automatu do wpisania zuzycia.
- Raport stanu i ruchow.

Testy:

- DB constraints dla ilosci i jednostek.
- API create stock movement.
- Deduction timing.
- Cofniecie/korekta.
- Wrong-station authorization.
- Chaos/double-submit dla zuzycia.

Ryzyko:

- To jest najwiekszy nowy modul. Nie zaczynac od pelnego ERP; zaczac od minimalnych ruchow magazynowych, jesli polityka jest jasna.

## 5. Raporty poprawek

Obecnie:

- Manager widzi agregat po `correction_reason_category`.
- Jest eksport CSV.
- Kategorie sa tekstowe/elastyczne.
- Po 2026-06-01 obecny zestaw kategorii jest OK na start.
- UI powinno pozostac proste i nie pozwalac operatorowi dopisywac wlasnych kategorii.
- Najwazniejszy wymiar raportu to powod poprawki; dodatkowe metryki/procenty nie sa teraz potrzebne.
- Panel w systemie i eksport sa potrzebne, czyli obecny kierunek jest zgodny.

Jesli lista kategorii ma byc finalna i sztywna:

- Zmienic UI na kontrolowana liste.
- Rozwazyc enum albo tabela slownikowa.
- Migracja starych kategorii lub sekcja `inne/legacy`.
- Testy walidacji i raportu.

Jesli raport ma miec filtry:

- Najpierw dodac backend query params: data od/do, klient, numer zlecenia, RAL, technologia, kategoria.
- Potem UI managera.
- CSV musi uzywac tych samych filtrow.
- Testy API + frontend.

Jesli raport ma pokazywac procent poprawek:

- Ustalic mianownik: wszystkie zlecenia, wszystkie sztuki, sztuki spakowane, okres czasu, klient.
- Bez tego procent moze byc mylacy.

## 6. Wydanie gotowego zlecenia

Obecnie:

- Tylko office moze oznaczyc READY jako wydane klientowi.
- Zapisuje sie data/czas wydania.
- Mozna cofnac oznaczenie.
- Manager i produkcja nie moga tego zmieniac.
- Po 2026-06-01 target policy zostalo wdrozone na poziomie station identity: wydanie oznacza biuro, nie manager.
- Docelowo program ma generowac dokument WZ dla gotowych zlecen.

Jesli potrzebne sa dodatkowe pola:

- Osoba/stacja wydajaca: stacja juz jest w audycie; login osobisty wymaga osobnego modelu uzytkownika.
- Komentarz wydania: dodac request field + audit details.
- Dokument wydania: powiazac z modulem dokumentow/zalacznikow.
- Potrzebne: szablon/format WZ, pola, moment generowania, czy WZ jest tylko do druku czy ma byc archiwizowany.

Ryzyko:

- Nie mieszac wydania logistycznego z produkcyjnym `READY`.

## 7. Dostepy, stanowiska, loginy

Obecnie:

- System uzywa wspolnej tozsamosci stanowiska przez `X-Station-Id`.
- Backend blokuje zle akcje stacji.
- Audyt zapisuje stacje i request ID.
- Po 2026-06-01 wspolne stanowisko/tablet nie wystarcza jako docelowy model dostepu.
- Produkcja ma logowac sie na stanowiska; biuro ma miec indywidualne loginy.
- Statystyki maja byc tylko dla managera.
- Produkcja nie ma miec mozliwosci edycji danych zlecenia, tylko akcje etapow i podglad zalacznikow/szczegolow.

Jesli potrzebne sa loginy osobiste:

- To osobny projekt: uzytkownicy, sesje, role, hasla/PIN, audyt operatora, migracja UI.
- Trzeba ustalic czy login jest wymagany zawsze, czy tylko do wybranych akcji.
- Trzeba ustalic, czy produkcyjne logowanie identyfikuje osobe, stanowisko, czy oba naraz.

Jesli manager ma miec akcje niedostepne dla biura:

- Rozdzielic obecna polityke office/manager tam, gdzie teraz sa rowne.
- Dodac testy 403 dla kazdej akcji.

## 8. Pakowanie jako zasob wyłączny

Obecnie:

- Nie ma `PACKING` resource lock.
- Pakowanie jest autoryzowane stacyjnie.
- Automatyczne zlecenia w zawieszaniu sa widoczne w pakowaniu jako read-only.

Jesli pakowanie moze miec tylko jedno aktywne zlecenie:

- Dodac zasob `PACKING` do lockow procesowych.
- Ustalic, kiedy lock sie zajmuje: start pakowania, pierwsza edycja formularza, czy finalne zatwierdzenie.
- Ustalic, czy widoczne automaty oczekujace licza sie jako zajecie pakowania. Najbezpieczniej: nie, dopoki pakowanie nie moze ich aktywnie obrabiac.
- UI musi pokazac blokade i powod.
- Testy: service/API conflicts, chaos, frontend disabled state.

Ryzyko:

- Zbyt wczesne zajmowanie pakowania moze blokowac realna prace, szczegolnie przy automatach czekajacych na koniec zawieszania.

## Rekomendowana kolejnosc po odpowiedziach

1. Dokument QC, ale dopiero po otrzymaniu pliku Excel i mapowania komorek.
2. Rownolegle zaprojektowac auth/loginy, bo wplywa na manager-only statystyki, audyt i globalna nawigacje.
3. Magazyn farb jako osobny wiekszy modul po doprecyzowaniu timingow rezerwacji/zuzycia i zachowania przy braku farby.
4. WZ po ustaleniu szablonu i powiazaniu z office-only wydaniem.
5. Pakowanie jako zasob zostaje osobnym pytaniem, bo odpowiedzi z 2026-06-01 go nie rozstrzygnely.

## Format przepisywania odpowiedzi kolegi

Przy kazdej odpowiedzi warto zapisac:

- Decyzja: co ma robic system.
- Zakres: ktore role/stacje dotyczy.
- Moment: kiedy w workflow to sie dzieje.
- Dane: jakie pola sa potrzebne.
- Wyjatki: kiedy wolno inaczej.
- Cofniecie/korekta: czy mozna naprawic blad.
- Audyt: co trzeba zapisac.
- Testy: jaki przypadek musi przejsc.
- Status: kompletne / wymaga doprecyzowania / sprzeczne z obecna polityka.