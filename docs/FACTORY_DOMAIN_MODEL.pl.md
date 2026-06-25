# Model domenowy fabryki — fizyczna prawda bazowa

> **Status: SZKIC, w budowie.** Ten dokument jest budowany sekcja po sekcji na podstawie
> ustrukturyzowanego wywiadu z właścicielem fabryki. Sekcje oznaczone **[TBD — wywiad w toku]** nie są
> jeszcze potwierdzone; nie traktuj ich jako prawdy ani nie implementuj na ich podstawie. Sekcje
> potwierdzone są autorytatywnym opisem tego, jak fizycznie działa fabryka.
>
> **Uwaga:** To jest polskie tłumaczenie dokumentu `FACTORY_DOMAIN_MODEL.md`. Źródłem prawdy pozostaje
> wersja angielska — przy rozbieżności wygrywa oryginał. (Trwałe dokumenty prowadzimy po angielsku.)

## Cel i miejsce w hierarchii dokumentów

Ten dokument opisuje **jak lakiernia fizycznie działa jako proces produkcyjny** — metody produkcji,
powłoki, fizyczną linię, zasoby oraz to, co jest mierzone. Jest to *fizyczna prawda bazowa*, która
leży **pod** dokumentami systemowymi:

1. **`FACTORY_DOMAIN_MODEL.md` (ten dokument)** — fizyczna rzeczywistość fabryki.
2. `WORKFLOW.md` — jak *oprogramowanie* modeluje tę rzeczywistość (stany, ilości, poprawki, macierz
   scenariuszy S01–S12). Gdy WORKFLOW.md wyjaśnia „dlaczego", powinno odsyłać tutaj.
3. Implementacja (serwisy, modele odczytu, frontend) — koduje model.

Gdy model fizyczny jest kiedykolwiek wątpliwy podczas planowania lub kodowania, to jest dokument, do
którego należy zajrzeć i — jeśli rzeczywistość się różni — poprawić go w pierwszej kolejności.

---

## 1. Dwie niezależne osie

Zlecenie jest opisane przez **dwie niezależne właściwości**. To *nie jest* jedna kategoria — to
osobne osie, a zlecenie ma jedną wartość na każdej z nich:

- **Metoda produkcji** — `MANUAL` (ręczna) lub `AUTOMATIC` (automatyczna). *Jak* elementy są
  obrabiane na linii.
- **Typ powłoki** — `RAL` lub `DECORAL`. *Jakie* wykończenie jest nałożone na elementy.

Ponieważ osie są niezależne, każde zlecenie jest dokładnie jedną z **czterech** kombinacji:

| | RAL | DECORAL |
|---|---|---|
| **MANUAL** | zlecenie ręczne, pojedyncza powłoka RAL | zlecenie ręczne, powłoka bazowa RAL + powłoka decoral |
| **AUTOMATIC** | zlecenie automatyczne, pojedyncza powłoka RAL | zlecenie automatyczne, powłoka bazowa RAL + powłoka decoral |

Kluczowe konsekwencje (potwierdzone przez właściciela):

- Pojedyncze zlecenie **może** być jednocześnie automatyczne *i* decoral — obie osie się nie
  wykluczają.
- Zwykłe zlecenie RAL jest **zawsze** albo ręczne, albo automatyczne — metoda produkcji nigdy nie
  jest pusta.
- Dlatego „ręczne", „automatyczne" i „decoral" **nie są trzema wzajemnie wykluczającymi się
  kubełkami**. „Ręczne" i „automatyczne" dzielą oś *metody produkcji*; „RAL" i „decoral" dzielą oś
  *powłoki*. (To jest sedno uzgadniania statystyk — patrz NA23.)

### Oś powłoki w szczegółach

- **RAL** — elementy otrzymują **jedną** powłokę proszkową w określonym kolorze RAL, a następnie
  przechodzą przez linię do pakowania. Jedna powłoka, jedno zdarzenie wykończeniowe.
- **DECORAL** — elementy otrzymują **najpierw tę samą powłokę bazową RAL** (identyczne traktowanie
  jak przy zleceniu RAL), a **następnie nakładana jest jedna dodatkowa powłoka na wierzch**, aby
  uzyskać dekoracyjne wykończenie. Zatem zlecenie decoral to „zlecenie RAL plus jedna dodatkowa
  powłoka". Powłoka bazowa i powłoka decoral pokrywają **te same fizyczne elementy**, więc
  powierzchnia (m²) jest identyczna dla obu — ale są to **dwa odrębne zdarzenia wykończeniowe**
  (inny moment, rejestrowane osobno). Powłoka decoral jest *dodatkowa*, nigdy nie jest ponownym
  pocięciem powłoki bazowej.
  - *Definicja właściciela (autorytatywna):* „powłoka decoral to powłoka RAL, która następnie ma
    nałożoną jeszcze jedną powłokę na wierzch".
  - **Gdzie nakładana jest powłoka decoral (potwierdzone):** na dedykowanej stacji **produkcji
    decoral**, która znajduje się **po** pakowaniu powłoki bazowej. Elementy *nie* są pakowane na tej
    stacji — powłoka decoral jest tam nakładana, a przepływ decoral ma **własną, osobną stację
    pakowania**, która następuje *po* powłoce decoral. Zatem fizyczna sekwencja zlecenia decoral to:
    `… → pakowanie powłoki bazowej → produkcja decoral (nakładanie powłoki) → pakowanie decoral`.
  - **Metoda produkcji przejazdu decoral (potwierdzone):** **dziedziczy** metodę produkcji zlecenia —
    przejazd decoral nie jest osobno wybierany jako ręczny/automatyczny.
  - **Natura/cel drugiej powłoki:** **[TBD — odłożone]** — celowo odroczone; do wyjaśnienia z
    kompetentnym współpracownikiem. Niepotrzebne dla bieżącej pracy nad modelowaniem/statystykami.

  > **Decyzja modelowa (potwierdzona przez właściciela 2026-06-17):** fizycznie istnieje osobna stacja
  > pakowania decoral po powłoce decoral, ale **system celowo nie śledzi jej jako osobnego etapu**.
  > Obecny model — pojedynczy końcowy etap `DECORAL_PRODUCTION` po `PACKING`, bez osobnego etapu
  > pakowania decoral — jest zaakceptowany w tej postaci. **Nie** dodawaj etapu/zakładki pakowania
  > decoral.

### Oś produkcji w szczegółach (potwierdzone)

Ręczna i automatyczna to **dwie osobne fizyczne linie**, które mogą działać **równolegle** (w tym
samym czasie). Różnią się sposobem nakładania farby:

- **AUTOMATIC** — elementy są **wieszane na suwnicach/przenośnikach** („suwnice"), wjeżdżają do
  **kabiny natryskowej, która maluje je automatycznie**, a następnie idą do pakowania. Etap
  wieszania istnieje **tylko** dla automatu (to etap `HANGING` / wyłączny zasób linii
  automatycznej).
- **MANUAL** — **lakiernik maluje elementy ręcznie** (w kabinie), a następnie idą do pakowania.
  Dla zleceń ręcznych **nie ma etapu wieszania**.

**Zasoby współdzielone vs. osobne:**

- **Współdzielone przez obie metody:** przygotowanie powierzchni (etap wejściowy) i **pakowanie** —
  obie linie wpadają do tego samego współdzielonego pakowania.
- **Osobne na metodę:** linia automatyczna (wieszanie + automatyczna kabina natryskowa) vs. ręczna
  kabina lakiernicza. Ponieważ linie są osobne, zlecenie ręczne i zlecenie automatyczne mogą być w
  produkcji jednocześnie.

**Liczność i dominacja (potwierdzone przez właściciela 2026-06-23):**

- Istnieje **dokładnie jedno stanowisko malowania ręcznego i dokładnie jedna automatyczna kabina
  natryskowa** — więc są **dwa równoległe zasoby malowania, po jednym na metodę**. Dlatego model
  planowania ma dokładnie dwie sekwencje linii (Automat / Ręczna): odzwierciedla to dwie fizyczne
  maszyny, a nie wybór stylistyczny.
- **Linia automatyczna przenosi zdecydowaną większość** przepustowości, kosztów i zysku fabryki.
  **Koszt zmiany koloru jest najwyższy na kabinie automatycznej**, więc sekwencja automatyczna jest
  głównym elementem wartym optymalizacji (grupowanie kolorów ma tam największe znaczenie).

### Utwardzanie / wypalanie (poza zakresem systemu — potwierdzone)

Elementy są utwardzane w piecu, fizycznie umiejscowionym mniej więcej przy obszarze pakowania.
**System nie śledzi procesu wypalania** — jest poza zakresem i nie powinien być modelowany jako etap.

---

## 2. Fizyczna linia

Fizyczna ścieżka elementu zależy od obu osi. Kroki oznaczone **(współdzielone)** to ten sam fizyczny
zasób dla ręcznej i automatycznej; krok malowania to miejsce, gdzie obie metody się rozchodzą.

```
                         ┌─────────────────────────────────────┐
                         │  Przygotowanie powierzchni (wspólne) │
                         └──────────────────┬──────────────────┘
                                            │
                  ┌─────────────────────────┴─────────────────────────┐
                  │                                                     │
          metoda AUTOMATYCZNA                                   metoda RĘCZNA
                  │                                                     │
   ┌──────────────▼───────────────┐                     ┌───────────────▼──────────────┐
   │ Wieszanie na suwnicach/przen. │                     │  Lakiernik maluje ręcznie     │
   │ → automatyczna kabina natr.   │   (osobne linie,    │  (brak etapu wieszania)       │
   │ (HANGING + linia automat.)    │    działają równol.)│                               │
   └──────────────┬───────────────┘                     └───────────────┬──────────────┘
                  │                                                     │
                  └─────────────────────────┬─────────────────────────┘
                                            │
                          ┌─────────────────▼─────────────────┐
                          │       Pakowanie (współdzielone)   │
                          └─────────────────┬─────────────────┘
                                            │
                   ┌────────────────────────┴────────────────────────┐
                   │                                                  │
              powłoka RAL                                       powłoka DECORAL
                   │                                                  │
            ┌──────▼──────┐                          ┌────────────────▼────────────────┐
            │  Wydane      │                         │  Produkcja decoral (2. powłoka)  │
            │  (gotowe)    │                         │  → własne pakowanie decoral      │
            └─────────────┘                          │    → wydane                       │
                                                      └──────────────────────────────────┘
```

Uwagi:

- **Przygotowanie powierzchni** i **pakowanie** są współdzielone przez obie metody produkcji.
  Przygotowanie powierzchni to **mycie/przygotowanie czyszczące** przed malowaniem — proces
  wieloetapowy z myciem, etapem kwasowym i kilkoma płukaniami; dokładna chemia **nie jest śledzona
  przez system** i ma niski priorytet do udokumentowania (właściciel, 2026-06-17). To także miejsce,
  gdzie **liczona jest rzeczywista przyjęta ilość** (patrz §3). Przygotowanie powierzchni to
  **podajnik sterowany planem** (nie napędzany fizycznym przybyciem elementów) i **wyprzedza
  malowanie** — nie jest wąskim gardłem (właściciel, 2026-06-23). Historycznie kolejność wynikała z
  drukowanego arkusza planowania kierownika.
  Ponieważ te dwa etapy są **pojedynczymi współdzielonymi zasobami** zasilającymi/opróżniającymi
  dwie równoległe linie malowania, ich kolejność **nie jest** pozycją w kolejce malowania danej linii
  (ten numer ma znaczenie tylko w obrębie jednej linii). Jest **wyprowadzana** (N49-10): przygotowanie
  powierzchni przeplata obie linie, zasilając w następnej kolejności linię z **mniejszym buforem
  przygotowanych-ale-jeszcze-niepomalowanych** (linia najbliżej zagłodzenia swojej kabiny; remisy →
  automat), bufor mierzony w **sztukach**; pakowanie podąża za **fizyczną gotowością** + rezerwacją
  slotu pakowania, **bez numerowania pozycji**. Patrz model harmonogramowania w `WORKFLOW.md` →
  „Target planning model" oraz pozycja NA49 w `IMMEDIATE_NEXT_ACTIONS.md`.
- Ścieżka **automatyczna** dodaje **wieszanie** (suwnice/przenośniki) przed automatyczną kabiną
  natryskową; ścieżka **ręczna** ma lakiernika nakładającego farbę ręcznie, bez wieszania.
- Dwie linie produkcyjne są fizycznie osobne i działają **równolegle**.
- Dla **RAL** element jest gotowy po pakowaniu. Dla **DECORAL** element kontynuuje do stacji
  **produkcji decoral** na drugą powłokę, a następnie przez **osobne pakowanie decoral** (patrz
  uwaga o rozbieżności model/rzeczywistość w §1).
- **Utwardzanie w piecu** odbywa się fizycznie (w okolicy obszaru pakowania), ale **nie jest
  śledzone** przez system (patrz §1).

---

## 3. Ilości, sztuki i poprawki (fizycznie)

- **Jednostka:** zlecenie obejmuje pewną ilość fizycznych **sztuk/elementów** oraz całkowitą
  **powierzchnię w m²** (`total_area_m2`). m² jest metryką podstawową (patrz §4).
- **Tylko część wolna od poprawek to gotowy wyrób.** Przy odpowiednim pakowaniu wszelkie sztuki,
  które nie przejdą i wymagają poprawki, są wydzielane jako **poprawka**; tylko część bez poprawek
  liczy się jako wyprodukowana/gotowa (RAL przy pakowaniu, decoral przy pakowaniu decoral — patrz §4).
- **Modelowanie poprawek w systemie** (RAL = reset tego samego zlecenia z batchem `CORRECTION`;
  DECORAL = wydzielenie zlecenia potomnego „P"; ilość jest zachowana w łańcuchu) jest szczegółowo
  opisane w `WORKFLOW.md` („Corrections Behavior", macierz scenariuszy S01–S12). Ten dokument tego
  nie powtarza.
- **Rzeczywista policzona ilość to prawda operacyjna.** Przygotowanie powierzchni liczy **faktycznie
  przyjęte** sztuki, które mogą różnić się od ilości zamówionej (patrz *niekompletne na przyjęciu*
  poniżej). Od tego momentu **rzeczywista policzona ilość — nie ilość zamówiona — jest tym, względem
  czego walidują stacje niżej i pakowanie** (pakowanie sprawdza „czy coś zginęło?" względem
  rzeczywistego licznika i to działa). ⚠️ **Znana luka UI (właściciel, 2026-06-17):** większość
  ekranów wciąż *wyświetla* ilość zamówioną zamiast rzeczywiście policzonej — zalogowane jako **NA26**
  do weryfikacji/naprawy w NA25.
- **Niekompletne na przyjęciu.** Zlecenie jest *niekompletne na przyjęciu*, gdy **fizycznie przybywa
  mniej elementów niż zamówiono**. Takie zlecenie **wciąż może iść do produkcji** — nie jest
  blokowane — a licznik z przygotowania powierzchni staje się ilością operacyjną. Znacznik jest stanem
  biura i nie zmienia przepływu produkcji.
- **Szczegóły fizycznych poprawek** (gdzie fizycznie trafia wadliwa sztuka, czy jest
  zdejmowana/przemalowywana, poprawki specyficzne dla decoral): **[TBD — wywiad w toku]**, niski
  priorytet — zachowanie systemu jest już opisane w `WORKFLOW.md`.

---

## 4. Pomiar — co jest liczone, gdzie i kiedy

**Metryka podstawowa: metry kwadratowe (m²).** m² to to, na czym fabryce zależy najbardziej.
**Sztuki** są metryką drugorzędną i również powinny być policzalne, ale m² prowadzi.

**Kiedy zlecenie liczy się jako wyprodukowane (potwierdzone):**

- **RAL** — gotowe przy **pakowaniu**, pod warunkiem że przy pakowaniu nie wyszły żadne poprawki.
- **DECORAL** — gotowe przy **pakowaniu decoral** (po przejeździe produkcji decoral), pod warunkiem
  że nie wyszły tam żadne poprawki.

W obu przypadkach praca jest liczona przy **końcowym pakowaniu dla danej powłoki**, a tylko część
**bez poprawek** liczy się jako gotowy wyrób.

### 4.1 Jak decoral liczy się do produkcji całkowitej (rozstrzygnięcie NA23)

**Zlecenie decoral to JEDEN wyrób, liczony RAZ.** Fabryka mierzy „ile m² faktycznie przeszło przez
fabrykę", a elementy zlecenia decoral to pojedynczy fizyczny wyrób — powłoka decoral to *etap w
środku*, **nie** druga jednostka wyjścia. Zatem zlecenie decoral o 10 m² wnosi **10 m²** do produkcji
całkowitej, **a nie 20**.

Jest to **zgodne z tym, jak przepustowość jest już obliczana** (`m2_total` sumuje `total_area_m2`
każdego zlecenia dokładnie raz, a przejazd decoral to osobna seria, która *nie* jest dodawana do
sumy). Uwidacznia to także coś, czego system jeszcze nie eksponował — czysty **podział wg powłoki**
sumy:

- **Produkcja całkowita** = m² (lub sztuki) każdego zlecenia, liczone **raz** („ile wyrobu przeszło
  przez fabrykę").
- Dzieli się czysto wzdłuż **dowolnej** osi, a **oba podziały sumują się do tej samej sumy**:
  - **Wg metody produkcji:** `ręczna + automatyczna = suma` (każde zlecenie ma dokładnie jedną
    metodę).
  - **Wg typu powłoki zlecenia:** `tylko-RAL + decoral = suma`. ⚠️ Kubełek „RAL" oznacza tu
    **zlecenia, których typ powłoki to wyłącznie RAL** (bez decoral) — *nie* „wszystko, co dostało
    powłokę RAL". Zlecenie decoral fizycznie dostaje też powłokę bazową RAL, ale jako **wyrób** jest
    sklasyfikowane jako `DECORAL` i liczone **raz, po stronie decoral**. Oznaczaj ten kubełek
    „czysty RAL / RAL only", nigdy samo „RAL", bo czyta się jako „wszystkie powłoki RAL" i podział
    przestaje się sumować (ten dokładny błąd etykiety wywołał realne zamieszanie — właściciel,
    2026-06-17).
- Dlatego podział wg metody i podział wg powłoki to **dwa niezależne sposoby cięcia tej samej
  całości**, a nie jeden trójdzielny kubełek. **„Ręczna + automatyczna + decoral" NIE jest poprawną
  sumą** — ręczna + automatyczna już równa się całości; decoral żyje na drugiej osi, więc dodanie go
  podwójnie liczy każde zlecenie decoral. (To było pierwotne sformułowanie właściciela; zostało
  wycofane, gdy przepracowaliśmy przykład liczbowy.)
- **Liczenie *nałożonych powłok* to inne pytanie**, które celowo **nie** sumuje się do produkcji
  całkowitej: każde zlecenie dostaje powłokę RAL (wł. bazę zleceń decoral), a zlecenia decoral
  dostają dodatkową powłokę decoral, więc „powłoki RAL + powłoki decoral" > produkcja całkowita. To
  obciążenie linii/powłok (patrz licznik „przejazd decoral" poniżej), a nie przepustowość.

**Dwa różne znaczenia „m² decoral" — nie mylić:**

1. **Decoral jako wyrób/powłoka (liczy się do sumy, raz):** zlecenia, których powłoka to `DECORAL`,
   mierzone raz jak każdy wyrób. To plasterek, który sprawia, że `RAL + decoral = suma`.
2. **Przejazd decoral (obciążenie, NIE część sumy):** m² przetworzone przez *samą linię decoral* przy
   nakładaniu drugiej powłoki (rejestrowane przy zakończeniu `DECORAL_PRODUCTION`). To mierzy, jak
   zajęta była linia decoral; **nakłada się** na powłokę bazową (te same elementy) i **nigdy** nie
   może być dodane do produkcji całkowitej. Istniejący wykres „Przejazd Decoral — m² / dzień" to to
   drugie znaczenie.

> **Implikacja projektowa dla NA23:** zaoferuj widok szczegółowy jako dwa niezależne podziały sumy
> (wg metody produkcji oraz wg powłoki), gdzie części każdego podziału widocznie sumują się do
> całości. Zachowaj „przejazd decoral" jako osobny licznik, wyraźnie oznaczony jako obciążenie linii,
> a nie część sumy. Potwierdź prezentację z użytkownikiem przed budową.

---

## 5. Dodatkowe typy zleceń i znaczniki

### Ocynk (galwanizacja)

Fabryka galwanizuje elementy (cynkowa warstwa antykorozyjna). **Z perspektywy systemu zlecenie
`is_ocynk` musi zachowywać się dokładnie jak zwykłe zlecenie** — te same etapy, ten sam routing,
swobodnie łączone z RAL/decoral i ręczne/automatyczne. Jedynym wymogiem jest **wyraźne oznaczenie
zlecenia jako OCYNK**, by stacje je widziały; fizyczna praca stacji się różni, ale przepływ
*systemowy* nie. `is_ocynk` jest niezależnym znacznikiem i nie zmienia routingu (właściciel,
2026-06-17).

### Przemalowanka

*Przemalowanka* to zlecenie **przemalowania elementów, które już mają powłokę** (zmiana koloru /
odświeżenie istniejących elementów). Zachowanie systemu: zawsze jest **samodzielnym zleceniem
klienta** (nigdy potomną poprawką — modelowane jako `work_order_kind = PRZEMALOWANKA`) i **pomija
`SURFACE_PREPARATION`**. Poza pominięciem przygotowania powierzchni zachowuje się jak zwykłe
zlecenie. *Dlaczego* pomija przygotowanie powierzchni potwierdzono z kompetentnym procesowo
współpracownikiem, ale fizyczny powód jest **[TBD — nieuchwycony]**.

---

## 6. Słownik

Krótkie kanoniczne definicje. Dla semantyki *systemowej* (stany, walidacja, READY, poprawki)
autorytetem pozostaje `WORKFLOW.md`; ten słownik podaje proste znaczenie i wiąże pojęcie z jego
miejscem.

| Termin (PL) | Znaczenie |
|---|---|
| **Element / sztuka** | Fizyczny element obrabiany w fabryce. Liczony w sztukach. Nie to samo co zlecenie. |
| **Zlecenie (work order)** | Rekord systemowy śledzący zamówioną pracę jednego klienta. Ma metodę produkcji i typ powłoki (§1). |
| **Profil / Akcesorium** | Dwie kategorie sztuk dzielące `total_quantity` zlecenia (`profile + akcesoria = suma`, gdy obie znane). Patrz `WORKFLOW.md`. |
| **Metoda produkcji** | `MANUAL` (lakiernik maluje ręcznie) lub `AUTOMATIC` (zawieszone na suwnicach → automatyczna kabina natryskowa). Jedna z dwóch osi (§1). |
| **Powłoka / Coating** | `RAL` (jedna powłoka proszkowa w kolorze RAL) lub `DECORAL`. Druga oś (§1). |
| **RAL** | Pojedyncza powłoka proszkowa w określonym kolorze RAL; zlecenie kończy się przy pakowaniu. |
| **Decoral** | Powłoka bazowa RAL **plus jedna dodatkowa powłoka dekoracyjna** nakładana na osobnej stacji Decoral po pakowaniu powłoki bazowej (§1). |
| **Przejazd Decoral** | Zdarzenie robocze nakładania powłoki decoral. Licznik **obciążenia linii** (nakłada się na powłokę bazową); nigdy nie część przepustowości całkowitej (§4.1). |
| **Ocynk** | Znacznik galwanizacji (`is_ocynk`). Neutralny systemowo: zachowuje się jak zwykłe zlecenie, tylko oflagowane (§5). |
| **Przemalowanka** | Przemalowanie już powlekanych elementów; samodzielne zlecenie pomijające przygotowanie powierzchni (§5). |
| **Przygotowanie powierzchni** | Mycie czyszczące/przygotowawcze przed malowaniem; także miejsce liczenia rzeczywiście przyjętej ilości (§2, §3). |
| **Poprawka (correction)** | Sztuki, które nie przejdą QC przy pakowaniu i są poprawiane. RAL → batch `CORRECTION` w miejscu; DECORAL → zlecenie potomne „P". Patrz `WORKFLOW.md`. |
| **Niekompletne na przyjęciu** | Przybyło mniej elementów niż zamówiono; zlecenie może wciąż iść do produkcji (§3). |
| **Ilość zamówiona / declared (`total_quantity`)** | To, co klient zamówił. |
| **Ilość policzona / actual received** | Rzeczywiste sztuki policzone przy przygotowaniu powierzchni — **prawda operacyjna** niżej (§3). |
| **READY** | Zlecenie jest w pełni ukończone (dokładna reguła: `WORKFLOW.md` „READY Rules"). |
| **`process_status`** | Status wyświetlany wyprowadzany przez backend; nigdy nie jest kolumną przechowywaną (patrz `WORKFLOW.md` / `CLAUDE.md`). |

---

## 7. Prawda bazowa planowania — norma dzienna, przepustowość, zmiana koloru i wybór linii

> Potwierdzone przez właściciela + kompetentnego procesowo współpracownika w wywiadzie procesowym
> „od zera" (2026-06-23). To fizyczne ugruntowanie modelu planowania w `docs/WORKFLOW.md` („Target
> planning model") oraz planu budowy w `IMMEDIATE_NEXT_ACTIONS.md` (NA49). Pozycje wciąż czekające na
> współpracownika są oflagowane.

### Norma dzienna to PODŁOGA, nie sufit

Fabryka jest rentowna tylko **powyżej minimalnej dziennej przepustowości** (prąd, płace, materiały
się zwracają). Norma to to minimum, a nie cel, na którym należy się zatrzymać:

- **≥ 800 m²** w długim dniu (zmiana 07:00–21:00, ~14 h).
- **≥ 500 m²** w krótkim dniu (zmiana 07:00–15:00, ~8 h).

To **podłogi do przekroczenia**, nie przepustowość. Fizyczny **sufit** jest wyższy: automatyczna
kabina pracuje z **~60–100 m²/h**, więc długi dzień może fizycznie sięgnąć ~1000–1400 m². Dzień jest
*zły*, gdy spada **poniżej** podłogi (za mało wyrobu), a nie gdy jest zajęty. Cel optymalizacji =
przekraczać podłogę każdego dnia roboczego i pakować **w kierunku sufitu** (więcej wyrobu = więcej
zysku), w kolejności terminów, z minimalną stratą na zmianach koloru. **Długość zmiany podąża za
dostępną pracą**: dość gotowej pracy, by przekroczyć ≥ 800 → uruchom długi dzień; tylko ~500 →
uruchom krótki dzień (długi dzień bezczynnie poniżej 800 = nierentownie).

### Automatyczna kabina jest ograniczeniem; ręczna to niemierzony nadmiar

- Automat przenosi zdecydowaną większość przepustowości; **~60–100 m²/h**, mierzalne.
- **Przepustowość linii ręcznej i ręczne zużycie farby są w praktyce niemierzalne** — ręczna to
  rozmyty **zawór nadmiarowy**, nie planowany ani nie opomiarowany precyzyjnie.
- Przygotowanie powierzchni jest *nieco* wolniejsze niż malowanie, ale **zwykle nadąża**, więc kabina
  rzadko na nie czeka (istnieje bufor oczyszczonych elementów; jego rozmiar **nie jest istotny**).
  Przygotowanie to podajnik sterowany planem, **nie wąskie gardło** — nie przemodelowuj go. Główny
  wyjątek to przypadek niespodzianki z farbą poniżej.

### Ekonomia zmiany koloru (główne pokrętło optymalizacji)

Zmiana koloru na automatycznej kabinie kosztuje czas, skalowany **progiem 100 m²** (ta sama liczba
co próg zapotrzebowania na farbę):

- następne zlecenie **< 100 m²** → „bez odzysku" → zmiana **≤ 15 min**.
- następne zlecenie **> 100 m²** → „z odzysku" (farba odzyskana, pełniejsze czyszczenie) → zmiana
  **do 30 min**.

Koszt zależy także od **kierunku/podobieństwa koloru**: przejście z **jaśniejszego** koloru na
**ciemniejszy** jest tanie (resztki jaśniejszego koloru są niewidoczne w ciemniejszym — przykład
właściciela: biały → szary), podczas gdy **ciemny → jasny** wymaga pełnego czyszczenia (resztki byłyby
widoczne). Zatem tani kształt dnia to pojedynczy **przejazd jasny → ciemny**; reset ciemny → jasny to
kosztowne zdarzenie do minimalizacji. Grupowanie identycznych kolorów w serie (zerowa zmiana) to
pierwsza dźwignia; uporządkowanie pozostałych zmian jasny → ciemny to druga. **Jasność koloru jest
wyprowadzalna z kodu RAL**, więc system może to obliczyć. Dokładne minuty/częstotliwość nie są
śledzone przez ludzi — system powinien je **uczyć się z danych produkcyjnych** (patrz §4) — ale
nagroda za grupowanie jest duża. **Pasma 15/30 min są potwierdzone**; *częstotliwość* zmian koloru
**nie jest stałą liczbą** — zależy od miksu zleceń dnia, więc system się jej uczy. Model jasności RAL
jasny→ciemny to robocze założenie (przykład właściciela biały→szary); właściciel nie potrafił
potwierdzić, czy „rodziny" kolorów go nadpisują — ⚠️ *wciąż do potwierdzenia ze współpracownikiem.*
**Zbudowane (N49-5/6):** wewnątrzdniowy przejazd + koszt zmiany rozmiar+kierunek są zaimplementowane;
RAL→jasność żyje w **jednym udokumentowanym helperze** `app/manager/colour.py::ral_lightness` (zgrubna
mapa grup/kotwic, NIE percepcyjna skala L\*) — ten helper to **jedyny punkt do rewizji**, gdy to
otwarte pytanie zostanie rozstrzygnięte (mapowanie CIE-Lab/HLC lub tabela rodzin zastąpiłyby go tam, i
nigdzie indziej).

### Wybór linii (ręczna vs automatyczna) to realna dźwignia planowania

Każde zlecenie *może* działać na dowolnej linii; element tego nie wymusza. Zasada kciuka
(właściciel): zlecenie idzie na **ręczną**, gdy jest **małe w m² ORAZ jego kolor nigdzie indziej się
nie powtarza** na liście zleceń (brak grupy do dołączenia); w przeciwnym razie idzie na **automat**,
by mogło dołączyć do serii koloru. Wybór linii zatem oddziałuje z grupowaniem kolorów i z
równoważeniem obciążenia bezczynnych stacji.

### Decoral nie jest drugim wąskim gardłem

Druga powłoka decoral jest czysto **estetyczna** („żeby ładniej wyglądało"); **zmiana folii nie
kosztuje czasu**, a stacja decoral nie zapycha linii. Decoral to ~1/4 zleceń. To końcowy doklejony
etap, **nie** coś, co harmonogramujący musi osobno optymalizować.

### Terminy są TWARDE

**Planowana data odbioru każdego zlecenia („Termin odbioru", `planned_pickup_date`) to twardy
termin** — jest **zawsze uzgadniany i wprowadzany przy tworzeniu zlecenia**, a zlecenie musi być
wysłane do tego czasu. Hierarchia twardości dla planowania: **twardy termin > dzienna podłoga (silny
cel ekonomiczny) > grupowanie kolorów (optymalizacja).** Mały dzień niosący twardy termin działa
nawet poniżej podłogi (musi wysłać), jako jawny wyjątek. **Horyzont terminów jest komfortowy — „na
pewno nie na jutro"** (właściciel, 2026-06-23), więc planujący ma **realną swobodę przestawiania pod
grupowanie kolorów** w ramach ograniczenia twardego terminu; ciasny termin to wyjątek, nie reguła.
(Dokładny typowy zapas wciąż warto potwierdzić ze współpracownikiem.)

**Horyzont planowania jest ograniczony do 3 dni roboczych** (właściciel, 2026-06-24): kierownik **nie
może planować więcej niż 3 dni robocze do przodu** — dziś plus kolejne dwa dni robocze. Elementy
dalej nie są jeszcze wystarczająco pewne, by harmonogramować względem nich, więc rolująca tablica i
wielodniowe rozmieszczanie nigdy nie patrzą poza to okno (egzekwowane w
`GET /manager/planner/multi-day`, domyślnie i maksymalnie `horizon_working_days = 3`).

### Dostępne sygnały pomiarowe (brak pomiaru w kabinie)

Operatorzy **nie** podpinają się do samej kabiny. Linia automatyczna emituje, na zlecenie, **start
HANGING** (tapnięte — wieszanie zajmuje zasób linii) oraz **zakończenie PACKING**, oba w
append-only logu `StageTransitionEvent`. Te **obejmują cały przejazd automatyczny** (wieszanie +
kabina + piec + pakowanie). Zatem zagregowana przepustowość (m²/h) i — statystycznie, na wielu
zleceniach — koszt zmiany koloru są **uczalne z istniejących sygnałów**; czysty czas kabiny nie jest
izolowany i to jest zaakceptowane.
