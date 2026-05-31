# Mapa decyzji na implementacje

Status: robocza mapa na czas oczekiwania na odpowiedzi fabryki. Nie wprowadza nowych zasad. Sluzy do szybkiego przetlumaczenia odpowiedzi kolegi na bezpieczne zadania techniczne.

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

Jesli odpowiedz brzmi: numer nadal opcjonalny i nieunikalny:

- Brak wymaganej implementacji.
- Mozliwe drobne usprawnienie: raport/lista potencjalnych duplikatow jako narzedzie biura.

Jesli numer ma byc wymagany:

- Zmienic Pydantic create/update validation.
- Zmienic frontend create form i komunikaty.
- Dodac migracje albo precheck dla istniejacych pustych danych.
- Ustalic wyjatki: poprawki, zlecenia awaryjne, telefoniczne, stare rekordy.
- Testy: API create/patch, frontend validation, migracja dirty-data.

Jesli numer ma byc unikalny:

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
- Przy mieszanych profilach/akcesoriach czesciowa poprawka nie zgaduje podzialu.

Jesli fabryka potwierdzi obecny model:

- Brak zmian.

Jesli przy poprawce czesciowej trzeba wpisac osobno profile i akcesoria:

- Rozszerzyc request pakowania o per-kategoria correction quantities.
- Dodac walidacje: profile_poprawka + akcesoria_poprawka = correction_quantity.
- Tworzenie child correction powinno przenosic dokladne wartosci.
- UI pakowania musi miec dodatkowe pola tylko wtedy, gdy rodzic ma mieszane kategorie.
- Testy: API, service, frontend bilans, DB/read model.

Ryzyko:

- Dodanie pol kategorii do pakowania zwieksza obciazenie operatora. Warto wdrozyc tylko jesli realnie potrzebne.

## 3. Dokument kontroli jakosci / dokument produkcyjny

Obecnie:

- Funkcja nie jest zaimplementowana.
- Wiadomo, ze fabryka ma gotowy szablon.

Minimum odpowiedzi potrzebne do implementacji:

- Format szablonu: Excel, Word, PDF, inny.
- Moment generowania: przy przyjeciu, po planowaniu, przed produkcja, po produkcji, przy wydaniu.
- Mapowanie pol: ktore pole dokumentu bierze dane z systemu, a ktore zostaje reczne.
- Czy wygenerowana kopia ma byc zapisywana jako zalacznik/audyt.

Jesli szablon to Excel:

- Najprostsza sciezka: wypelnianie pliku `.xlsx`, zapis jako zalacznik albo download.
- Dodac zaleznosc tylko po sprawdzeniu biblioteki i testow.
- Testy: generowanie pliku, mapowanie pol, uprawnienia, pobieranie.

Jesli szablon to PDF:

- Trzeba ustalic czy PDF jest formularzem z polami, czy statycznym wzorem do renderowania.
- Statyczny PDF moze wymagac generowania nowego dokumentu z layoutem, a to jest wiekszy projekt.

Ryzyko:

- Bez prawdziwego szablonu latwo zbudowac ladny, ale nieuzywany dokument.

## 4. Magazyn farb i zuzycie

Obecnie:

- Zlecenie ma producenta farby i RAL.
- Nie ma modelu stanu magazynowego ani ruchow magazynowych.
- Automat ma w przyszlosci wpisywac zuzycie farby.

Minimum odpowiedzi potrzebne do implementacji:

- Jednostka: kg, litry, opakowania, inna.
- Czy sledzimy partie/batche farby.
- Czy stan jest per producent + RAL, czy per konkretny produkt/partia.
- Kiedy zdejmowac ze stanu: planowanie, start, wpis zuzycia, koniec zlecenia.
- Kto moze dodawac stan, kto moze wpisywac zuzycie, kto moze korygowac.
- Czy stan ujemny jest dozwolony.

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

- Office i manager moga oznaczyc READY jako wydane klientowi.
- Zapisuje sie data/czas wydania.
- Mozna cofnac oznaczenie.
- Produkcja nie moze tego zmieniac.

Jesli potrzebne sa dodatkowe pola:

- Osoba/stacja wydajaca: stacja juz jest w audycie; login osobisty wymaga osobnego modelu uzytkownika.
- Komentarz wydania: dodac request field + audit details.
- Dokument wydania: powiazac z modulem dokumentow/zalacznikow.

Ryzyko:

- Nie mieszac wydania logistycznego z produkcyjnym `READY`.

## 7. Dostepy, stanowiska, loginy

Obecnie:

- System uzywa wspolnej tozsamosci stanowiska przez `X-Station-Id`.
- Backend blokuje zle akcje stacji.
- Audyt zapisuje stacje i request ID.

Jesli wspolne stanowiska wystarczaja:

- Brak zmian poza przyszlymi uprawnieniami dla farb/dokumentow.

Jesli potrzebne sa loginy osobiste:

- To osobny projekt: uzytkownicy, sesje, role, hasla/PIN, audyt operatora, migracja UI.
- Trzeba ustalic czy login jest wymagany zawsze, czy tylko do wybranych akcji.

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

1. Najpierw male decyzje o niskim ryzyku: numer zewnetrzny required/unique, finalne filtry raportu poprawek.
2. Potem workflow-zasoby: pakowanie jako zasob, jesli potwierdzone.
3. Potem dokument QC, jesli szablon i mapowanie sa dostepne.
4. Na koncu magazyn farb, bo to najwiekszy nowy model i wymaga najwiecej edge-case'ow.

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