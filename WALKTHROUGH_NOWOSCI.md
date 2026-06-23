# Przejście testowe — nowości od 20.06

Krótki, jednorazowy scenariusz do klikania. Każde zlecenie stoi dokładnie tam, gdzie testujesz jedną
funkcję — bez powtarzania ustawień. (To pomocniczy plik testowy, nie dokumentacja.)

## 0. Uruchomienie

```powershell
python scripts/seed_new_features_walkthrough.py   # RESETUJE local.db i ustawia stany
.\scripts\dev.ps1                                  # backend :8000 + frontend :5173
```

- Wejdź na **http://127.0.0.1:5173** i zaloguj się: **`admin` / `adm1`** (ma dostęp do wszystkich ekranów).
- Pliki do wgrania (krok 2) leżą w folderze **`walkthrough_files/`**:
  `rysunek-techniczny.png`, `dokument.pdf`, `zly-plik.txt`.

Mapa zleceń (numery nadane przez system):

| Nr | Co testujesz | Ekran |
|----|--------------|-------|
| 0001 | NA38 — folia na zleceniu Decoral | `/decoral`, szczegóły |
| 0003 | NA36 — rysunek techniczny · NA44 — etykieta + PO TERMINIE | `/produkcja-reczna`, `/biuro` |
| 0004 | NA34 — korekta „od razu poprawiona” (statystyczna) | `/pakowanie` |
| 0005 | NA34 — korekta „do zaplanowania” → NA31 | `/pakowanie` → `/kierownik` |
| 0002 | NA32 — sumaryczne zużycie farby · NA30 (opcjonalnie) | szczegóły zlecenia |

---

## 1. NA35 (scroll) + NA38 (wybór folii przy zleceniu) — utwórz nowe zlecenie

1. `/biuro` → **„Dodaj zlecenie”**.
2. W polach liczbowych (ilość, metraż) **pokręć kółkiem myszy** — wartość zmienia się o **całe jednostki**
   (nigdy 20,3) i tylko gdy pole jest aktywne. → **NA35 OK**.
3. Ustaw **Technologia = Decoral** → pojawia się **lista wyboru folii** (dla RAL jej nie ma). Wybierz folię,
   zapisz. Otwórz szczegóły zlecenia → wybrana folia jest widoczna. → **NA38 (intake) OK**.

## 2. NA36 — rysunki techniczne

**Wgranie (biuro):**
1. Otwórz szczegóły dowolnego zlecenia (np. **0003**) w `/biuro`.
2. W sekcji załączników wybierz **Kategoria = „Rysunek techniczny”**, wgraj `walkthrough_files/rysunek-techniczny.png`
   (obraz!) — przyjęte. Wgraj też `dokument.pdf` jako **„Dokument”**.
3. Spróbuj wgrać `zly-plik.txt` → **odrzucone** (dozwolone tylko PDF/PNG/JPG).

**Podgląd na stacji:**
4. `/produkcja-reczna` → na karcie **0003** jest blok **„Rysunki techniczne”** z linkiem do pobrania
   (działa na każdej stacji, bez logowania do biura). → **NA36 OK**.

## 3. NA38 — rejestr folii

1. Wejdź na **`/folie`** → dodaj nową folię (nazwa + kod + dostawca). Kod musi być unikalny (duplikat odrzucony).
2. Otwórz **0001** (Decoral) — szczegóły oraz karta `/decoral` pokazują wybraną folię „Złoty dąb”. → **NA38 OK**.

## 4. NA44 — precyzyjne etykiety + „PO TERMINIE”

1. `/biuro` — na liście zobacz różne, dokładne etykiety statusu zamiast zbiorczego „W produkcji”:
   **0003 = „Produkcja ręczna”**, **0004/0005 = „Pakowanie”**, **0001 = „Produkcja Decoral”**
   (zlecenia automatyczne pokazują **„Produkcja automat”**).
2. **0003** ma znacznik **„PO TERMINIE”** (planowany odbiór w przeszłości, jeszcze nie Gotowe). → **NA44 OK**.

## 5. NA34 — korekta „od razu poprawiona” (statystyczna)

1. `/pakowanie` → karta **0004** (pakowanie już rozpoczęte, widać formularz).
2. Wpisz liczby tak, by część była do poprawki (np. OK = 18, poprawka = 2), podaj powód.
3. W bloku korekty wybierz **„Od razu poprawiona”** → zatwierdź.
4. Efekt: **0004 kończy się jako Gotowe** (nie wraca do planowania, brak zlecenia-dziecka), a korekta liczy się
   w statystykach (`/kierownik` → raport poprawek / przepustowość). → **NA34 (stat-only) OK**.

## 6. NA34 „do zaplanowania” → NA31 — planowanie na pozycji 1 bez F5

1. `/pakowanie` → karta **0005**. Zatwierdź pakowanie z korektą, ale wybierz **„Do zaplanowania”**.
2. Efekt: zlecenie **wraca do planowania**.
3. Przejdź na **`/kierownik`** — **bez odświeżania (F5)** — zaplanuj 0005 na **pozycji 1**: pole przyjmuje 1,
   pozycja nie jest błędnie „zajęta”. → **NA31 OK**.

## 7. NA32 — sumaryczne zużycie farby (automat, przez rundy korekty)

1. Otwórz szczegóły **0002** (automat, przeszło przez korektę z farbą w obu rundach).
2. **Zużyta farba = 22 kg** (18 z rundy 1 + 4 z rundy 2) — sumarycznie, a nie tylko ostatnia runda.
3. Stan farby (RAL 9006) jest pomniejszony o pełne 22 kg (dostawa 200 → 178). → **NA32 OK**.

## 8. (Opcjonalnie, zaawansowane) NA30 — nie można cofnąć zakończonego zlecenia

0002 jest **Gotowe**. Jego `id` odczytasz z adresu szczegółów (`/zlecenia/{id}`). W
**http://127.0.0.1:8000/docs** (zalogowany jako admin) wywołaj
`POST /process/work-orders/{id}/stages/PRODUCTION/start` dla 0002 → odpowiedź to **kontrolowany błąd**
(nie da się cofnąć ukończonego zlecenia wstecz), zamiast sprzecznego stanu. → **NA30 OK**.

## 9. (Regresja) NA42 — automat bez etapu PRODUKCJA, ręczne bez ZAWIESZANIA

- **0003** (ręczne) **nie pojawia się** na `/zawieszanie` — ręczne nie ma zawieszania.
- **0002** (automat) przeszło przez zawieszanie i farbę z panelu automatu — widok operatora automatu bez zmian.
→ **NA42 OK** (zachowanie jak wcześniej).

---

Po przejściu możesz w każdej chwili wrócić do czystego stanu: ponownie uruchom
`python scripts/seed_new_features_walkthrough.py`.
