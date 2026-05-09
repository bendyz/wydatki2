# Wydatki 2.0

Osobisty tracker wydatków z AI. Skanuj paragony zdjęciem lub wpisz tekstem — AI rozpozna kwotę, sklep i kategorie.

**Stack:** FastAPI · SQLite · Jinja2 · vanilla JS · OpenRouter API

---

## Wymagania

- Docker **lub** Podman (zalecany)
- Klucz API OpenRouter → [openrouter.ai/keys](https://openrouter.ai/keys)

---

## Pierwsze uruchomienie

### 1. Sklonuj repo

```bash
git clone https://github.com/bendyz/wydatki2.git
cd wydatki2
```

### 2. Przygotuj katalog danych

```bash
mkdir -p data/config data/db data/uploads/receipts
```

### 3. Utwórz plik konfiguracyjny

```bash
cp data/config/config.yaml.example data/config/config.yaml  # jeśli masz przykład
# lub utwórz ręcznie:
```

Minimalna zawartość `data/config/config.yaml`:

```yaml
registration_enabled: true
SECRET_KEY: "wygeneruj-losowy-string-min-32-znaki"

server:
  host: "0.0.0.0"
  port: 8000

database:
  url: "sqlite:///data/db/wydatki.db"

storage:
  uploads_path: "data/uploads/receipts"

openrouter:
  api_key: "sk-or-v1-TWÓJ_KLUCZ_API"
  model: "google/gemini-2.0-flash-001"
  max_tokens: 4096
  temperature: 0.1

personal_context: []

duplicates:
  date_range_days: 3
  amount_threshold: 0.5
```

> **Ważne:** `server.host` musi być `"0.0.0.0"` wewnątrz kontenera.

---

## Budowanie obrazu

### Docker

```bash
docker build -t wydatki .
```

### Podman

```bash
podman build -t wydatki .
```

---

## Uruchamianie

### Docker

```bash
docker run -d \
  --name wydatki \
  -p 8000:8000 \
  -v ./data:/app/data \
  --restart unless-stopped \
  wydatki
```

### Podman

```bash
podman run -d \
  --name wydatki \
  -p 8000:8000 \
  -v ./data:/app/data:Z \
  wydatki
```

> Flaga `:Z` jest wymagana na systemach z SELinux (Fedora, RHEL, CentOS).

Aplikacja działa pod: **http://localhost:8000**

---

## Podman jako usługa systemd (Quadlet)

Aby kontener startował automatycznie po restarcie serwera:

```bash
# 1. Skopiuj plik quadlet
mkdir -p ~/.config/containers/systemd/
cp wydatki.container ~/.config/containers/systemd/

# 2. Edytuj ścieżkę do danych jeśli trzeba (domyślnie ~/wydatki-data)
#    Upewnij się że katalog istnieje:
mkdir -p ~/wydatki-data
cp -r data/* ~/wydatki-data/

# 3. Zbuduj obraz (jeśli jeszcze nie zbudowany)
podman build -t wydatki .

# 4. Włącz i uruchom usługę
systemctl --user daemon-reload
systemctl --user enable --now wydatki.service

# 5. Włącz autostart bez konieczności logowania
loginctl enable-linger $USER
```

Przydatne komendy:

```bash
systemctl --user status wydatki.service   # status
systemctl --user restart wydatki.service  # restart
journalctl --user -u wydatki.service -f   # logi na żywo
```

---

## Aktualizacja

```bash
git pull
podman build -t wydatki .
podman restart wydatki
# lub jeśli używasz systemd:
systemctl --user restart wydatki.service
```

---

## Pierwsze logowanie

1. Otwórz aplikację w przeglądarce
2. Zarejestruj konto — **pierwszy użytkownik automatycznie zostaje administratorem**
3. Po zalogowaniu przejdź do **Admin → Konfiguracja** aby ustawić klucz OpenRouter i personalizację AI
4. Wyłącz rejestrację jeśli nie chcesz nowych użytkowników

---

## Nginx reverse proxy (HTTPS)

Minimalna konfiguracja nginx:

```nginx
server {
    listen 443 ssl;
    server_name twoja-domena.pl;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

> Jeśli używasz Nginx Proxy Manager, włącz opcję **"Trust Forwarded Proto"** w ustawieniach proxy hosta — inaczej aplikacja będzie generować `http://` linki mimo działającego HTTPS.
