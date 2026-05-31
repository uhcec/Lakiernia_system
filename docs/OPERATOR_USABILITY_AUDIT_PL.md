# Audyt uzywalnosci operatorow

Status: roboczy audyt systemu na 2026-05-31. Ten dokument nie jest zrodlem prawdy o polityce fabryki. Zrodlem semantyki pozostaje `docs/WORKFLOW.md`, a pytania otwarte sa sledzone w `docs/WORKFLOW_VALIDATION_CHECKLIST.md`.

Cel: opisac, co obecny system daje kazdej roli, gdzie jest ergonomicznie dobry, gdzie moze wprowadzac w blad, oraz co warto sprawdzic z uzytkownikami zanim dopiszemy kolejne funkcje.

## Szybki wniosek

System jest teraz wystarczajaco spojny, zeby prowadzic normalny przeplyw zlecen: biuro przyjmuje, kierownik planuje, stanowiska widza swoje aktywne prace, pakowanie rozdziela OK/poprawki, poprawki wracaja przez planowanie, a gotowe zlecenia mozna oznaczac jako wydane.

Najwieksze ryzyka uzywalnosci nie wynikaja juz z oczywistych bledow ekranow, tylko z brakujacych decyzji biznesowych: magazyn farb, dokument kontroli jakosci, polityka numeru zewnetrznego, ewentualna wyłącznosc pakowania i ostateczny ksztalt raportow poprawek.

## Nawigacja i role

Obecne glowne wejscia w aplikacji:

- `/zlecenia` - biuro, lista zlecen.
- `/zlecenia/nowe` - biuro, przyjecie zlecenia.
- `/zlecenia/:id` - szczegoly zlecenia, zalaczniki, historia, wydanie.
- `/kierownik` - planowanie, kolejka, poprawki, statystyki.
- `/przygotowanie` - przygotowanie powierzchni.
- `/zawieszanie` - zawieszanie automatycznych zlecen.
- `/produkcja-reczna` - produkcja reczna.
- `/produkcja-automat` - produkcja automatyczna / podglad automatycznego przeplywu.
- `/pakowanie` - pakowanie, kontrola jakosci, poprawki.
- `/produkcja-decoral` - produkcja Decoral.
- `/audyt` - techniczny/administracyjny podglad zdarzen.

## Biuro

Obecnie obslugiwane zadania:

- Dodanie nowego zlecenia z klientem, technologia, RAL, producentem farby, data przyjecia, planowanym odbiorem, iloscia calkowita, powierzchnia, profile/akcesoria, `Przemalowanka`, `Ocynk`, numerem zewnetrznym i notatkami.
- Oznaczenie zlecenia jako niekompletne na przyjeciu.
- Przeglad zlecen w praktycznych grupach: `Zlecenia`, `Na produkcji`, `Gotowe`.
- Wyszukiwanie po numerze zewnetrznym.
- Podglad roznicy miedzy iloscia deklarowana a policzona na przygotowaniu powierzchni.
- Obsluga zalacznikow PDF w szczegolach zlecenia.
- Oznaczenie gotowego zlecenia jako wydane klientowi.

Mocne strony:

- Biuro widzi szeroki kontekst procesu bez udawania, ze status frontendu jest zrodlem prawdy.
- Gotowe zlecenia sa oddzielone od produkcji i nie pokazuja aktywnych licznikow.
- Zalaczniki sa dostepne w szczegolach, a produkcja moze je pobierac bez uprawnien biurowych.

Ryzyka i pytania:

- Numer zewnetrzny jest opcjonalny i nieunikalny; to jest bezpieczne technicznie, ale moze byc za slabe organizacyjnie.
- Przyjecie zlecenia nie wymaga jeszcze danych magazynu farby, bo model magazynu nie jest zdecydowany.
- Dokument kontroli jakosci nie istnieje, bo brakuje szablonu i mapowania pol.

## Kierownik

Obecnie obslugiwane zadania:

- Planowanie normalnych zlecen i poprawek.
- Nadanie typu produkcji: reczna albo automatyczna.
- Ustawienie pozycji w jednej globalnej kolejce.
- Przestawianie aktywnej kolejki.
- Podglad, czy zlecenie jest blokowane przez znane zasoby: `HANGING` lub `AUTOMATIC_LINE`.
- Podglad kontekstu poprawek: rodzic, planowany odbior, statusy.
- Statystyka powodow poprawek i eksport CSV.
- Liczniki `Zlecenia`, `Na produkcji`, `Gotowe`.

Mocne strony:

- Jedna globalna kolejka dobrze pasuje do potwierdzonej polityki.
- Zakonczone zlecenia nie blokuja aktywnych pozycji planowania.
- Poprawki nie sa automatycznie priorytetyzowane, wiec manager zachowuje decyzje.

Ryzyka i pytania:

- Raport poprawek jest minimalny: bez filtrow daty, klienta, RAL, technologii.
- Kategorie powodow poprawek sa elastyczne, bo lista nie jest finalna.
- Jesli potrzebna jest historia pierwotnej pozycji kolejki, trzeba dodac osobne pole/audyt, nie przeciazac aktualnej `queue_position`.

## Przygotowanie powierzchni

Obecnie obslugiwane zadania:

- Widok zlecen oczekujacych/aktywnych na przygotowaniu.
- Start przygotowania bez wymogu wpisania ilosci.
- Zakonczenie przygotowania z wymaganym wpisaniem policzonej ilosci.
- Przekazanie policzonej ilosci jako operacyjnej prawdy dla dalszych etapow.

Mocne strony:

- Operator nie widzi kontekstu roznicy deklarowana-vs-policzona, tylko wpisuje swoja prawde operacyjna.
- Zaczecie pracy nie jest blokowane przez brak policzonej ilosci.

Ryzyka i pytania:

- Jesli w praktyce liczenie zdarza sie czesciowo lub przez kilka osob, obecny model ma jedno koncowe `counted_quantity`, bez rozbitej historii liczenia.
- Brak osobnej akcji potwierdzania duzej roznicy jest obecnie potwierdzonym uproszczeniem.

## Zawieszanie

Obecnie obslugiwane zadania:

- Widok automatycznych zlecen wymagajacych zawieszenia.
- Start i koniec zawieszania.
- Zwolnienie zasobu zawieszania po zakonczeniu zawieszania.
- Szczegoly i zalaczniki dostepne z kontekstem stacji.

Mocne strony:

- Tylko jedno aktywne zawieszanie naraz.
- Nastepne zlecenie moze wejsc na zawieszanie po zakonczeniu poprzedniego zawieszania, nawet jesli poprzednie zajmuje linie automatyczna.

Ryzyka i pytania:

- Jesli realnie istnieja rownolegle haki/linie zawieszania, model jednego zasobu bylby zbyt waski. Na razie polityka mowi, ze jedno aktywne zawieszanie jest poprawne.

## Produkcja automatyczna

Obecnie obslugiwane zadania:

- Podglad automatycznych zlecen gotowych do zawieszania lub bedacych w zawieszaniu.
- Podglad aktywnego przeplywu automatycznego bez recznych start/finish dla produkcji automatycznej.
- Szczegoly i zalaczniki.

Mocne strony:

- Operator automatu widzi dzienny przeplyw zanim linia jest fizycznie zajeta.
- System rozdziela zasob zawieszania od zasobu linii automatycznej.

Ryzyka i pytania:

- Tablet automatyczny ma miec wpisywanie zuzycia farby, ale nie ma jeszcze modelu magazynu i zuzycia.
- Nie jest zdecydowane, czy automat kiedys potrzebuje wlasnych start/finish produkcji; obecnie nie.

## Produkcja reczna

Obecnie obslugiwane zadania:

- Widok manualnych zlecen produkcyjnych.
- Start i koniec produkcji recznej.
- Widoczne informacje operacyjne: metry, farba, klient, kolejka, znaczniki typu.
- Szczegoly i zalaczniki.

Mocne strony:

- Ekran jest skupiony na akcji stanowiska, nie na danych biurowych.
- `Ocynk` i `Przemalowanka` sa widoczne jako markery robocze.

Ryzyka i pytania:

- Jesli produkcja reczna ma wpisywac zuzycie farby albo inne parametry wykonania, trzeba to dodac razem z modelem magazynu/audytu.

## Pakowanie

Obecnie obslugiwane zadania:

- Widok zlecen gotowych do pakowania.
- Widok automatycznych zlecen jeszcze w zawieszaniu jako wiersze/cardy oczekujace, bez mozliwosci zakonczenia pakowania.
- Wpisanie ilosci policzonej, OK i do poprawki.
- Walidacja bilansu pakowania.
- Wymaganie powodu poprawki, gdy powstaje poprawka.
- Automatyczne utworzenie zlecenia poprawkowego.

Mocne strony:

- Bilans pakowania jest czytelny i ogranicza pomylki.
- Aktywne automaty w zawieszaniu sa widoczne, ale nie da sie ich zakonczyc za wczesnie.
- Poprawki sa od razu materializowane jako osobne zlecenia do planowania.

Ryzyka i pytania:

- Wyłącznosc fizyczna pakowania jest nadal otwarta. Jesli pakowanie moze miec tylko jedno aktywnie rozpoczete zlecenie, trzeba dodac zasob `PACKING`.
- Przy mieszanych profilach/akcesoriach poprawka czesciowa ma tylko jedna ilosc poprawki; system nie zgaduje podzialu kategorii. Jesli fabryka potrzebuje dokladnego podzialu, pakowanie musi dostac pola per kategoria.

## Decoral

Obecnie obslugiwane zadania:

- Widok zlecen Decoral po pakowaniu/splocie jakosciowym.
- Start i koniec Decoral.
- Zakonczenie zlecen Decoral bez dalszego pakowania, jesli nie ma poprawek.

Mocne strony:

- Decoral jest oddzielnym stanowiskiem koncowym dla wlasnej technologii.
- RAL/Decoral i `Ocynk` moga sie laczyc jako niezalezne znaczniki.

Ryzyka i pytania:

- Jesli Decoral potrzebuje osobnego dokumentu, parametrow procesu albo kontroli jakosci, trzeba to powiazac z dokumentem produkcyjnym.

## Audyt

Obecnie obslugiwane zadania:

- Przeglad zdarzen wedlug zlecenia, typu zdarzenia, stacji, request ID, celu i dat.
- Eksport CSV.
- Podglad szczegolow zdarzen.

Mocne strony:

- Daje techniczne sledzenie kto/stacja/co zmienil.
- Dobrze pasuje do modelu wspolnych stanowisk bez logowania osobistego.

Ryzyka i pytania:

- Jesli beda loginy osobiste, audyt trzeba rozszerzyc o operatora/uzytkownika, nie tylko stacje.
- Audyt jest raczej narzedziem administracyjnym niz ekranem dla operatora.

## Najwazniejsze obserwacje przekrojowe

- Frontend powinien nadal wyswietlac backendowy `process_status`, a nie zgadywac workflow z ilosci.
- Szczegoly zlecenia dzialaja jako bezpieczny wspolny widok dla biura, managera i stacji, ale stacje nie powinny dostawac mutacji biurowych.
- Zalaczniki sa dobrze umieszczone w szczegolach; dedykowana szuflada na tabletach bylaby tylko usprawnieniem ergonomii, nie koniecznoscia semantyczna.
- Najbardziej wartosciowe kolejne prace beda po odpowiedziach: magazyn farb, dokument QC, polityka numeru zewnetrznego, pakowanie jako zasob, finalne raporty poprawek.

## Proponowany test z uzytkownikami

Przejsc z kolega lub operatorem przez 7 scenariuszy:

1. Biuro tworzy normalne RAL manualne zlecenie.
2. Kierownik planuje je do produkcji recznej.
3. Przygotowanie wpisuje inna ilosc niz deklarowana.
4. Produkcja reczna konczy etap.
5. Pakowanie dzieli na OK i poprawke.
6. Kierownik planuje poprawke.
7. Biuro oznacza finalnie gotowe zlecenie jako wydane.

Podczas przejscia notowac tylko trzy rzeczy: co uzytkownik rozumie od razu, gdzie szuka informacji, gdzie ekran moze sugerowac zla akcje.