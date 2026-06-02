# Definicja Systemu Farby - Draft

Status: `draft po odpowiedziach uzytkownika z 2026-06-02; przed implementacja potrzebne jedno doprecyzowanie semantyczne`

## 1. Co juz wynika z ustalen

Potwierdzone kierunki:

- To, co biuro wpisuje przy tworzeniu zlecenia dla farby, ma oznaczac aktualny stan magazynowy tej farby.
- Gdy farby jest za malo, system ma to wyswietlic, a nie blokowac sam zapis zlecenia.
- Automatyczne poprawki maja dzialac tak samo jak zwykle zlecenia automatyczne w zakresie farby.
- QC, WZ i auth nie wchodza teraz do tego zakresu.
- Pakowanie traktujemy jako zasob wylaczny, ale ten temat nie zmienia definicji farby.

## 2. Co to oznacza dla modelu danych

Obecny kod nie modeluje magazynu farby. Obecny slice zapisuje na zleceniu:

- `paint_code`
- `paint_producer`
- `planned_paint_quantity_kg`
- `consumed_paint_quantity_kg`

W aktualnej implementacji `planned_paint_quantity_kg` nie oznacza stanu magazynowego. Oznacza ilosc przypisana do konkretnego zlecenia i sluzy jednoczesnie jako:

- dane widoczne w UI jako plan dla zlecenia,
- limit backendowy: zuzycie nie moze przekroczyc `planned_paint_quantity_kg`,
- podstawa do wyliczenia `remaining_paint_quantity_kg`.

To jest sprzeczne z nowym kierunkiem, w ktorym wartosc wpisana przez biuro ma oznaczac aktualny stan magazynowy, a nie alokacje dla pojedynczego zlecenia.

Wniosek: nastepny krok implementacyjny nie powinien polegac na samej zmianie opisu pola. Trzeba rozdzielic dwa znaczenia:

- stan magazynowy widziany przez biuro przy wpisywaniu zlecenia,
- zapotrzebowanie / oczekiwane zuzycie / rzeczywiste zuzycie dla konkretnego zlecenia.

## 3. Minimalny model docelowy dla pierwszego magazynowego slice'u

Rekomendowany model semantyczny:

- `paint_code`, `paint_producer`, `ral_code` identyfikuja farbe potrzebna dla zlecenia.
- Biuro zapisuje na zleceniu snapshot: ile tej farby bylo dostepne w magazynie w momencie wpisywania zlecenia.
- System wylicza albo przyjmuje zapotrzebowanie dla zlecenia jako osobna wartosc.
- System wystawia stan logiczny typu `paint_shortage`: czy w chwili wpisania zlecenia farby bylo za malo wzgledem zapotrzebowania.
- Automatyczna produkcja zapisuje faktyczne `consumed_paint_quantity_kg`.
- Automatyczne poprawki podlegaja tej samej logice co zwykle zlecenia automatyczne.
- Pakowanie automatyczne nie powinno sie zamknac bez wpisanego zuzycia farby takze dla poprawek automatycznych.

Istotna konsekwencja:

- Jezeli pole biura oznacza stan magazynowy, to faktyczne zuzycie farby nie powinno byc ograniczane przez ten snapshot jako twardy limit per zlecenie.
- Jesli chcemy miec limit per zlecenie, musi istniec osobna wartosc: zapotrzebowanie lub alokacja dla zlecenia.

## 4. Jedno kluczowe doprecyzowanie przed kodem

Przed implementacja trzeba ustalic, skad bierze sie wartosc zapotrzebowania dla zlecenia.

Na ten moment sa logicznie trzy mozliwe warianty:

1. Automatycznie liczona z powierzchni.
2. Wpisywana recznie przez biuro.
3. Liczona automatycznie jako podpowiedz, ale z mozliwoscia nadpisania.

Wczesniejsza formula robocza byla taka:

- ponizej `70 m2` -> `area_m2 / 4`
- powyzej `70 m2` -> `area_m2 / 6`

Twoja odpowiedz `dana wprowadzona` najpewniej sugeruje, ze zapotrzebowanie nie powinno byc narzucone sama formula i musi istniec wartosc wpisywana recznie. To wymaga potwierdzenia jednym zdaniem przed zmiana modelu i migracji.

Bez tego doprecyzowania nie da sie bezpiecznie zdecydowac, czy w bazie mamy miec:

- tylko snapshot stanu magazynowego,
- snapshot + reczne zapotrzebowanie,
- snapshot + automatyczna sugestie zapotrzebowania.

## 5. O co chodzilo z partia / batch

Tu nie chodzi o obecny snapshot na zleceniu, tylko o przyszly rzeczywisty magazyn farby.

Mozliwe poziomy szczegolowosci:

1. `Partia tylko informacyjna`
   System zapisuje numer partii przy przyjeciu farby, ale nie uzywa go potem do wyszukiwania ani rozliczania.

2. `Partia raportowalna`
   System zapisuje numer partii i pozwala go wyszukiwac albo pokazywac w raportach, ale zuzycie nadal schodzi z lacznego stanu producent + kolor.

3. `Partia rozliczana`
   System pilnuje, z ktorej konkretnej partii zeszla farba, czyli magazyn schodzi po partiach.

Rekomendacja do pierwszego magazynowego slice'u: zaczac od wariantu 1 albo 2, nie od 3.

## 6. Bezpieczna kolejnosc implementacji

Najbezpieczniejszy porzadek prac:

1. Rozdzielic w modelu danych snapshot stanu magazynowego od zapotrzebowania/alokacji dla zlecenia.
2. Dodac backendowy status braku farby i wyswietlac go w UI bez twardej blokady.
3. Ujednolicic logike farby dla zwyklych automatow i automatycznych poprawek.
4. Dopiero potem projektowac osobny magazyn przyjec, korekt i partii.

## 7. Ryzyka, jesli zrobimy to za szybko bez rozdzielenia semantyki

- Backend zacznie traktowac stan magazynowy jak limit dla pojedynczego zlecenia, co da falszywe bledy walidacji.
- UI bedzie pokazywalo `pozostalo` tak, jakby to byla rezerwacja dla zlecenia, mimo ze chodziloby o stan magazynowy.
- Audit przestanie miec jasne znaczenie: nie bedzie wiadomo, czy zapis dotyczy stanu magazynu, planu zlecenia czy realnego zuzycia.
- Korekty automatyczne odziedzicza zle semantycznie dane, jesli najpierw nie ustalimy zrodla zapotrzebowania.

## 8. Testy, ktore beda potrzebne po doprecyzowaniu

- zapis snapshotu stanu magazynowego przy tworzeniu zlecenia,
- wyliczenie lub zapis zapotrzebowania dla zlecenia,
- widoczne ostrzezenie o braku farby bez blokady zapisu,
- ten sam obowiazek wpisania zuzycia dla zwyklych automatow i automatycznych poprawek,
- brak mylnego limitowania zuzycia snapshotem magazynowym,
- czytelne audit eventy rozrozniajace snapshot, zapotrzebowanie i zuzycie.