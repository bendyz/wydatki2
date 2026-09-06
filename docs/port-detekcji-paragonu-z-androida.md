# Port detekcji paragonu z Androida (OpenCV)

**Ten dokument opisuje kod, którego w tym repo jeszcze nie ma.** Detekcja i kadrowanie
paragonu działa dziś wyłącznie w aplikacji Android; tu jest opis tego, jak działa, i plan
przeniesienia jej do backendu. Sekcje 1–8 są opisem stanu faktycznego po stronie Androida,
sekcja 9 to plan portu wraz ze szkicem implementacji w Pythonie.

Dopóki port nie wejdzie, `app/services/image_service.py` robi wyłącznie skalowanie
i `adaptiveThreshold` — żadnego wykrywania paragonu.

- Źródło (aplikacja Android): `../wydatki2.0android/app/src/main/java/com/bendyz/wydatki/ui/scan/`
- Oryginał dokumentu: `../wydatki2.0android/docs/detekcja-paragonu.md` — **tam jest kanoniczna
  wersja**; przy zmianie detektora po stronie Androida trzeba zaktualizować oba pliki
  albo zastąpić ten odsyłaczem, gdy port już wejdzie i implementacje się rozejdą.
- Wersja OpenCV: `org.opencv:opencv:5.0.0.1` (Android), `opencv-python-headless==4.13.0.92` (backend).

---

## 1. Po co to jest

Do `POST /api/v1/ai/receipt` ma polecieć **sam paragon, wyprostowany**, a nie zdjęcie
paragonu leżącego na biurku pod kątem. Model vision dostaje wtedy więcej pikseli tekstu
na ten sam rozmiar pliku i nie musi zgadywać, co na zdjęciu jest paragonem.

Ten sam detektor pracuje w dwóch miejscach:

| Gdzie | Wejście | Po co |
|---|---|---|
| Podgląd na żywo (`ReceiptFrameAnalyzer`) | klatka YUV z CameraX, ~8 fps | zielona ramka naprowadzająca + zapasowe źródło kadru |
| Zrobione zdjęcie (`detectAndCropWithOpenCV`) | pełny JPEG po korekcie EXIF | właściwy kadr, który leci do AI |

Wspólny detektor to warunek, żeby ramka na podglądzie nie kłamała względem tego, co
faktycznie zostanie wycięte.

---

## 2. Wejście: luminancja + chrominancja

Detektor (`findReceiptQuad(luma, chroma)`) nie dostaje RGB, tylko dwa kanały 8-bitowe:

- **luma** — jasność (kanał Y),
- **chroma** — odległość od szarości: `max(|U − 128|, |V − 128|)`, czyli 0 dla neutralnej bieli.

Powód jest praktyczny: klatka z CameraX *już* jest w YUV, więc płaszczyznę Y bierzemy
wprost (`ImageProxy.toLumaMat()`), bez konwersji kolorów i bez tworzenia bitmapy na każdą
klatkę. Chrominancja przychodzi w połowie rozdzielczości, więc kosztuje ćwierć tego co Y —
detektor i tak skaluje oba wejścia do wspólnej rozdzielczości roboczej.

Zdjęcie (RGBA) jest rozkładane na te same dwa kanały przez `lumaIChroma()`
(`ReceiptImageProcessing.kt`), żeby podgląd i zdjęcie liczyły dokładnie ten sam wzór.

**Chroma jest opcjonalna** (`chroma: Mat? = null`) — bez niej detekcja działa, ale gorzej
radzi sobie z paragonem trzymanym w dłoni: skóra i drewno mają jasność zbliżoną do papieru,
różnią się dopiero nasyceniem.

---

## 3. Algorytm — krok po kroku

### 3.1. Skalowanie do stałej rozdzielczości roboczej

```
DLUGI_BOK_ROBOCZY = 640 px   // INTER_AREA
```

To **warunek poprawności, nie optymalizacja**. Progi Canny'ego (50/150), rozmiary jąder
morfologicznych (3, 9, 15, 31 px) i `epsilon` w `approxPolyDP` są wyrażone w pikselach —
na klatce podglądu 640×480 i na zdjęciu 12 Mpx znaczyłyby coś zupełnie innego. Bez
sprowadzenia do wspólnej skali detekcja na pełnym zdjęciu tonie w teksturze papieru.

Skala jest zapamiętywana i na końcu rogi wracają do współrzędnych oryginału.

### 3.2. Mapa „papierowości"

```
papier = luma − 3.0 × chroma     (addWeighted, z saturacją do 0)
```

Paragon jest biały: jasny **i** nienasycony. Blat, drewno, dłoń i tło są ciemniejsze,
bardziej nasycone albo jedno i drugie. Na tej mapie paragon jest **zwartą jasną plamą** —
a plamę da się progować, czego nie da się zrobić z porozrywanym obrysem krawędzi.

`WAGA_CHROMY = 3.0` — przy 1.0 ciepłe drewno wciąż wchodziło w plamę paragonu.

### 3.3. Dwa niezależne źródła konturów (`zbierzKontury`)

Żadne z nich samo nie wystarcza, więc lecą oba i konkurują punktacją.

**A. Śledzenie krawędzi** — wygrywa na gładkim, jednolitym blacie:

```
GaussianBlur 5×5  →  Canny(50, 150)  →  dilate 3×3 (RECT)
findContours(RETR_LIST, CHAIN_APPROX_SIMPLE)
```

`RETR_LIST`, **nie** `RETR_EXTERNAL` — paragon trzymany w dłoni leży *wewnątrz* obrysu ręki
i jako kontur zewnętrzny nigdy by się nie pojawił. Dylatacja 3×3 skleja krawędź przerwaną
przez zagniecenie.

**B. Segmentacja jasnej plamy** — wygrywa, gdy obrys jest porozrywany (dłoń, jasne drewno):

```
GaussianBlur 5×5 na mapie papieru  →  threshold(OTSU)
morphologyEx OPEN,  ELLIPSE 9×9    // zjada drobiazgi i szum
morphologyEx CLOSE, ELLIPSE 15×15  // zasklepia dziury po tekście na paragonie
findContours(RETR_EXTERNAL, CHAIN_APPROX_SIMPLE)
```

Wyniki obu źródeł trafiają do jednej listy kandydatów.

### 3.4. Kontur → czworokąt (`czworokatZKonturu`)

```
convexHull  →  approxPolyDP z epsilon szukanym połowieniem
```

Sztywne `epsilon = 0.02 × obwód` trafia w równo cztery wierzchołki tylko przy czystych
krawędziach. Na pogiętym paragonie zwraca sześć albo dwanaście i kontur przepada. Dlatego
epsilon jest **szukany bisekcją** w przedziale `[0.005, 0.25] × obwód`, maks. 24 iteracje:
za dużo wierzchołków → podnieś dolną granicę, za mało → obniż górną.

Gdy bisekcja nie trafi w cztery rogi, fallback: `boxPoints(minAreaRect(...))` — najmniejszy
opisany prostokąt. Gorzej, ale to wciąż kandydat, który zostanie oceniony.

### 3.5. Odsiew i punktacja

Każdy kandydat przechodzi cztery testy, **w kolejności od najtańszego**:

| Cecha | Próg | Co odsiewa |
|---|---|---|
| `udzial` = pole / pole kadru | `0.06 … 0.95` | drobiazgi i „kontur całego kadru" |
| `prostokatnosc` = pole / pole `minAreaRect` | `≥ 0.70` | kleksy i kształty nieprostokątne |
| `katy` = regularność kątów | `≥ 0.45` | czworokąty zdegenerowane, mocno skośne |
| `kontrast` z otoczeniem | `≥ 0.02` | równie prostokątny kawałek blatu albo dłoni |

**`regularnoscKatow`** = `1 − max|cos θ|` po czterech wierzchołkach. 1.0 gdy wszystkie kąty
proste, 0.0 gdy czworokąt się zapada.

**`kontrastZOtoczeniem`** — o ile jaśniejsze i bardziej „papierowe" jest wnętrze kandydata
od jego najbliższego otoczenia:

```
maska      = fillPoly(czworokąt)
pierscien  = dilate(maska, ELLIPSE 31×31) − maska
kontrast   = (mean(papier, maska) − mean(papier, pierscien)) / 255
```

Liczony jako **ostatni**, bo wymaga maski na cały kadr i dwóch przejść po obrazie — płacimy
za niego tylko dla kandydatów, które przeszły tanie testy kształtu.

Kandydaci, którzy przeszli, dostają ocenę:

```
ocena = prostokatnosc × katy²  × udzial^0.25 × (kontrast + 0.2)^0.5
```

Wykładniki są celowe: **kąty** decydują najmocniej (kwadrat), **udział w kadrze** ledwie
przechyla szalę (^0.25 — większy nie znaczy lepszy, paragon w rogu zdjęcia jest tak samo
dobry), **kontrast** wchodzi z przesunięciem `+0.2`, żeby paragon na jasnym tle nie dostał
zera za samo słabe odcięcie od blatu.

Wygrywa **najlepiej oceniony, nie największy** kandydat. Rogi są przeliczane z powrotem na
skalę oryginału i porządkowane jako **TL, TR, BR, BL** (`uporzadkujRogi`: min/max sum i
różnic współrzędnych) — prostowanie perspektywy zakłada tę kolejność.

Gdy żaden kandydat nie przejdzie — `null`. To sygnał do ścieżki awaryjnej, nie błąd.

---

## 4. Prostowanie i zapis (`warpAndSave`)

```
outW = max(|TL−TR|, |BL−BR|)
outH = max(|TL−BL|, |TR−BR|)
M    = getPerspectiveTransform(quad, prostokąt outW×outH)
warpPerspective(src, M)  →  JPEG q=92
```

Rozmiar wyjścia bierze się z **dłuższej z pary przeciwległych krawędzi** — przy zdjęciu pod
kątem bliższa krawędź jest dłuższa i to ona wyznacza rozdzielczość, żeby nie tracić
szczegółu na dalszej połowie paragonu.

Warp leci na **pełnej rozdzielczości** oryginału (detekcja liczyła się na 640 px, ale rogi
wróciły przeskalowane) — do AI idzie ostry obraz, nie powiększona miniaturka.

Uwaga: `warpAndSave` **kasuje plik źródłowy** i zwraca nowy (`auto_<nazwa>.jpg`).

---

## 5. Ścieżka awaryjna

`CameraViewModel.analyzePhoto()` — tryb auto, w kolejności:

1. `detectAndCropWithOpenCV(file)` — detekcja na pełnym zdjęciu. **Główne źródło kadru:**
   pracuje na tych pikselach, które faktycznie zostaną wycięte.
2. `cropToQuad(file, liveQuad)` — ramka widziana na podglądzie w chwili migawki. Zapasowo,
   bo to inna klatka i bywa o moment przesunięta. `toPhotoCoords()` zwraca `null`, gdy
   proporcje klatki analizy i zdjęcia rozjeżdżają się o >2% — inne pole widzenia, nakładanie
   jednego na drugie by skłamało.
3. `cropToFrame(file, viewW, viewH)` — sztywna ramka `8%…92% × 12%…82%` kadru, przeliczona
   przez mapowanie `FILL_CENTER` z `PreviewView`. To samo, co robi tryb ręczny.

Tryb ręczny idzie od razu do punktu 3. Zdjęcie z galerii: punkt 1, a przy niepowodzeniu
całe zdjęcie bez kadrowania (ramka kadrująca dotyczy podglądu z kamery, tu nie ma sensu).

Każdy krok jest w `runCatching` — wyjątek z OpenCV degraduje do następnego, nie wywala ekranu.

---

## 6. Podgląd na żywo

`ReceiptFrameAnalyzer` + `ReceiptQuadMapping.kt`:

- **Throttling** `MIN_INTERVAL_MS = 120` (~8 fps) — oko nie odróżnia tego od płynnego,
  a telefon się nie grzeje. `STRATEGY_KEEP_ONLY_LATEST`, analiza na własnym executorze.
- **Rotacja** `rotateQuad()` — obracamy cztery punkty z orientacji sensora do orientacji
  wyświetlania, zamiast obracać całą klatkę. Po obrocie rogi trzeba **ponownie uporządkować**
  (`orderCorners`), bo obrót przesuwa ich role — bez tego kadr wychodzi dobry, ale o 90° obrócony.
- **Mapowanie na ekran** `toViewCoords()` — `PreviewView` skaluje jak `FILL_CENTER`: większa
  z dwóch skal, nadmiar ucięty po równo. Ta sama matematyka co w `cropToFrame`, w drugą stronę.
- **Wygładzanie** `smoothTowards(next, 0.35)` — surowe wyniki z kolejnych klatek drgają na
  tyle, że bez dociągania ramka miga.
- **Histereza zaniku** `MAX_MISSED_FRAMES = 3` (~0,4 s) — ramka nie znika po jednej
  nieudanej klatce.
- Analizator jest wpięty tylko gdy `autoMode && state is Idle`.

Kamera i analiza pracują na `RATIO_4_3_FALLBACK_AUTO_STRATEGY`, wspólnie — bez tego
`toPhotoCoords()` odrzucałoby ramkę na niezgodności proporcji.

---

## 7. Test regresyjny

`../wydatki2.0android/app/src/androidTest/.../ReceiptDetectionTest.kt`

```bash
cd ../wydatki2.0android && ./gradlew connectedDebugAndroidTest
```

- **Instrumentalny**, bo OpenCV potrzebuje natywnych bibliotek — na czystym JVM nie ruszy.
  Potrzebny podłączony telefon.
- **Uruchomienie odinstalowuje aplikację** — kasuje token, adres serwera i hasło do Majątku.
- Zdjęcia w `../wydatki2.0android/app/src/androidTest/assets/receipts/` są **poza gitem** (ciężkie i prywatne); na świeżym
  klonie test się pomija (`assumeTrue`), nie wywala.
- Metryka: **IoU** prostokąta opisanego na wykrytym czworokącie z ręcznie oznaczonym boxem
  z `oczekiwane_paragony.json` (współrzędne względne 0–1). Domyślny próg `0.80`, per zdjęcie
  nadpisywalny przez `prog`; `dopuszczalny_brak: true` dla zdjęć, na których wolno nie znaleźć.
- Mierzy też czas samej detekcji (bez dekodowania JPEG) — **budżet klatki podglądu to 120 ms**.

---

## 8. Znane ograniczenia

- Na podglądzie detektor obrysowuje czasem przedmioty, które paragonem nie są. Ramka jest
  dziś tylko naprowadzaniem i zapasem, więc to kosmetyka — nie psuje tego, co leci do AI.
- **Brak przykładów negatywnych** w zestawie testowym (biurko, klawiatura, książka, kubek).
  Bez nich odrzucanie stroi się na ślepo.
- **Sam próg minimalnej oceny to zła odpowiedź** na powyższe: poprawne trafienia punktują od
  0.195 (podwinięty paragon pod kątem) do 0.594, więc próg musiałby siedzieć tak nisko, że nic
  by nie odsiał. Właściwy kierunek to stabilność w czasie — licznik zgodnych klatek przed
  narysowaniem ramki (`smoothTowards` już jest, brakuje licznika).
- Detektor zakłada **jeden** paragon w kadrze. Dwa obok siebie → wygrywa lepiej oceniony.

---

## 9. Plan portu — co zrobić w tym repo

To repo ma już OpenCV (`opencv-python-headless`) i już przetwarza wgrane zdjęcie w
`app/services/image_service.py` → `save_and_process_receipt_image()`. Detekcja wchodzi tam
jako krok **przed** skalowaniem do `MAX_DIMENSION` i przed `adaptiveThreshold`.

### 9.1. Po co to w backendzie, skoro apka już kadruje

- Zdjęcia wgrane z innych klientów (web, curl, przyszły klient iOS) nie przechodzą przez
  kadrowanie z Androida.
- Zdjęcia z galerii w apce, gdy autodetekcja na telefonie nie znajdzie nic — dziś idą całe.
- Jedno miejsce do strojenia progów zamiast dwóch, i możliwość poprawiania detekcji bez
  wypuszczania nowego APK.

### 9.2. Podwójne kadrowanie — trzeba zablokować ręcznie

Kuszące założenie brzmi: zdjęcie **już wykadrowane** przez telefon ma paragon na całym
kadrze, więc `udzial > MAX_UDZIAL_KADRU (0.95)` odsieje kandydata i backend zostawi obraz
w spokoju. **To nieprawda** — sprawdzone na syntetycznej scenie: drugi przebieg na własnym
wyjściu daje `udzial = 0.915`, czyli poniżej progu, i obraz jest prostowany po raz drugi.
Krawędzie paragonu leżą wtedy na samej granicy kadru, więc wykryty czworokąt bywa o kilka
pikseli skośny i każdy kolejny przebieg dokłada trochę skosu (516×436 → 514×434).

Jedno przejście za dużo jest niegroźne, ale trzeba je świadomie odciąć. Dwa wyjścia:

- **Strażnik w `wykadruj_paragon`**: gdy `udzial > 0.90` **i** czworokąt jest praktycznie
  prostokątem osiowym (rogi w granicach paru pikseli od narożników kadru) — nie ma co
  prostować, zwróć oryginał. Działa dla każdego klienta, nic nie trzeba zmieniać w API.
- **Flaga w multiparcie** (`already_cropped=true` z apki). Prostsze, ale zaufanie do klienta
  i trzeba pamiętać przy każdym nowym.

Rekomendacja: strażnik. Flaga rozwiązuje tylko przypadek, który sami kontrolujemy.

### 9.3. Fałszywe trafienia — w backendzie kosztują więcej niż w apce

Ta sama słabość co w §8 (brak przykładów negatywnych), ale konsekwencje są inne. Na syntetycznej
scenie bez paragonu — ciemna klawiatura i kubek na drewnie — detektor **znalazł kandydata**
(`udzial = 0.113`).

W apce to prawie nic nie kosztuje: użytkownik widzi kadr na ekranie `Processing(cropped=true)`
zanim poleci do AI, i widzi wynik. W backendzie nie ma nikogo, kto by zauważył — wgrany obraz
zostałby po cichu przycięty do kubka, a do modelu poleciałby kadr bez paragonu.

Dlatego przy porcie:

- **oryginał zostaje na dysku**, kadr jest dodatkowym plikiem, nie zamiennikiem — inaczej nie
  da się później zdiagnozować złej odpowiedzi AI ani przestroić progów na prawdziwych danych;
- warto logować `ocena` i `udzial` wybranego kandydata — to jedyne źródło danych do strojenia
  progów na ruchu produkcyjnym;
- zanim to wejdzie na stałe: zestaw negatywny (§8) najpierw, próg potem.

### 9.4. Kolejność kroków — uwaga na dzisiejszy `adaptiveThreshold`

Detekcja **musi** iść na obrazie kolorowym, przed progowaniem: mapa papieru potrzebuje
chrominancji, a po `adaptiveThreshold` nie ma ani koloru, ani jasności — jest binarny szum
tekstu. Docelowa kolejność:

```
imdecode (BGR)
  → wykryj_paragon()  →  warp_perspective     # nowe
  → resize do MAX_DIMENSION
  → cvtColor BGR2GRAY → GaussianBlur → adaptiveThreshold
  → imwrite JPEG
```

Osobno warto sprawdzić, czy `adaptiveThreshold` przed wysłaniem do modelu vision w ogóle
pomaga — dla klasycznego OCR (Tesseract) tak, dla modelu multimodalnego binaryzacja bywa
stratna. To jednak inna decyzja niż ten port; jeśli próg zostanie usunięty, detekcja i tak
siedzi wcześniej i nic się nie zmienia.

### 9.5. Mapowanie API: Kotlin (OpenCV 5) → Python (cv2 4.x)

Android używa OpenCV 5, gdzie część funkcji geometrycznych przeniesiono do
`org.opencv.geometry.Geometry`. W `cv2` 4.x wszystkie są w module głównym:

| Kotlin (OpenCV 5) | Python (`cv2` 4.13) |
|---|---|
| `CVGeometry.convexHull` | `cv2.convexHull` |
| `CVGeometry.arcLength` / `approxPolyDP` | `cv2.arcLength` / `cv2.approxPolyDP` |
| `CVGeometry.contourArea` / `minAreaRect` / `boxPoints` | `cv2.contourArea` / `cv2.minAreaRect` / `cv2.boxPoints` |
| `CVGeometry.getPerspectiveTransform` | `cv2.getPerspectiveTransform` |
| `Imgproc.*` (Canny, dilate, morphologyEx, threshold, warpPerspective) | `cv2.*` — bez zmian |
| `Imgproc.findContours(img, kontury, hierarchia, …)` | `contours, _ = cv2.findContours(img, …)` (4.x zwraca 2 wartości) |
| `Core.addWeighted` / `mean` / `countNonZero` / `absdiff` / `max` / `split` | `cv2.*` — bez zmian |
| ręczne `Mat.release()` | niepotrzebne — GC |

Wejście: backend czyta obraz jako **BGR** (`cv2.imdecode(..., IMREAD_COLOR)`), więc
konwersja to `cv2.COLOR_BGR2YUV`, nie `RGB2YUV`. Kanały Y/U/V wychodzą tak samo.

### 9.6. Szkic implementacji

Wierne tłumaczenie `ReceiptQuadDetector.kt`. Uruchomione na `opencv-python-headless 4.13`
na scenie syntetycznej (biały czworokąt pod kątem na drewnianym tle): wykryte rogi trafiają
w oznaczenie z dokładnością ~3 px. **Nie przetestowane na prawdziwych zdjęciach** — przenieść
i przepuścić przez zestaw z §9.9, nie wklejać w ciemno.

```python
# app/services/receipt_detection.py
import cv2
import numpy as np

DLUGI_BOK_ROBOCZY = 640.0
MIN_UDZIAL_KADRU = 0.06
MAX_UDZIAL_KADRU = 0.95
MIN_PROSTOKATNOSC = 0.70
MIN_REGULARNOSC_KATOW = 0.45
MIN_KONTRAST = 0.02
WAGA_CHROMY = 3.0


def _luma_i_chroma(bgr):
    y, u, v = cv2.split(cv2.cvtColor(bgr, cv2.COLOR_BGR2YUV))
    chroma = np.maximum(
        cv2.absdiff(u, np.full_like(u, 128)),
        cv2.absdiff(v, np.full_like(v, 128)),
    )
    return y, chroma


def _mapa_papieru(luma, chroma):
    dopasowana = cv2.resize(chroma, (luma.shape[1], luma.shape[0]))
    return cv2.addWeighted(luma, 1.0, dopasowana, -WAGA_CHROMY, 0.0)


def _zbierz_kontury(praca, papier):
    rozmyte = cv2.GaussianBlur(praca, (5, 5), 0)
    krawedzie = cv2.Canny(rozmyte, 50, 150)
    krawedzie = cv2.dilate(
        krawedzie, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    )
    # RETR_LIST, nie RETR_EXTERNAL: paragon w dłoni leży wewnątrz obrysu ręki
    z_krawedzi, _ = cv2.findContours(
        krawedzie, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
    )

    _, maska = cv2.threshold(
        cv2.GaussianBlur(papier, (5, 5), 0), 0, 255,
        cv2.THRESH_BINARY | cv2.THRESH_OTSU,
    )
    maska = cv2.morphologyEx(
        maska, cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)),
    )
    maska = cv2.morphologyEx(
        maska, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)),
    )
    z_plamy, _ = cv2.findContours(
        maska, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    return list(z_krawedzi) + list(z_plamy)


def _czworokat_z_konturu(kontur):
    """Epsilon jest szukany bisekcją — sztywne 0.02 gubi pogięty paragon."""
    otoczka = cv2.convexHull(kontur)
    if len(otoczka) < 4:
        return None
    obwod = cv2.arcLength(otoczka, True)
    if obwod <= 0:
        return None

    lo, hi = 0.005, 0.25
    for _ in range(24):
        srodek = (lo + hi) / 2
        przyblizenie = cv2.approxPolyDP(otoczka, srodek * obwod, True)
        if len(przyblizenie) > 4:
            lo = srodek
        elif len(przyblizenie) < 4:
            hi = srodek
        else:
            return przyblizenie.reshape(4, 2).astype(np.float64)

    return cv2.boxPoints(cv2.minAreaRect(otoczka)).astype(np.float64)


def _regularnosc_katow(rogi):
    najgorszy = 0.0
    for i in range(4):
        a = rogi[(i + 3) % 4] - rogi[i]
        b = rogi[(i + 1) % 4] - rogi[i]
        da, db = np.linalg.norm(a), np.linalg.norm(b)
        if da == 0 or db == 0:
            return 0.0
        najgorszy = max(najgorszy, abs(float(a @ b) / (da * db)))
    return max(0.0, 1.0 - najgorszy)


def _kontrast_z_otoczeniem(rogi, papier, jadro):
    maska = np.zeros(papier.shape, np.uint8)
    cv2.fillPoly(maska, [rogi.astype(np.int32)], 255)
    if cv2.countNonZero(maska) == 0:
        return None
    wewnatrz = cv2.mean(papier, maska)[0]
    pierscien = cv2.subtract(cv2.dilate(maska, jadro), maska)
    na_zewnatrz = (
        cv2.mean(papier, pierscien)[0] if cv2.countNonZero(pierscien) else 0.0
    )
    return (wewnatrz - na_zewnatrz) / 255.0


def _ocen(prostokatnosc, katy, udzial, kontrast):
    return prostokatnosc * katy**2 * udzial**0.25 * (kontrast + 0.2) ** 0.5


def _uporzadkuj_rogi(rogi):
    """TL, TR, BR, BL — prostowanie perspektywy zakłada tę kolejność."""
    suma, roznica = rogi[:, 0] + rogi[:, 1], rogi[:, 1] - rogi[:, 0]
    return np.array([
        rogi[np.argmin(suma)], rogi[np.argmin(roznica)],
        rogi[np.argmax(suma)], rogi[np.argmax(roznica)],
    ], dtype=np.float32)


def znajdz_paragon(bgr):
    """Rogi paragonu (TL, TR, BR, BL) we współrzędnych `bgr`, albo None."""
    luma, chroma = _luma_i_chroma(bgr)
    zmniejszenie = DLUGI_BOK_ROBOCZY / max(luma.shape[:2])
    praca = (
        cv2.resize(luma, None, fx=zmniejszenie, fy=zmniejszenie,
                   interpolation=cv2.INTER_AREA)
        if zmniejszenie < 1.0 else luma
    )
    skala = praca.shape[1] / luma.shape[1]

    papier = _mapa_papieru(praca, chroma)
    pole_kadru = float(praca.shape[0] * praca.shape[1])
    jadro = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31))

    najlepszy, najlepsza_ocena = None, 0.0
    for kontur in _zbierz_kontury(praca, papier):
        rogi = _czworokat_z_konturu(kontur)
        if rogi is None:
            continue

        pole = abs(cv2.contourArea(rogi.astype(np.float32)))
        udzial = pole / pole_kadru
        if not (MIN_UDZIAL_KADRU <= udzial <= MAX_UDZIAL_KADRU):
            continue
        (_, (w, h), _) = cv2.minAreaRect(rogi.astype(np.float32))
        if w * h <= 0:
            continue
        prostokatnosc = pole / (w * h)
        if prostokatnosc < MIN_PROSTOKATNOSC:
            continue
        katy = _regularnosc_katow(rogi)
        if katy < MIN_REGULARNOSC_KATOW:
            continue
        # Kontrast na końcu — jako jedyny wymaga maski na cały kadr
        kontrast = _kontrast_z_otoczeniem(rogi, papier, jadro)
        if kontrast is None or kontrast < MIN_KONTRAST:
            continue

        ocena = _ocen(prostokatnosc, katy, udzial, kontrast)
        if ocena > najlepsza_ocena:
            najlepsza_ocena, najlepszy = ocena, rogi

    if najlepszy is None:
        return None
    return _uporzadkuj_rogi(najlepszy / skala)


def wyprostuj(bgr, rogi):
    """Prostuje czworokąt do prostokąta na pełnej rozdzielczości."""
    tl, tr, br, bl = rogi
    out_w = max(1, int(max(np.linalg.norm(tl - tr), np.linalg.norm(bl - br))))
    out_h = max(1, int(max(np.linalg.norm(tl - bl), np.linalg.norm(tr - br))))
    cel = np.array([
        [0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]
    ], dtype=np.float32)
    M = cv2.getPerspectiveTransform(rogi, cel)
    return cv2.warpPerspective(bgr, M, (out_w, out_h))


def wykadruj_paragon(bgr):
    """Zwraca wykadrowany paragon albo oryginał, gdy nic wiarygodnego nie widać."""
    rogi = znajdz_paragon(bgr)
    return bgr if rogi is None else wyprostuj(bgr, rogi)
```

Wpięcie w `save_and_process_receipt_image()`:

```python
img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
if img is None:
    raise ValueError("Nie można odczytać obrazu…")

try:
    img = wykadruj_paragon(img)          # nowe — degraduje do oryginału
except cv2.error:
    logger.warning("Detekcja paragonu nie powiodła się, zapisuję bez kadrowania")

height, width = img.shape[:2]            # dalej bez zmian
```

Wyjątek z OpenCV nie może wywalić uploadu — to samo założenie co `runCatching` w apce.

### 9.7. EXIF

Android prostuje obrót po EXIF **przed** detekcją (`rotateBitmap`). `cv2.imdecode`
**ignoruje EXIF** — zdjęcie z telefonu przyjdzie w orientacji sensora. Sama detekcja jest na
to odporna (czworokąt to czworokąt niezależnie od obrotu), ale wynik zostanie zapisany
obrócony i tekst na paragonie poleci do AI bokiem. Do zrobienia przy porcie: odczyt
`Orientation` (np. przez `PIL.ImageOps.exif_transpose` albo `piexif`) i `cv2.rotate` przed
detekcją. Pillow nie jest dziś zależnością backendu — trzeba ją dodać albo sparsować tag ręcznie.

### 9.8. Wydajność

Na telefonie mediana detekcji mieści się w budżecie klatki podglądu 120 ms (na 640 px, bez
dekodowania JPEG). Na backendzie dochodzi dekodowanie pełnego zdjęcia i `warpPerspective` na
pełnej rozdzielczości — rzędu setek ms na obraz. Endpoint `POST /api/v1/ai/receipt` jest
`async`, a to praca CPU-bound: **`save_and_process_receipt_image` powinno lecieć przez
`run_in_threadpool` / `asyncio.to_thread`**, inaczej blokuje pętlę zdarzeń. Dziś ten problem
już istnieje (resize + adaptiveThreshold), port tylko go powiększa.

### 9.9. Test po stronie backendu (do napisania)

Odpowiednik `ReceiptDetectionTest`, ale prostszy — na CPython OpenCV działa bez urządzenia,
więc to zwykły `pytest`:

- zdjęcia i `oczekiwane_paragony.json` — ten sam format co w `../wydatki2.0android/app/src/androidTest/assets/receipts/`
  (box we współrzędnych względnych 0–1, `prog`, `dopuszczalny_brak`), zestaw poza gitem,
  `pytest.skip` gdy katalog pusty;
- metryka IoU prostokąta opisanego z oznaczeniem, próg domyślny 0.80;
- **jeden test więcej niż na Androidzie**: idempotencja — wykadrowany paragon podany
  ponownie musi zwrócić `None` z `znajdz_paragon`.

Dopóki obie implementacje żyją równolegle, ten sam zestaw zdjęć na obu stronach jest jedynym
sposobem, żeby wiedzieć, że nie rozjechały się progi.
