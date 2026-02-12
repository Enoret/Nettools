#!/bin/bash
# =========================================
#  NetTools - Instalador Automatico
#  Para sistema limpio Debian 12 / Ubuntu 22+
#  Instala TODO desde cero (Apache incluido)
# =========================================

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

# Rutas
BACKEND_DIR="/opt/nettools"
DATA_DIR="/opt/nettools/data"
VENV_DIR="/opt/nettools/venv"
SERVICE_NAME="nettools"
WEBROOT="/var/www/html"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ERRORS=0

# =========================================
print_banner() {
    clear
    echo ""
    echo -e "${BLUE}${BOLD}"
    echo "  ╔═══════════════════════════════════════╗"
    echo "  ║        NetTools  Installer            ║"
    echo "  ║    Monitor de Red & Speed Test        ║"
    echo "  ║                                       ║"
    echo "  ║    Debian 12 / Ubuntu 22+  (limpio)   ║"
    echo "  ╚═══════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""
}

log_info()    { echo -e "  ${BLUE}[INFO]${NC}    $1"; }
log_ok()      { echo -e "  ${GREEN}[  OK  ]${NC}  $1"; }
log_warn()    { echo -e "  ${YELLOW}[ WARN ]${NC}  $1"; }
log_error()   { echo -e "  ${RED}[ERROR]${NC}   $1"; ERRORS=$((ERRORS+1)); }
log_step()    { echo -e "\n${CYAN}${BOLD}▶ $1${NC}"; }

# =========================================
check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "Este script debe ejecutarse como root"
        echo -e "  Ejecuta: ${BOLD}sudo bash install.sh${NC}"
        exit 1
    fi
}

check_source_files() {
    log_step "Verificando archivos del proyecto..."

    if [ ! -d "${SCRIPT_DIR}/docker/backend" ]; then
        log_error "No se encontro: docker/backend/"
        echo -e "  Asegurate de tener la estructura completa del proyecto"
        exit 1
    fi

    if [ ! -d "${SCRIPT_DIR}/nettools" ]; then
        log_error "No se encontro: nettools/"
        exit 1
    fi

    if [ ! -f "${SCRIPT_DIR}/docker/backend/main.py" ]; then
        log_error "No se encontro: docker/backend/main.py"
        exit 1
    fi

    if [ ! -f "${SCRIPT_DIR}/docker/backend/requirements.txt" ]; then
        log_error "No se encontro: docker/backend/requirements.txt"
        exit 1
    fi

    if [ ! -f "${SCRIPT_DIR}/nettools/index.html" ]; then
        log_error "No se encontro: nettools/index.html"
        exit 1
    fi

    log_ok "Todos los archivos del proyecto encontrados"
}

detect_os() {
    log_step "Detectando sistema operativo..."

    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS_NAME="$NAME"
        OS_VERSION="$VERSION_ID"
        OS_ID="$ID"
        log_ok "${OS_NAME} ${OS_VERSION}"
    else
        OS_ID="unknown"
        log_warn "No se pudo detectar el SO, continuando igualmente..."
    fi
}

# =========================================
install_system_deps() {
    log_step "Actualizando sistema e instalando dependencias..."

    # Limpiar posibles problemas previos de dpkg
    log_info "Reparando posibles paquetes rotos..."
    dpkg --configure -a 2>/dev/null || true
    apt-get -f install -y 2>/dev/null || true

    # Actualizar repositorios
    log_info "Actualizando repositorios..."
    if apt-get update -y 2>&1 | tail -1; then
        log_ok "Repositorios actualizados"
    else
        log_error "Fallo al actualizar repositorios"
        return 1
    fi

    # Paquetes base
    log_info "Instalando paquetes base..."
    apt-get install -y \
        python3 \
        python3-pip \
        python3-venv \
        curl \
        wget \
        2>&1 | tail -3
    log_ok "Python3, pip, venv, curl, wget"

    # Apache
    log_info "Instalando Apache..."
    apt-get install -y apache2 2>&1 | tail -3
    log_ok "Apache2"

    # Herramientas de red
    log_info "Instalando herramientas de red..."
    apt-get install -y \
        arp-scan \
        nmap \
        iputils-ping \
        net-tools \
        traceroute \
        dnsutils \
        2>&1 | tail -3
    log_ok "arp-scan, nmap, ping, net-tools, traceroute, dnsutils"

    # Official Ookla Speedtest CLI
    log_info "Instalando official Ookla Speedtest CLI..."
    OOKLA_INSTALLED=false

    # Method 1: Try Ookla apt repository
    curl -s https://packagecloud.io/install/repositories/ookla/speedtest-cli/script.deb.sh | bash 2>&1 | tail -1 || {
        log_warn "Failed to add Ookla repository"
    }
    apt-get install -y speedtest 2>&1 | tail -1 && OOKLA_INSTALLED=true || {
        log_warn "Ookla package not available via apt, trying direct download..."
    }

    # Method 2: Direct download from Ookla CDN (for distros where the apt repo doesn't work)
    if [ "$OOKLA_INSTALLED" = false ]; then
        log_info "Descargando Ookla Speedtest CLI directamente..."
        ARCH=$(dpkg --print-architecture 2>/dev/null || echo "amd64")
        case "$ARCH" in
            amd64)  OOKLA_ARCH="x86_64" ;;
            arm64)  OOKLA_ARCH="aarch64" ;;
            armhf)  OOKLA_ARCH="armhf" ;;
            i386)   OOKLA_ARCH="i386" ;;
            *)      OOKLA_ARCH="x86_64" ;;
        esac

        OOKLA_URL="https://install.speedtest.net/app/cli/ookla-speedtest-1.2.0-linux-${OOKLA_ARCH}.tgz"
        OOKLA_TMP="/tmp/ookla-speedtest.tgz"

        if curl -sL "$OOKLA_URL" -o "$OOKLA_TMP" 2>/dev/null; then
            tar xzf "$OOKLA_TMP" -C /tmp/ 2>/dev/null
            if [ -f /tmp/speedtest ]; then
                # Rename Python speedtest-cli alias if it exists at /usr/bin/speedtest
                if [ -f /usr/bin/speedtest ] && /usr/bin/speedtest --version 2>&1 | grep -qi "speedtest-cli"; then
                    mv /usr/bin/speedtest /usr/bin/speedtest-cli-python 2>/dev/null || true
                fi
                cp /tmp/speedtest /usr/local/bin/speedtest
                chmod +x /usr/local/bin/speedtest
                OOKLA_INSTALLED=true
                log_ok "Ookla Speedtest CLI instalado via descarga directa"
            else
                log_warn "No se pudo extraer el binario de Ookla"
            fi
            rm -f "$OOKLA_TMP" /tmp/speedtest /tmp/speedtest.md /tmp/speedtest.5 2>/dev/null
        else
            log_warn "No se pudo descargar Ookla Speedtest CLI"
        fi
    fi

    if [ "$OOKLA_INSTALLED" = true ]; then
        # Verify it's really the Ookla binary
        if speedtest --version 2>&1 | grep -qi "ookla"; then
            log_ok "Official Ookla Speedtest CLI verificado"
        else
            log_warn "speedtest binary found but may not be official Ookla"
        fi
    else
        log_warn "Official Ookla Speedtest CLI installation failed - using Python fallback"
    fi

    # Fallback: Python speedtest-cli (always install as backup)
    log_info "Instalando speedtest-cli (Python) como fallback..."
    apt-get install -y speedtest-cli 2>&1 | tail -1 || {
        log_warn "speedtest-cli no disponible en repos, instalando via pip..."
        pip3 install speedtest-cli --break-system-packages 2>/dev/null || pip3 install speedtest-cli
    }
    log_ok "speedtest-cli (fallback)"

    # Activar modulos proxy de Apache
    a2enmod proxy proxy_http 2>&1 | tail -1
    log_ok "Modulos proxy de Apache activados"
}

# =========================================
install_backend() {
    log_step "Instalando backend en ${BACKEND_DIR}..."

    # Crear directorios
    mkdir -p "$BACKEND_DIR" "$DATA_DIR"

    # Copiar archivos del backend
    cp "${SCRIPT_DIR}/docker/backend/"*.py "$BACKEND_DIR/"
    cp "${SCRIPT_DIR}/docker/backend/requirements.txt" "$BACKEND_DIR/"
    log_ok "Archivos del backend copiados"

    # Crear entorno virtual
    log_info "Creando entorno virtual de Python..."
    if [ -d "$VENV_DIR" ]; then
        rm -rf "$VENV_DIR"
    fi
    python3 -m venv "$VENV_DIR"
    log_ok "Entorno virtual creado"

    # Instalar dependencias Python
    log_info "Instalando dependencias Python (puede tardar 1-2 min)..."
    "$VENV_DIR/bin/pip" install --upgrade pip 2>&1 | tail -1
    "$VENV_DIR/bin/pip" install -r "$BACKEND_DIR/requirements.txt" 2>&1 | tail -3
    log_ok "Dependencias Python instaladas"
}

# =========================================
install_frontend() {
    log_step "Instalando frontend en ${WEBROOT}..."

    # Crear webroot si no existe
    mkdir -p "$WEBROOT"

    # Limpiar contenido previo de nettools (no borrar todo por si hay otras cosas)
    for item in index.html css js assets; do
        rm -rf "${WEBROOT:?}/${item}" 2>/dev/null || true
    done

    # Copiar frontend
    cp -r "${SCRIPT_DIR}/nettools/"* "$WEBROOT/"
    chown -R www-data:www-data "$WEBROOT/"
    log_ok "Frontend desplegado en ${WEBROOT}"
}

# =========================================
create_service() {
    log_step "Creando servicio systemd..."

    # Parar servicio si existe
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true

    cat > "/etc/systemd/system/${SERVICE_NAME}.service" << 'SERVICEEOF'
[Unit]
Description=NetTools Backend API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/nettools
Environment=NETTOOLS_DB_PATH=/opt/nettools/data/nettools.db
ExecStart=/opt/nettools/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICEEOF

    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME" 2>&1 | tail -1
    systemctl start "$SERVICE_NAME"
    log_ok "Servicio ${SERVICE_NAME} creado"

    # Esperar a que arranque
    log_info "Esperando a que el backend arranque..."
    sleep 3

    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log_ok "Backend corriendo correctamente"
    else
        log_error "El backend no arranco"
        echo ""
        echo -e "  ${YELLOW}Logs del error:${NC}"
        journalctl -u "$SERVICE_NAME" -n 15 --no-pager
        echo ""
    fi
}

# =========================================
configure_apache() {
    log_step "Configurando Apache..."

    APACHE_CONF="/etc/apache2/sites-available/000-default.conf"

    # Crear configuracion limpia
    cat > "$APACHE_CONF" << 'APACHEEOF'
<VirtualHost *:80>
    ServerAdmin webmaster@localhost
    DocumentRoot /var/www/html

    # === NetTools API Proxy ===
    ProxyPreserveHost On
    ProxyPass /api/ http://127.0.0.1:8000/api/
    ProxyPassReverse /api/ http://127.0.0.1:8000/api/
    ProxyTimeout 180

    <Directory /var/www/html>
        Options -Indexes +FollowSymLinks
        AllowOverride All
        Require all granted
    </Directory>

    ErrorLog ${APACHE_LOG_DIR}/error.log
    CustomLog ${APACHE_LOG_DIR}/access.log combined
</VirtualHost>
APACHEEOF

    # Activar site y reiniciar
    a2ensite 000-default 2>&1 | tail -1
    systemctl restart apache2
    log_ok "Apache configurado y reiniciado"
}

# =========================================
verify_installation() {
    log_step "Verificando instalacion..."

    sleep 2

    # Backend API
    if curl -sf http://127.0.0.1:8000/api/health | grep -q '"status":"ok"'; then
        log_ok "Backend API respondiendo (puerto 8000)"
    else
        log_error "Backend no responde en puerto 8000"
    fi

    # Apache
    if systemctl is-active --quiet apache2; then
        log_ok "Apache corriendo"
    else
        log_error "Apache no esta corriendo"
    fi

    # Frontend
    if [ -f "${WEBROOT}/index.html" ]; then
        log_ok "Frontend en ${WEBROOT}"
    else
        log_error "Frontend no encontrado"
    fi

    # Proxy completo
    if curl -sf http://127.0.0.1/api/health | grep -q '"status":"ok"'; then
        log_ok "Proxy Apache -> Backend OK"
    else
        log_warn "Proxy Apache -> Backend no verificado"
    fi

    # Official Ookla Speedtest CLI (preferred)
    if command -v speedtest &> /dev/null && speedtest --version 2>&1 | grep -qi "ookla"; then
        log_ok "Official Ookla Speedtest CLI disponible"
    else
        log_warn "Official Ookla Speedtest CLI no encontrado, checking fallback..."
        # Fallback: speedtest-cli (Python)
        if command -v speedtest-cli &> /dev/null || command -v speedtest &> /dev/null || [ -f "$VENV_DIR/bin/speedtest-cli" ]; then
            log_ok "speedtest-cli (Python fallback) disponible"
        else
            log_error "Ningun speedtest encontrado"
        fi
    fi

    # arp-scan
    if command -v arp-scan &> /dev/null; then
        log_ok "arp-scan disponible"
    else
        log_warn "arp-scan no encontrado"
    fi

    # nmap
    if command -v nmap &> /dev/null; then
        log_ok "nmap disponible"
    else
        log_warn "nmap no encontrado"
    fi
}

# =========================================
print_summary() {
    SERVER_IP=$(hostname -I | awk '{print $1}')

    echo ""
    if [ $ERRORS -eq 0 ]; then
        echo -e "${GREEN}${BOLD}"
        echo "  ╔═══════════════════════════════════════╗"
        echo "  ║     Instalacion completada!           ║"
        echo "  ╚═══════════════════════════════════════╝"
        echo -e "${NC}"
    else
        echo -e "${YELLOW}${BOLD}"
        echo "  ╔═══════════════════════════════════════╗"
        echo "  ║  Instalacion con ${ERRORS} advertencia(s)     ║"
        echo "  ╚═══════════════════════════════════════╝"
        echo -e "${NC}"
    fi

    echo ""
    echo -e "  ${BOLD}Accede a NetTools:${NC}"
    echo -e "    Local:   ${CYAN}http://localhost${NC}"
    echo -e "    Red:     ${CYAN}http://${SERVER_IP}${NC}"
    echo ""
    echo -e "  ${BOLD}Comandos utiles:${NC}"
    echo -e "    Estado backend:    ${CYAN}systemctl status nettools${NC}"
    echo -e "    Logs en vivo:      ${CYAN}journalctl -u nettools -f${NC}"
    echo -e "    Reiniciar backend: ${CYAN}systemctl restart nettools${NC}"
    echo -e "    Reiniciar Apache:  ${CYAN}systemctl restart apache2${NC}"
    echo ""
    echo -e "  ${BOLD}Archivos:${NC}"
    echo -e "    Frontend:    ${WEBROOT}/"
    echo -e "    Backend:     ${BACKEND_DIR}/"
    echo -e "    Base datos:  ${DATA_DIR}/nettools.db"
    echo -e "    Servicio:    /etc/systemd/system/${SERVICE_NAME}.service"
    echo ""
}

# =========================================
#  MAIN
# =========================================
print_banner
check_root
check_source_files
detect_os
install_system_deps
install_backend
install_frontend
create_service
configure_apache
verify_installation
print_summary
