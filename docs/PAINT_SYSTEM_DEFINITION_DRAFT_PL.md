# Definicja Systemu Farby - Draft

Status: `zalozenia potwierdzone 2026-06-02; pierwszy slice to magazyn farb + snapshot historyczny na zleceniu`

## 1. Co juz wynika z ustalen

Potwierdzone kierunki:

- Magazyn farb w tej aplikacji jest zrodlem prawdy dla aktualnego stanu farb.
- Biuro przy tworzeniu zlecenia wybiera farbe i widzi aktualny stan, ale samo utworzenie zlecenia nie robi rezerwacji.
- Ostrzezenie o brakach farby przy przyjeciu JEST wdrozone (aktualizacja 2026-06-17): read model liczy przewidywane zapotrzebowanie (`total_area_m2 / 4` ponizej 100 m², `/6` od 100 m²) i ostrzega, gdy przekracza biezacy stan (`paint_inventory_insufficient_for_prediction`). Poza pierwszym slice'em pozostaje dopiero alert oparty na rezerwacji/demandzie wzgledem wspolnego magazynu. (Pierwotne zalozenie "alert nie wchodzi do slice'u" jest nieaktualne.)
- Automatyczne poprawki maja dzialac tak samo jak zwykle zlecenia automatyczne w zakresie zuzycia farby.
- Tylko automat zapisuje zuzycie farby.
- Stan magazynowy nie moze zejsc ponizej zera.
- Historia zlecenia ma zostac historyczna i nie moze sie zmieniac po pozniejszej edycji kartoteki farby.
- QC, WZ i auth nie wchodza teraz do tego zakresu.
- Pakowanie traktujemy jako zasob wylaczny, ale ten temat nie zmienia definicji farby.

## 2. Co to oznacza dla modelu danych

Docelowy pierwszy slice modeluje dwa rozne byty:

1. biezacy magazyn farb,
2. historyczny snapshot farby zapisany na zleceniu.

Na zleceniu pozostaja:

- `paint_code`
- `paint_producer`
- `ral_code`
- `paint_stock_snapshot_quantity_kg`
- `consumed_paint_quantity_kg`

W aktualnej definicji znaczenia sa nastepujace:

- `paint_stock_snapshot_quantity_kg` to historyczny snapshot stanu magazynowego widziany przez biuro podczas wpisywania zlecenia,
- `consumed_paint_quantity_kg` to faktyczne zuzycie wpisane przez automat,
- biezacy stan magazynowy nie jest liczony ze snapshotow na zleceniach, tylko z ruchow magazynowych.

## 3. Minimalny model docelowy dla pierwszego magazynowego slice'u

Potwierdzony model semantyczny:

- `paint_code`, `paint_producer`, `ral_code` identyfikuja farbe potrzebna dla zlecenia.
- System przechowuje kartoteke farby i biezacy stan magazynowy dla tej farby.
- Biuro zapisuje na zleceniu snapshot: ile tej farby bylo dostepne w magazynie w momencie wpisywania zlecenia.
- Automatyczna produkcja zapisuje faktyczne `consumed_paint_quantity_kg`.
- Zapis zuzycia automatycznie zmniejsza biezacy stan magazynowy tej farby.
- Dostawa automatycznie zwieksza biezacy stan magazynowy tej farby.
- Reczna korekta magazynowa moze zwiekszac albo zmniejszac biezacy stan, ale musi byc auditowalna.
- Automatyczne poprawki podlegaja tej samej logice co zwykle zlecenia automatyczne.
- Pakowanie automatyczne nie powinno sie zamknac bez wpisanego zuzycia farby takze dla poprawek automatycznych.
- Utworzenie zlecenia nie robi rezerwacji stanu magazynowego.
- System nie pozwala zapisac ruchu, ktory spowodowalby stan ujemny.

Istotna konsekwencja:

- Snapshot stanu magazynowego na zleceniu nie jest live stockiem po czasie; to sladowa wartosc historyczna.
- Live stock jest liczony z kartoteki i ruchow magazynowych.
- Zuzycie jest traktowane jako jednorazowy zapis produkcyjny, bez pozniejszej edycji przez operatora.
- Bledy po zapisie sa naprawiane korekta magazynowa, nie przepisywaniem historii zlecenia.

## 4. Aktualny proces aktualizacji stanu

Potwierdzony obieg pracy:

- Biuro utrzymuje stan farb bezposrednio w tej aplikacji.
- Przy dostawie biuro dopisuje ilosc przyjetej farby do stanu magazynowego.
- Przy korekcie biuro recznie koryguje stan magazynowy z notatka.
- Przy tworzeniu zlecenia biuro wskazuje farbe, a system pokazuje aktualny stan i zapisuje jego snapshot na zleceniu.
- Automat wpisuje faktyczne zuzycie farby na zleceniu.
- Zapis zuzycia automatycznie zmniejsza stan magazynowy.

Wniosek: pierwszy magazynowy slice to aplikacyjny magazyn agregowany per farba plus historyczny snapshot na zleceniu.

## 5. O co chodzilo z partia / batch

Tu nie chodzi o obecny snapshot na zleceniu, tylko o przyszly rzeczywisty magazyn farby.

Mozliwe poziomy szczegolowosci:

1. `Partia tylko informacyjna`
   System zapisuje numer partii przy przyjeciu farby, ale nie uzywa go potem do wyszukiwania ani rozliczania.

2. `Partia raportowalna`
   System zapisuje numer partii i pozwala go wyszukiwac albo pokazywac w raportach, ale zuzycie nadal schodzi z lacznego stanu producent + kolor.

3. `Partia rozliczana`
   System pilnuje, z ktorej konkretnej partii zeszla farba, czyli magazyn schodzi po partiach.

Rekomendacja do pierwszego magazynowego slice'u: nie modelowac partii w ogole. Trzymac tylko laczny stan dla farby.

## 6. Bezpieczna kolejnosc dalszej implementacji

Najbezpieczniejszy porzadek prac:

1. Wprowadzic kartoteke farb i biezacy stan magazynowy per farba.
2. Wprowadzic ruchy magazynowe: dostawa, zuzycie automatyczne, korekta reczna.
3. Podpiac snapshot historyczny pod tworzenie zlecenia bez rezerwacji.
4. Dopiero potem decydowac, czy aplikacja ma kiedys wejsc w partie i bardziej zlozone rozliczanie.

## 7. Ryzyka, jesli rozrosniemy to bez decyzji o zakresie

- Gdyby snapshot stanu byl traktowany jak live stock, UI zacznie sugerowac aktualnosc, ktorej ten snapshot nie ma.
- Gdyby system zbyt szybko wrocil do dodatkowego pola zapotrzebowania bez jasnej decyzji biznesowej, znow wymiesza semantyke informacyjna i magazynowa.
- Gdyby zapis zuzycia z automatu mogl byc wielokrotnie nadpisywany bez twardych zasad, magazyn zacznie gubic integralnosc stanu.

## 8. Testy potrzebne i juz czesciowo wdrozone

- zapis dostawy zwieksza stan magazynowy,
- zapis recznej korekty aktualizuje stan i zachowuje powod/notatke,
- zapis snapshotu stanu magazynowego przy tworzeniu zlecenia,
- ten sam obowiazek wpisania zuzycia dla zwyklych automatow i automatycznych poprawek,
- blokada zejscia ponizej zera,
- brak rezerwacji przy tworzeniu zlecenia,
- czytelne audit eventy rozrozniajace dostawe, korekte, snapshot i zuzycie.