# Port detekcji paragonu do backendu — design

**Data:** 2026-09-06
**Gałąź:** `feature/port-detekcji-paragonu`
**Dokument źródłowy:** [`docs/port-detekcji-paragonu-z-androida.md`](../../port-detekcji-paragonu-z-androida.md)
(opis algorytmu po stronie Androida, §1–8, oraz plan portu i szkic w Pythonie, §9)

## 1. Cel

Backend ma sam wykrywać i prostować paragon na wgranym zdjęciu, zamiast polegać na tym,
że zrobiła to aplikacja androidowa. Dziś `app/services/image_service.py` robi wyłącznie
skalowanie, konwersję do szarości i `adaptiveThreshold` — żadnego kadrowania.

Po co, skoro apka już kadruje (§9.1 dokumentu źródłowego):

- zdjęcia z innych klientów (www, `curl`, przyszły klient iOS) nie przechodzą przez
  kadrowanie z Androida;
- zdjęcia z galerii, gdy autodetekcja na telefonie nic nie znalazła, idą dziś w całości;
- jedno miejsce do strojenia progów zamiast dwóch, i możliwość poprawiania detekcji bez
  wypuszczania nowego APK.

Model vision dostaje wtedy więcej pikseli tekstu na ten sam rozmiar pliku i nie musi
zgadywać, co na zdjęciu jest paragonem.

## 2. Decyzje

| Decyzja | Wybór | Uzasadnienie |
|---|---|---|
| Wdrożenie | **Na ostro** — kadr idzie do AI od pierwszego dnia | Bez trybu cieniowego i bez przełącznika w konfiguracji. Ryzyko fałszywego trafienia (§9.3) przyjęte świadomie, log z §5 jest jego przeciwwagą. |
| Podwójne kadrowanie | **Flaga `already_cropped` w API** | Zamiast strażnika rekomendowanego w §9.2. Klient wie najlepiej, czy już kadrował. |
| Pliki na dysku | **Tylko wynik + log metryk** | Oryginał nie zostaje. Dysk nie rośnie, cena: diagnostyka opiera się wyłącznie na logu. |
| `adaptiveThreshold` | **Zostaje; los rozstrzyga pomiar po porcie** | Osobny skrypt porównawczy, decyzja po zobaczeniu tabeli. Port nie zmienia tej części pipeline. |
| Testy | **`pytest` na geometrię + skrypt na pomiar AI** | Darmowe i powtarzalne w teście, płatne i jednorazowe w skrypcie. |
| Struktura | **Osobny moduł czystych funkcji** | Detektor testowalny bez dysku, bez `UploadFile` i bez serwera. |

## 3. Moduł detekcji

Nowy plik `app/services/receipt_detection.py` — wierne tłumaczenie `ReceiptQuadDetector.kt`
według szkicu §9.6 dokumentu źródłowego. Czyste funkcje: numpy wchodzi, numpy wychodzi.
Zero I/O, zero zależności od FastAPI, zero logowania w środku.

### 3.1. Powierzchnia publiczna

```python
class Detection(NamedTuple):
    score: float          # ocena wybranego kandydata
    frame_ratio: float    # udział w polu kadru
    out_size: tuple[int, int]

def find_receipt_quad(bgr) -> np.ndarray | None:
    """Rogi paragonu (TL, TR, BR, BL) we współrzędnych `bgr`, albo None."""

def deskew(bgr, quad) -> np.ndarray:
    """Prostuje czworokąt do prostokąta na pełnej rozdzielczości."""

def crop_receipt(bgr) -> tuple[np.ndarray, Detection | None]:
    """Wykadrowany paragon albo oryginał, gdy nic wiarygodnego nie widać."""
```

`crop_receipt` zwraca krotkę, a nie sam obraz jak w szkicu §9.6. Powód: skoro oryginał nie
zostaje na dysku, metryki muszą wyjechać z modułu na zewnątrz, bo inaczej nie ma czego
logować — a log jest jedynym śladem po tym, co detektor zrobił. `None` w drugim polu znaczy
„nic nie wykryto, obraz wraca nietknięty".

### 3.2. Nazewnictwo

Identyfikatory **angielskie**, docstringi i komunikaty **polskie** — konwencja całego repo
(`save_and_process_receipt_image`, `generate_unique_filename`). Szkic §9.6 używa nazw
polskich; dokument źródłowy dostanie tabelkę mapowania, analogiczną do tej z §9.5
(Kotlin → Python).

| Szkic §9.6 | Ten moduł |
|---|---|
| `znajdz_paragon` | `find_receipt_quad` |
| `wyprostuj` | `deskew` |
| `wykadruj_paragon` | `crop_receipt` |
| `_luma_i_chroma` | `_luma_and_chroma` |
| `_mapa_papieru` | `_paper_map` |
| `_zbierz_kontury` | `_collect_contours` |
| `_czworokat_z_konturu` | `_quad_from_contour` |
| `_regularnosc_katow` | `_angle_regularity` |
| `_kontrast_z_otoczeniem` | `_surround_contrast` |
| `_ocen` | `_score` |
| `_uporzadkuj_rogi` | `_order_corners` |

### 3.3. Progi

Stałe modułu, **nie** `config.yaml`:

```python
WORKING_LONG_EDGE = 640.0     # warunek poprawności, nie optymalizacja (§3.1)
MIN_FRAME_RATIO = 0.06
MAX_FRAME_RATIO = 0.95
MIN_RECTANGULARITY = 0.70
MIN_ANGLE_REGULARITY = 0.45
MIN_CONTRAST = 0.02
WEIGHT_CHROMA = 3.0
```

Wartości i cały algorytm — bez zmian względem §3 i §9.6: mapa papierowości
`luma − 3.0 × chroma`, dwa niezależne źródła konturów (Canny + segmentacja plamy Otsu),
epsilon w `approxPolyDP` szukany bisekcją, cztery testy odsiewu w kolejności od najtańszego,
ocena `prostokątność × kąty² × udział^0.25 × (kontrast + 0.2)^0.5`, wygrywa najlepiej
oceniony, nie największy.

Progi nie idą do konfiguracji celowo: strojenie odbywa się przez test IoU i przebudowę
obrazu, a bez zestawu negatywnego (§8, §9.3) wystawienie ich na zewnątrz dałoby pokrętło,
którym nie ma jak świadomie kręcić.

## 4. Zmiany w API

Nowe pole `already_cropped: bool = Form(False)` w **obu** endpointach przyjmujących zdjęcie:

- `POST /api/v1/ai/receipt` — skan do draftu,
- `POST /api/v1/receipts/{expense_id}/receipt` — podpięcie zdjęcia do zapisanego wydatku.

Apka androidowa przechodzi przez oba po kolei z tym samym plikiem; bez flagi w drugim
endpoincie kadrowanie i tak wykonałoby się na już wykadrowanym paragonie, tyle że przy
zapisie.

`Form`, nie query — oba endpointy są multipartem. Domyślnie `False`, więc klient, który nic
nie wie o fladze, dostaje kadrowanie.

Nazwa opisuje **wiedzę klienta** („to zdjęcie jest już wykadrowane"), a nie polecenie dla
backendu („nie kadruj"). Ta pierwsza starzeje się lepiej: gdy dojdzie druga rzecz zależna od
tego faktu, flaga nadal będzie prawdziwa.

Po zmianie: regeneracja `docs/api.json` przez `python scripts/export_openapi.py`.

### 4.1. Oczekiwanie wobec klienta androidowego

Flaga ma iść jako `true` **tylko** gdy własna detekcja apki faktycznie coś wycięła. Przy
degradacji do `cropToFrame` albo do całego zdjęcia z galerii (§5 dokumentu źródłowego,
punkty 2–3) powinno lecieć `false`, żeby backend spróbował.

To zmiana w repo `../wydatki2.0android`, poza zakresem tego specu — ale bez niej flaga nie
ma nadawcy.

## 5. Pipeline

```
imdecode (BGR)
  → korekta orientacji z EXIF                    # nowe
  → if not already_cropped: crop_receipt()       # nowe, log metryk
  → resize do MAX_DIMENSION
  → cvtColor BGR2GRAY → GaussianBlur → adaptiveThreshold
  → imwrite JPEG q=85
```

Detekcja **musi** iść na obrazie kolorowym, przed progowaniem: mapa papieru potrzebuje
chrominancji, a po `adaptiveThreshold` nie ma ani koloru, ani jasności — jest binarny szum
tekstu (§9.4).

### 5.1. EXIF

Obowiązkowy, nie opcjonalny. `cv2.imdecode` ignoruje orientację, więc zdjęcie z telefonu
przychodzi w orientacji sensora. Sama detekcja to zniesie — czworokąt zostaje czworokątem po
obrocie — ale zapisany kadr poleciałby do modelu bokiem i to jest regresja względem dzisiaj.

`Pillow` dochodzi do `requirements.txt`, korekta przez `ImageOps.exif_transpose`. Ręczne
parsowanie tagu odrzucone: kilkadziesiąt linii do utrzymania po to, żeby nie dodać
zależności, którą i tak ma pół ekosystemu.

### 5.2. Odporność na błędy

`cv2.error` w detekcji → `logger.warning` i obraz leci dalej nietknięty. Wyjątek z OpenCV nie
może wywalić uploadu — to samo założenie co `runCatching` w apce (§5 dokumentu źródłowego).

### 5.3. Logowanie

`logger = logging.getLogger(__name__)` w `image_service.py`, komunikaty po polsku — konwencja
z `scheduler.py` i `ai_service.py`. Jedna linia na upload, poziom `INFO`:

- trafienie: `ocena`, `udzial`, rozmiar wyjścia;
- pudło: `"detekcja: brak kandydata"`;
- flaga: `"detekcja pominięta (already_cropped)"`.

To jedyne źródło danych do strojenia progów na ruchu produkcyjnym (§9.3) i jedyny ślad
diagnostyczny, skoro oryginał nie zostaje.

### 5.4. Praca CPU poza pętlą zdarzeń

Cały blok OpenCV idzie przez `asyncio.to_thread`. Endpoint jest `async`, a to setki
milisekund czystego CPU na obraz (§9.8). Błąd istnieje już dziś przez `resize` +
`adaptiveThreshold`; port go powiększa, więc naprawiamy przy okazji.

`save_and_process_receipt_image` zostaje `async def`, czyta bajty, a przetwarzanie woła
w wątku. Sygnatura dla obu endpointów bez zmian poza nową flagą.

## 6. Weryfikacja

### 6.1. `requirements-dev.txt`

Nowy plik: `pytest`. **Nie** do `requirements.txt` — ten instaluje Dockerfile do obrazu
produkcyjnego. `tests/` i `scripts/` nie są kopiowane do obrazu, więc runtime się nie zmienia.

Dochodzi też `pytest.ini` z `pythonpath = .`: repo nie jest pakietem instalowalnym i nie ma
`pyproject.toml`, więc bez tego testy nie zaimportują `app.*`.

`pytest-asyncio` nie jest potrzebne — testy celują w funkcje synchroniczne
(`_decode_upright`, `_process_and_save`, detektor), nie w `async def`.

To pierwszy test w tym repo; `CLAUDE.md` („There are no tests in this project") wymaga
aktualizacji.

### 6.2. `tests/test_receipt_detection.py`

Regresja geometrii — za darmo i powtarzalnie.

- **Zestaw:** 18 zdjęć z `app/src/androidTest/assets/receipts/` w repo androidowym,
  `oczekiwane_paragony.json` **poziom wyżej**, w `assets/`. Ścieżka z env
  `RECEIPT_TEST_SET`, domyślnie `../wydatki2.0android/app/src/androidTest/assets/`.
  Brak katalogu → `pytest.skip`; na świeżym klonie test ma milczeć, nie wywalać zestawu.
  (Dokument źródłowy §9.9 podaje lokalizację JSON-a niedokładnie — do poprawienia tam.)
- **Metryka:** IoU prostokąta opisanego na wykrytym czworokącie z ręcznym oznaczeniem
  (współrzędne względne 0–1). Próg domyślny `0.80`, nadpisywalny per zdjęcie przez `prog`,
  `dopuszczalny_brak: true` dla zdjęć, na których wolno nie znaleźć. Ten sam format i te same
  progi co po stronie Androida — jedyny sposób, żeby wiedzieć, że implementacje się nie
  rozjechały.
- `pytest.mark.parametrize` po zdjęciach, żeby raport pokazywał, **które** zdjęcie padło.

### 6.3. Test powtórnego przebiegu

Dokument źródłowy §9.9 chce testu idempotencji: wykadrowany paragon podany ponownie ma
zwrócić `None`. **Ta własność jest nieprawdziwa** i sam dokument to mierzy — §9.2 pokazuje, że
drugi przebieg na własnym wyjściu daje `udzial = 0.915`, czyli poniżej progu `0.95`, więc
kandydat przechodzi i obraz jest prostowany po raz drugi. Oba zdania mogłyby być prawdziwe
naraz tylko ze strażnikiem z §9.2, którego świadomie nie robimy (sekcja 2).

Test sprawdza więc własność, która jest prawdziwa i wciąż warta pilnowania: **drugi przebieg
musi być praktycznie tożsamością** — IoU kadru z drugiego przebiegu względem pierwszego
`≥ 0.98`, rozmiar w granicach paru pikseli. Dokumentuje faktyczne zachowanie zamiast
pobożnego życzenia i złapie realną regresję: zmianę progów, po której powtórne kadrowanie
zaczyna obraz zjadać.

### 6.4. `scripts/porownaj_binaryzacje.py`

Rozstrzygnięcie losu `adaptiveThreshold` — ręcznie i płatnie.

Przepuszcza te same 18 zdjęć przez `parse_receipt_image` w dwóch wariantach (z progiem
i bez), po kadrowaniu w obu. Otwiera prawdziwą sesję SQLite i bierze `user_id` z argumentu,
żeby nie duplikować budowania promptu. Wypisuje tabelę: kwota, sklep, liczba pozycji, czas —
wariant obok wariantu. 36 wywołań OpenRouter, jednorazowo.

Prawdy podstawowej nie ma — nikt nie oznaczył oczekiwanych kwot dla tych zdjęć — więc werdykt
wydaje człowiek, patrząc na tabelę i na paragony. Przy 18 pozycjach to kilka minut,
a oznaczanie kwot do automatycznego porównania kosztuje więcej, niż jest warte dla
jednorazowej decyzji.

**Skrypt powstaje w tej robocie, decyzja o progu zapada po niej.** Port wchodzi
z `adaptiveThreshold` nietkniętym; ewentualne usunięcie progu to osobny commit, gdy tabela
go uzasadni.

## 7. Poza zakresem

Świadome ubytki:

- **Strażnik podwójnego kadrowania (§9.2)** — zastąpiony flagą. Cena: APK w wersji sprzed tej
  zmiany, który wyśle wykadrowany paragon bez flagi, dostanie drugie prostowanie. Pierwsza
  ocena (syntetyczna scena, `udzial = 0.915`, kadr 516×436 → 514×434) mówiła "lekki skos,
  jednorazowo niegroźne" — **pomiar na prawdziwych zdjęciach ją obala**:
  `test_powtorne_kadrowanie_niczego_nie_zjada` (§9.9 dokumentu źródłowego) pokazuje 10 z 16
  zdjęć poniżej progu pokrycia 0.98, najgorzej `07.jpg` przy 0.476 — drugi przebieg zostawia
  niecałą połowę powierzchni pierwszego wyjścia, nie tylko lekki skos. Cena jednorazowego
  braku flagi jest więc realna utrata obrazu, nie kosmetyka. To samo obala rekomendację
  strażnika z §9.2: przy drugim przebiegu na wszystkich 18 zdjęciach `frame_ratio`
  zwycięskiego kandydata mieści się w przedziale 0.477–0.894, więc próg `udzial > 0.90` nie
  zadziałałby prawie na żadnym z nich — patrz poprawiony §9.2 dokumentu źródłowego.
- **Zestaw negatywny (§8, §9.3)** — biurko, klawiatura, kubek, książka. Bez niego odrzucanie
  stroi się na ślepo, a przy trybie „na ostro" fałszywe trafienie idzie do AI niezauważone.
  Dług świadomy: żeby go spłacić, trzeba najpierw zrobić zdjęcia, których nie ma. Log
  z sekcji 5.3 jest namiastką — po kilkudziesięciu paragonach pokaże rozkład ocen.
- **Progi w `config.yaml`** — pokrętło, którym bez zestawu negatywnego nie ma jak kręcić.
- **Sprzątanie `data/uploads/receipts/0/`** — 17 MB tymczasowych zdjęć z `/ai/receipt`, pliki
  od kwietnia, nikt ich nie kasuje. Problem zastany i niezależny od portu; ten port go nie
  pogarsza, bo oryginał nie zostaje. Osobne zadanie.
- **Ujednolicenie implementacji z Androidem** — dwie kopie algorytmu żyją równolegle. Wspólny
  zestaw zdjęć i te same progi to jedyne zakładane spoiwo.
- **Zmiana w apce androidowej** (wysyłanie `already_cropped`) — inne repo, osobne zadanie.

## 8. Kryteria ukończenia

1. `app/services/receipt_detection.py` istnieje, jest czysty (brak I/O, brak importów
   FastAPI) i eksportuje `find_receipt_quad`, `deskew`, `crop_receipt`, `Detection`.
2. Oba endpointy przyjmują `already_cropped`; przy `true` detekcja się nie uruchamia,
   co widać w logu.
3. Zdjęcie z telefonu z EXIF-em zapisuje się w poprawnej orientacji.
4. `cv2.error` w detekcji nie przerywa uploadu — obraz zapisuje się bez kadrowania,
   w logu jest `warning`.
5. `pytest` przechodzi na zestawie 18 zdjęć **z tymi samymi progami per zdjęcie, co test
   androidowy**, a bez zestawu pomija się zamiast padać.

   Uwaga: szkic §9.6 był uruchomiony wyłącznie na scenie syntetycznej (~3 px dokładności),
   nigdy na prawdziwych zdjęciach — dokument mówi to wprost. Jeśli któreś zdjęcie nie
   dobije do progu, to **wynik do porównania z Androidem**, a nie automatyczna zgoda na
   obniżenie progu: rozjazd oznacza błąd w tłumaczeniu, a nie zbyt ostre kryterium.
   Obniżenie progu wymaga osobnej decyzji i wpisu w dokumencie źródłowym.
6. Test powtórnego przebiegu (6.3) przechodzi.
7. `scripts/porownaj_binaryzacje.py` uruchamia się i wypisuje tabelę dla obu wariantów.
8. `docs/api.json` przegenerowany, `CLAUDE.md` zaktualizowany (testy, kadrowanie, Pillow),
   `VERSION` podbity.
