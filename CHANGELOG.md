# Zmiany

Notatki wydaniowe prowadzone od wersji 0.11.0. Opisują zmiany widoczne dla
użytkownika — szczegóły techniczne są w historii gita.

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
