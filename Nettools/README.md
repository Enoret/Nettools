<p align="center">
  <img src="nettools/assets/logo.svg" alt="NetTools Logo" width="80" height="80">
</p>

<h1 align="center">NetTools</h1>

<p align="center">
  <strong>Monitor de red y test de velocidad autoalojado</strong>
</p>

<p align="center">
  <a href="#instalacion-docker">Docker</a> &bull;
  <a href="#instalacion-manual">Manual</a> &bull;
  <a href="#funcionalidades">Funcionalidades</a> &bull;
  <a href="#capturas">Capturas</a> &bull;
  <a href="#api">API</a>
</p>

<p align="center">
  <img src="https://img.shields.io/docker/pulls/mbraut/nettools?style=flat-square&logo=docker" alt="Docker Pulls">
  <img src="https://img.shields.io/github/license/Enoret/Nettools?style=flat-square" alt="License">
  <img src="https://img.shields.io/badge/python-3.12-blue?style=flat-square&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/fastapi-0.109-green?style=flat-square&logo=fastapi" alt="FastAPI">
</p>

---

## Descripcion

**NetTools** es una aplicacion web autoalojada para monitorizar tu red local y medir la velocidad de tu conexion a Internet. Ofrece una interfaz moderna y responsive con tres modulos principales: **Net Speed** (tests de velocidad), **Net Alert** (descubrimiento de dispositivos) y **Net Check** (herramientas de diagnostico).

### Caracteristicas principales

- Tests de velocidad automaticos y manuales con **Ookla Speedtest CLI**
- Descubrimiento de dispositivos en tu red local con **arp-scan** y **nmap**
- Herramientas de diagnostico: **Ping**, **Traceroute** y **NSLookup**
- Notificaciones por **Telegram** al detectar nuevos dispositivos
- Graficos interactivos con historial de velocidad, latencia y dispositivos
- Temas claro, oscuro y automatico
- Colores personalizables
- Zona horaria configurable
- API REST completa
- Sin dependencias en la nube - todo se ejecuta en tu servidor

---

## Funcionalidades

### Net Speed
- Test de velocidad manual con seleccion de servidor
- Tests automaticos programables (15 min - 24 h)
- Graficos de historial de velocidad (descarga/subida)
- Graficos de latencia (ping/jitter)
- Promedio de velocidad por hora
- Tabla de tests recientes
- Estadisticas: mejor descarga, mejor subida, mejor ping, total tests

### Net Alert
- Escaneo automatico de la red local (arp-scan + nmap)
- Deteccion de dispositivos nuevos
- Identificacion de marca/fabricante por MAC
- Edicion de dispositivos: nombre, tipo, ubicacion, descripcion
- Marcado de IP estatica o DHCP
- Filtros: todos, en linea, desconectados, nuevos, guardados, manuales
- Ordenacion por nombre, IP, MAC, marca, ubicacion, estado
- Historial de dispositivos conectados (grafico)
- Notificaciones por Telegram al detectar nuevos dispositivos
- Ping rapido desde la tarjeta del dispositivo

### Net Check
- **Ping**: a IP individual o a todos los dispositivos guardados
- **Traceroute**: visualizacion de la ruta con mapa de saltos y tabla detallada
- **NSLookup / DNS**: consultas A, AAAA, MX, NS, TXT, CNAME, SOA, PTR, SRV, ANY con selector de servidor DNS

### Ajustes
- Frecuencia de tests automaticos
- Frecuencia de escaneo de red
- Rango de red (CIDR)
- Retencion de historial
- Zona horaria
- Notificaciones Telegram (bot token + chat ID + test de conexion)
- Personalizacion de colores (acento, fondo, descarga, subida)
- Exportacion de datos (JSON)
- Limpieza de historial y dispositivos

---

## Instalacion (Docker)

### Docker Run

```bash
docker run -d \
  --name nettools \
  --network host \
  -v nettools-data:/data \
  -e TZ=Europe/Madrid \
  --restart unless-stopped \
  mbraut/nettools:latest
```

### Docker Compose

```yaml
services:
  nettools:
    image: mbraut/nettools:latest
    container_name: nettools
    restart: unless-stopped
    network_mode: host
    volumes:
      - nettools-data:/data
    environment:
      - TZ=Europe/Madrid

volumes:
  nettools-data:
    driver: local
```

```bash
docker compose up -d
```

Accede a **http://tu-servidor:8080**

> **Nota:** `network_mode: host` es necesario para que `arp-scan` y `nmap` puedan descubrir dispositivos en tu red local. Sin el, los tests de velocidad y herramientas de diagnostico funcionan, pero el escaneo de red no detectara dispositivos.

---

## Instalacion Manual

### Requisitos

- Python 3.10+
- Nginx
- Herramientas de red: `arp-scan`, `nmap`, `traceroute`, `dnsutils`, `iputils-ping`, `net-tools`
- (Recomendado) Ookla Speedtest CLI

### Pasos

```bash
# 1. Clonar repositorio
git clone https://github.com/Enoret/Nettools.git
cd Nettools

# 2. Instalar dependencias del sistema
sudo apt-get install -y arp-scan nmap iputils-ping net-tools traceroute dnsutils nginx

# 3. Instalar Ookla Speedtest CLI (recomendado)
# Ver: https://www.speedtest.net/apps/cli
# Si no se instala, se usa speedtest-cli (Python) como fallback

# 4. Configurar backend
sudo mkdir -p /opt/nettools
sudo cp docker/backend/*.py /opt/nettools/
sudo cp docker/backend/requirements.txt /opt/nettools/
cd /opt/nettools
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 5. Configurar frontend
sudo cp -r Nettools/nettools/* /var/www/html/

# 6. Configurar Nginx
sudo cp docker/nginx/nginx.conf /etc/nginx/sites-available/nettools
sudo ln -sf /etc/nginx/sites-available/nettools /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo systemctl restart nginx

# 7. Crear servicio systemd
sudo tee /etc/systemd/system/nettools.service > /dev/null <<EOF
[Unit]
Description=NetTools Backend
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/nettools
ExecStart=/opt/nettools/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
Environment=NETTOOLS_DB_PATH=/data/nettools.db
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo mkdir -p /data
sudo systemctl daemon-reload
sudo systemctl enable nettools
sudo systemctl start nettools
```

Accede a **http://tu-servidor:8080**

---

## Actualizacion

### Docker

```bash
docker pull mbraut/nettools:latest
docker compose down
docker compose up -d
```

### Manual

```bash
cd Nettools
git pull
cp -r nettools/* /var/www/html/
cp docker/backend/*.py /opt/nettools/
systemctl restart nettools
```

---

## Arquitectura

```
                    Puerto 8080
                        |
                    [ Nginx ]
                    /       \
            Estaticos      /api/*
           (Frontend)        |
                        [ Uvicorn ]
                        (FastAPI)
                            |
                     [ SQLite DB ]
                      /data/nettools.db
```

| Componente | Tecnologia |
|---|---|
| Frontend | HTML5, CSS3, JavaScript (Vanilla) |
| Graficos | ApexCharts |
| Iconos | Remix Icon |
| Backend | Python 3.12, FastAPI, Uvicorn |
| Base de datos | SQLite (WAL mode) |
| Speed Test | Ookla Speedtest CLI / speedtest-cli (fallback) |
| Escaneo de red | arp-scan, nmap, python-nmap |
| Notificaciones | Telegram Bot API |

---

## API

El backend expone una API REST en el puerto 8000, accesible via Nginx en `/api/`.

### Speed Test

| Metodo | Endpoint | Descripcion |
|---|---|---|
| `POST` | `/api/speedtest/run` | Ejecutar un test de velocidad |
| `GET` | `/api/speedtest/results?range=24h` | Historial de tests (1h, 6h, 24h, 7d, 30d, all) |
| `GET` | `/api/speedtest/latest` | Ultimo test |
| `GET` | `/api/speedtest/stats` | Estadisticas globales |
| `GET` | `/api/speedtest/servers` | Lista de servidores disponibles |
| `GET` | `/api/speedtest/status` | Estado del test (en curso o no) |
| `DELETE` | `/api/speedtest/results` | Eliminar todo el historial |
| `DELETE` | `/api/speedtest/results/{id}` | Eliminar un test |

### Dispositivos

| Metodo | Endpoint | Descripcion |
|---|---|---|
| `GET` | `/api/devices` | Lista de dispositivos |
| `GET` | `/api/devices/{id}` | Detalle de un dispositivo |
| `POST` | `/api/devices` | Crear dispositivo manual |
| `PUT` | `/api/devices/{id}` | Actualizar dispositivo |
| `DELETE` | `/api/devices/{id}` | Eliminar dispositivo |
| `POST` | `/api/devices/scan` | Escanear la red |
| `GET` | `/api/devices/scan/status` | Estado del escaneo |
| `GET` | `/api/devices/history?range=24h` | Historial de dispositivos |

### Herramientas

| Metodo | Endpoint | Descripcion |
|---|---|---|
| `POST` | `/api/ping` | Ping a una IP |
| `POST` | `/api/ping/batch` | Ping a multiples IPs |
| `POST` | `/api/traceroute` | Traceroute a una IP/dominio |
| `POST` | `/api/nslookup` | Consulta DNS |

### Configuracion

| Metodo | Endpoint | Descripcion |
|---|---|---|
| `GET` | `/api/settings` | Obtener configuracion |
| `PUT` | `/api/settings` | Guardar configuracion |
| `POST` | `/api/settings/telegram/test` | Probar notificacion Telegram |
| `GET` | `/api/export` | Exportar todos los datos (JSON) |
| `GET` | `/api/health` | Health check |

---

## Configuracion de Telegram

1. Crea un bot con [@BotFather](https://t.me/BotFather) en Telegram
2. Copia el **Bot Token**
3. Obtiene tu **Chat ID** (puedes usar [@userinfobot](https://t.me/userinfobot))
4. En NetTools > Ajustes > Notificaciones Telegram:
   - Activa Telegram
   - Pega el Bot Token y Chat ID
   - Pulsa "Enviar Prueba" para verificar
   - Guarda la configuracion

Recibiras una notificacion cada vez que se detecte un nuevo dispositivo en tu red.

---

## Volumen de datos

| Ruta | Contenido |
|---|---|
| `/data/nettools.db` | Base de datos SQLite con tests, dispositivos y configuracion |

Para hacer backup, simplemente copia el archivo `/data/nettools.db`.

---

## Variables de entorno

| Variable | Defecto | Descripcion |
|---|---|---|
| `NETTOOLS_DB_PATH` | `/data/nettools.db` | Ruta de la base de datos |
| `TZ` | `Europe/Madrid` | Zona horaria del contenedor |
| `PYTHONUNBUFFERED` | `1` | Logs en tiempo real |

---

## Construir la imagen

```bash
git clone https://github.com/Enoret/Nettools.git
cd Nettools

# Build
docker build -t mbraut/nettools:latest .

# Build multi-arquitectura (amd64 + arm64)
docker buildx build --platform linux/amd64,linux/arm64 -t mbraut/nettools:latest --push .
```

---

## Requisitos del sistema

| Recurso | Minimo |
|---|---|
| CPU | 1 core |
| RAM | 256 MB |
| Disco | 100 MB + base de datos |
| Red | Acceso a la LAN para escaneo |
| SO | Linux (Docker o bare metal) |

Compatible con **amd64**, **arm64** (Raspberry Pi 4/5) y **armhf**.

---

## Licencia

MIT License - ver [LICENSE](LICENSE)

---

## Creditos

Desarrollado por [bytebeat.es](https://bytebeat.es)

<p align="center">
  <sub>NetTools - Monitor de red autoalojado</sub>
</p>
