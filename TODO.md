# TODO

## Wspólny budżet (household / multi-user)

**Cel:** Dwa konta operują na tych samych wydatkach. Każdy widzi wspólne wydatki,
ale może oznaczyć pojedynczy wydatek jako prywatny (niewidoczny dla drugiej osoby).

### Co trzeba zrobić

**Modele (rdzeń):**
- Nowa tabela `Household` (id, name, created_by)
- Tabela asocjacyjna `household_members` (household_id, user_id, role)
- `Expense.household_id` — FK do Household (nullable; null = tylko mój)
- `Expense.private` — Boolean, default False; jeśli True widzi tylko twórca

**Backend:**
- `get_expenses` — przepisanie logiki: zwróć *(moje prywatne)* + *(wspólne household, gdzie private=False)*
  - To dotyka KAŻDEGO miejsca które odpytuje wydatki (stats, AI duplikaty, receipts, itd.)
- Nowe CRUD: `create_household`, `add_member`, `remove_member`, `get_household_members`
- Logika zaproszenia: household ma unikalny kod (6 znaków), druga osoba wpisuje go w UI
- Kategorie i tagi: decyzja — wspólne per household czy każdy ma swoje?
  - Prostsze: każdy ma swoje (mniejsza zmiana)
  - Lepsze UX: wspólne (większa zmiana, kategorie/tagi też dostają household_id)
- Statystyki: agregacja po household zamiast user_id
- AI: draft trafia do household domyślnie; opcja "prywatny" w modalu draftu

**Frontend:**
- Zarządzanie household w panelu admina lub osobny widok (zaproś, usuń, opuść)
- Ikonka kłódki 🔒 na wydatku w edycji — toggle private/shared
- Wizualny indicator w liście wydatków dla wydatków prywatnych (np. szary/kursywa)
- Filtr: "wszystkie" / "tylko moje"
- Widoczne kto dodał który wydatek (e.description + "dodał: X")

**Ważne:**
- Prywatne wydatki MUSZĄ być filtrowane po stronie API, nie frontend
  (żeby nie dało się ich podejrzeć przez devtools/network tab)
- Migracja: istniejące wydatki zostają przypisane do użytkownika (household_id = null)

### Szacunek

~15-20h pracy (~2-3 dni). Inwazyjna zmiana rdzenia — każdy moduł wymaga weryfikacji.
Robić tylko jeśli to realna potrzeba w najbliższym czasie, nie "może kiedyś".
