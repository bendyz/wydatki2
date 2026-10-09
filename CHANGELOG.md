# Zmiany

Notatki wydaniowe prowadzone od wersji 0.11.0. Opisują zmiany widoczne dla
użytkownika — szczegóły techniczne są w historii gita.

## 0.14.0 — 2026-10-09

### Roczny warunek karty

W oknie karty (Karty → edycja) jest nowa sekcja **Warunek roczny**: minimalna
kwota w roku i data wydania karty. Rok liczy się od rocznicy wydania (bez daty
— rok kalendarzowy), a nad tabelą miesięczną pojawia się pasek postępu, np.
„7 340 / 10 000 zł (73%) — brakuje 2 660 zł". Kliknięcie paska pokazuje wszystkie
wydatki z karty w tym okresie. Warunek roczny jest niezależny od miesięcznych.

### Dla aplikacji Android

Nowe opcjonalne pola karty `yearly_min_amount` i `issued_date`, blok `year`
w `GET /cards/stats`, a `GET /cards/{id}/expenses` przyjmuje alternatywnie
`date_from` i `date_to`. Starsze wersje apki działają bez zmian.

## 0.13.1 — 2026-10-09

- „Nazwa aplikacji" z ustawień administratora widnieje teraz w tytule karty
  przeglądarki i w pasku bocznym (wcześniej służyła tylko w nagłówku zapytań do
  OpenRouter i w dokumentacji API).

## 0.13.0 — 2026-10-08

### Kredyty w module Majątek

Przy dodawaniu konta jest nowy typ **Kredyt** (np. hipoteka). Wpisujesz w nim
saldo pozostałe do spłaty — kwotą dodatnią, tak jak widzisz ją w banku — i
dodajesz kolejne wpisy po każdej racie.

- Kredyt jest odejmowany od sumy: nagłówek to teraz **Majątek netto**
  (aktywa minus kredyty), a pod nim, gdy masz jakiś dług, widać „Do spłaty".
- Na liście kont kredyt ma kwotę na czerwono ze znakiem minus.
- Lista kont jest ułożona według rodzaju: najpierw konta bankowe, gotówka i
  oszczędności, potem inwestycje (ETF, krypto, waluty), inne, a kredyty
  zawsze na dole.
- Wykres sumy pokazuje majątek netto, a linia kredytu leży pod zerem (na
  minusie).

### Dla aplikacji Android

Spec API (`docs/api.json`) zmienia się tylko o jedno pole; nowy typ konta to
zwykły string. Do zrobienia po stronie apki:

1. Nowa wartość `account_type = "loan"` — dodać do listy typów w formularzu
   konta (etykieta „Kredyt", ikona domu) i do mapowania etykiet/ikon.
2. `GET /assets/summary` → każdy punkt ma nowe pole `debt` (suma sald
   kredytów, dodatnia); `total` oznacza teraz majątek **netto**. Zmienić
   etykietę „Łącznie" na „Majątek netto" i pokazać „Do spłaty: {debt}", gdy
   `debt > 0`.
3. Kwoty wpisów kredytu są **dodatnie** i tak mają być wysyłane w
   `POST /assets/accounts/{id}/snapshots`. Odejmowanie robi serwer, apka ma
   tylko pokazać kwotę kredytu ze znakiem minus / na czerwono.
4. Starsze wersje apki działają dalej, ale nieznany typ `loan` pokażą jako
   zwykłe konto (bez ikony), a „Łącznie" będzie już netto.

## 0.12.1 — 2026-09-28

### Poprawki

- Lista abonamentów znów się wczytuje. Wcześniej wystarczył jeden abonament
  ratalny ze spłaconą ostatnią ratą, żeby cała lista kończyła się błędem.
  Spłacone raty nie pokazują się już wśród aktywnych abonamentów.

## 0.12.0 — 2026-09-20

### Import wyciągu bankowego

W „Dodaj wydatek" doszła czwarta zakładka: **Import wyciągu**. Wrzucasz
eksport operacji z mBanku (CSV) i dostajesz listę obciążeń porównaną z tym,
co już masz zapisane — po kwocie co do grosza i dacie z tolerancją jednego
dnia, bez udziału AI:

- **zielony** — wydatek już jest w bazie,
- **żółty** — niepewne, np. w wyciągu są dwie operacje po 10 zł, a w bazie
  jedna; pod wierszem widać, co dokładnie jest w bazie, żeby dało się
  rozstrzygnąć,
- **pomarańczowy** — nic takiego nie ma.

Przy żółtych i pomarańczowych jest przycisk „Dodaj": otwiera okienko z gotowym
opisem (data, kwota, opis z wyciągu, kategoria banku), który można poprawić,
a potem AI proponuje wydatek jak przy opisie tekstowym. Po zapisie wiersz
zmienia kolor na zielony. Wpływy są pomijane.

Nic nie zapisuje się samo — import tylko pokazuje, czego brakuje.

Dla klientów zewnętrznych: `POST /api/v1/import/bank-csv` zwraca tę samą listę
ze statusami `matched` / `ambiguous` / `missing`.

## 0.11.0 — 2026-09-13

### Czytelna lista pozycji na paragonie

Pozycje w oknie dodawania i edycji wydatku pokazują się jako lista, a nie jako
rząd pól do wypełnienia. Wiersz mieści ikonę kategorii, nazwę, „ilość × cena"
i sumę pozycji po prawej. Formularz rozwija się dopiero po kliknięciu pozycji.

Wcześniej w jednym rzędzie stały cztery pola bez opisów i nie dało się
odróżnić ceny od ilości; na wąskim ekranie kategoria i suma uciekały poza
krawędź okna. Teraz cena i ilość mają etykiety nad polami.

Drobiazgi, które z tego wynikły:

- ilość pokazuje się w podsumowaniu tylko wtedy, gdy różna od jednej,
- pozycja bez kategorii jest oznaczona na czerwono, zanim zapiszesz wydatek,
- suma pozycji odzywa się tylko wtedy, gdy różni się od kwoty wydatku —
  razem z przyciskiem „Ustaw jako kwotę". Wcześniej wisiała zawsze.

### Podgląd zdjęcia przed zapisem

Okno propozycji AI pokazuje zdjęcie, które faktycznie poleciało do modelu —
po kadrowaniu i przetworzeniu, a nie to wybrane z dysku. Widać więc od razu,
czy zły wynik bierze się ze złego kadru. Kliknięcie powiększa.

Zdjęcie stoi pod listą pozycji, tak samo w oknie dodawania i edycji.

### Dla klientów API

`POST /api/v1/ai/receipt` przyjmuje nowe pole `include_preview` (domyślnie
`false`). Przy `true` odpowiedź zawiera `receipt_preview` — przetworzone
zdjęcie jako `data:image/jpeg;base64,...`. Pole jest opcjonalne po obu
stronach, więc klienci, którzy o nim nie wiedzą, działają bez zmian.

---

Wersje wcześniejsze niż 0.11.0 nie mają notatek wydaniowych — ich zakres
odtwarza historia gita.
