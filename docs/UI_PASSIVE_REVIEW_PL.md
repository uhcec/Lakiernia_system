# Pasywny przeglad UI

Status: roboczy przeglad zrodel frontendu, bez zmiany zachowania aplikacji.

Ten dokument nie jest specyfikacja workflow. To lista obserwacji z UI, ktore moga pomoc wybrac kolejne male, bezpieczne kroki albo przygotowac rozmowe z uzytkownikami hali. Dla znaczenia procesu nadal obowiazuja `docs/WORKFLOW.md`, `docs/WORKFLOW_VALIDATION_CHECKLIST.md` i decyzje fabryczne.

## Zakres przegladu

Przejrzane glowne ekrany:

- globalny layout i nawigacja,
- lista zlecen biura,
- formularz tworzenia zlecenia,
- panel kierownika,
- wspolne karty stanowisk,
- pakowanie,
- szczegoly zlecenia,
- audyt.

Nie robilem jeszcze testu w przegladarce na realnym tablecie ani przejscia z operatorem. To jest pasywna ocena po kodzie i tekstach UI.

## Najkrotszy wniosek

UI ma juz sensowny rdzen: pokazuje stan z backendu, rozdziela aktywne i historyczne ilosci, zachowuje kontekst stacji w linkach szczegolow i nie probuje zgadywac workflow z samych liczb.

Najwieksze ryzyka nie sa teraz techniczne, tylko operatorskie:

- jedna globalna nawigacja pokazuje wszystkim role i panele, ktore w realnej fabryce moga nie byc dla nich przeznaczone,
- akcja `Cofnij` jest widoczna jako normalny element pracy stanowiska, ale nie mamy pewnosci, czy to ma byc zwykla akcja operatora czy awaryjne cofniecie,
- formularze biurowe i managerskie sa funkcjonalne, ale wymagaja drobnego uporzadkowania, zeby mniej zalezec od pamieci operatora.

## Co wyglada zdrowo

- Listy i karty uzywaja backendowego `process_status` oraz stanowiskowych statusow etapu, zamiast lokalnie wyliczac znaczenie workflow.
- Widoki zakonczone unikaja najbardziej niebezpiecznego bledu typu `0 / X` jako aktywny postep.
- Stanowiska pokazuja karty z jednym zleceniem naraz, co jest lepsze dla tabletu niz duza tabela.
- Pakowanie ma bilans `Policzono = OK + Poprawki`, wiec najwazniejsza kontrola jakosci jest widoczna przed zapisem.
- Szczegoly zlecenia zachowuja tryb stacji przez `station_context`, wiec operator moze otworzyc zalaczniki bez przypadkowego dostepu do mutacji biura.
- Panel kierownika rozdziela `Do zaplanowania`, `Aktywne` i `Zakonczone`, a zakonczone zostaja tylko pogladowo.

## Bezpieczne poprawki UI

Te rzeczy nie powinny wymagac nowej decyzji workflow, bo dotycza czytelnosci albo spojnosc tekstu z istniejacym zachowaniem.

1. Licznik na liscie biura

   Ekran zlecen pokazuje `Widocznych rekordow`, ale wartosc pochodzi z calego pobranego zestawu, nie z aktywnej zakladki. Przy filtrze `Zlecenia / Na produkcji / Gotowe` moze to mylic.

   Proponowany kierunek: zmienic etykiete na `Pobrane rekordy` albo licznik na `visibleWorkOrders.length`.

2. Podpowiedz dla profili i akcesoriow w formularzu tworzenia

   Regula `Profile + Akcesoria = Ilosc calkowita` jest egzekwowana, ale operator widzi ja dopiero przez blad walidacji. To jest latwe miejsce na pomylke.

   Proponowany kierunek: dodac cicha podpowiedz lub maly licznik sumy przy polach profili/akcesoriow. Nie zgadywac wartosci automatycznie.

3. Placeholder na przygotowaniu powierzchni

   Pole `Policzono` ma `min=1`, ale placeholder `0`. To drobiazg, ale podpowiada wartosc, ktorej formularz nie akceptuje.

   Proponowany kierunek: placeholder `Podaj ilosc` albo pusty placeholder.

4. Pakowanie: neutralna instrukcja bilansu

   Pakowanie jest walidowane poprawnie, ale przy pustym `Policzono` operator nie ma stalego tekstu zasady poza dynamicznym bilansem.

   Proponowany kierunek: mala linia pomocnicza `OK + Poprawki musi rownac sie Policzono`. Bez automatycznego przepisywania OK, dopoki nie wiemy, czy to pasuje do praktyki.

5. Dlugosc szczegolow zlecenia

   Szczegoly zlecenia sa kompletne, ale bardzo dlugie: dane, planowanie, status, etapy, historia ilosci, zalaczniki i audyt sa na jednej osi. To jest dobre do audytu, slabsze do szybkiej pracy.

   Proponowany kierunek: dodac prosta nawigacje sekcji albo zakladki tylko w UI, bez zmiany danych.

6. Browserowe potwierdzenia

   `window.confirm` jest uzywane przy kompletowaniu przyjecia, wydaniu/cofnieciu wydania i usuwaniu zalacznika. Dziala, ale wyglada inaczej niz reszta aplikacji i ma malo kontekstu.

   Proponowany kierunek: pozniej zastapic spojnym modalem potwierdzenia, zwlaszcza dla akcji cofajacych albo usuwajacych.

7. Audyt: techniczne filtry

   Audyt jest przydatny developersko i managersko, ale filtry typu `Request ID`, `Typ obiektu`, `ID obiektu` sa techniczne.

   Proponowany kierunek: zostawic jako narzedzie serwisowe, a w przyszlosci dodac prostszy tryb managerski z filtrami po zleceniu, stacji i czasie.

## Wymaga decyzji lub rozmowy z fabryka

Aktualizacja 2026-06-01: czesc pytan ponizej dostala odpowiedzi. Globalna nawigacja i widocznosc statystyk trzeba projektowac razem z loginami/rolami; audyt i statystyki nie powinny polegac wylacznie na wspolnym tablecie. Pytanie o fizyczna wyłącznosc pakowania nadal pozostaje otwarte.

1. Globalna nawigacja dla wszystkich stanowisk

   Header pokazuje biuro, kierownika, wszystkie stanowiska, audyt i dodawanie zlecenia. Przy jednym wspolnym systemie jest to wygodne, ale na tablecie stanowiskowym operator moze widziec za duzo drog.

   Pytanie: czy docelowo urzadzenia maja miec tryb stanowiskowy/kioskowy z jednym panelem, czy pelna nawigacja jest akceptowalna?

2. Dostepnosc akcji `Cofnij`

   Karty zakonczonych etapow mowia, ze zlecenia sa dostepne do cofniecia, a przy statusie `DONE` akcja ma label `Cofnij`. To moze byc potrzebne do naprawy bledu, ale moze tez zachecac operatora do cofania zakonczonej pracy.

   Pytanie: kto moze cofac etap i w jakich sytuacjach: operator stanowiska, kierownik, biuro, czy tylko serwis/admin?

3. Drag-and-drop kolejki kierownika na tablecie

   Kolejka kierownika uzywa przeciagania. Na desktopie to jest szybkie, ale na tabletach HTML drag-and-drop bywa mniej pewny.

   Pytanie: czy kierownik bedzie uzywal glownie komputera z myszka, czy tabletu? Jesli tabletu, warto dodac przyciski gora/dol albo pole pozycji jako rownorzedna metode.

4. Widocznosc audytu w glownej nawigacji

   Bez logowania osobowego audyt jest read-only, ale nadal pokazuje historie operacyjna i techniczne dane. Po odpowiedziach z 2026-06-01 trzeba go traktowac jako ekran wymagajacy docelowych rol/uprawnien, nie jako ogolny panel dla wszystkich.

   Pytanie otwarte: kto poza managerem/serwisem ma miec dostep do audytu po wprowadzeniu loginow?

5. Pakowanie i zasob pakowania

   UI pokazuje pakowanie i oczekujace automaty, ale otwarta pozostaje decyzja, czy pakowanie samo w sobie ma miec ograniczenie zasobu / jedno aktywne pakowanie.

   Pytanie: czy pakowanie moze rownolegle obslugiwac kilka zlecen, czy potrzebny jest blokujacy zasob jak dla automatu?

6. Produkcja automatyczna i zuzycie farby

   Potwierdzono, ze produkcja automatyczna wpisuje zuzycie farby, a pakowanie automatycznego zlecenia nie powinno dac sie zakonczyc bez tego wpisu. Aktualne UI pokazuje producenta/RAL, ale nie ma kontrolowanego wpisu zuzycia farby.

   Otwarte: rezerwacja versus odjecie po faktycznym zuzyciu, zachowanie przy braku farby, dokladnie 70 m2 w formule.

7. Dokument kontroli jakosci

   Pakowanie pelni role kontroli jakosci, ale UI nie generuje jeszcze dokumentu QC z szablonu fabryki. Wiemy juz, ze szablon jest w Excelu, generuje go biuro przed produkcja, a systemowe pola to numer wewnetrzny, farba i firma.

   Otwarte: potrzebny jest realny plik i mapowanie komorek.

## Nie ruszac teraz

- Nie dodawac nowej logiki workflow po stronie frontendu. UI ma dalej wyswietlac backendowa prawde.
- Nie automatyzowac profili/akcesoriow przez domysly, np. nie dopelniac drugiego pola bez decyzji UX.
- Nie ukrywac akcji `Cofnij` bez decyzji, bo to moze byc obecny mechanizm ratunkowy.
- Nie projektowac finalnych uprawnien UI, dopoki nie ma decyzji o logowaniu, rolach albo trybie stanowiskowym.
- Nie rozszerzac audytu na ladniejszy raport managerski, dopoki nie wiemy, kto realnie bedzie go czytal i po co.

## Proponowana kolejnosc

1. Zrobic male bezpieczne poprawki czytelnosci: licznik listy, placeholder `Policzono`, podpowiedz sumy profili/akcesoriow, neutralny tekst bilansu pakowania.
2. Po odpowiedziach kolegi zdecydowac o `Cofnij`, trybie stanowiskowym i widocznosci audytu.
3. Dopiero potem projektowac wieksze zmiany UI: role/kiosk, manager queue controls pod tablet, dokument QC, farba, finalne raporty.
4. Przed szersza implementacja uruchomic seeded demo i przejsc po jednym scenariuszu dla kazdej roli: biuro, kierownik, przygotowanie, zawieszanie, produkcja reczna, produkcja automatyczna, pakowanie, Decoral.