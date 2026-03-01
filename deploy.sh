#!/usr/bin/env bash
# ============================================================
# ReadPaper - One-Click Deployment Script
# ============================================================
# Usage:
#   ./deploy.sh              # Start services (HTTP mode)
#   ./deploy.sh setup-ssl    # Setup SSL with Let's Encrypt
#   ./deploy.sh stop         # Stop all services
#   ./deploy.sh logs         # View logs
#   ./deploy.sh status       # Check service status
#   ./deploy.sh update       # Pull latest & rebuild
# ============================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Pre-flight checks ──────────────────────────────────────────
check_prerequisites() {
    log_info "Checking prerequisites..."

    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        echo "  Visit: https://docs.docker.com/get-docker/"
        exit 1
    fi

    if ! docker compose version &> /dev/null; then
        log_error "Docker Compose V2 is not available."
        echo "  Docker Compose is included with Docker Desktop, or install the plugin:"
        echo "  https://docs.docker.com/compose/install/"
        exit 1
    fi

    if ! docker info &> /dev/null 2>&1; then
        log_error "Docker daemon is not running. Please start Docker."
        exit 1
    fi

    log_ok "All prerequisites met."
}

# ── Environment setup ──────────────────────────────────────────
setup_env() {
    if [ ! -f .env ]; then
        log_warn ".env file not found. Creating from template..."
        cp .env.example .env
        log_warn "Please edit .env and fill in your API keys:"
        echo ""
        echo "  Required:"
        echo "    GEMINI_API_KEY     - Get from https://aistudio.google.com/"
        echo ""
        echo "  Optional (for Google Login):"
        echo "    AUTH_GOOGLE_ID     - Google OAuth Client ID"
        echo "    AUTH_GOOGLE_SECRET - Google OAuth Client Secret"
        echo "    NEXTAUTH_SECRET    - Run: openssl rand -base64 32"
        echo ""
        echo "  Edit the file:  nano .env"
        echo "  Then re-run:    ./deploy.sh"
        exit 1
    fi

    # Validate essential env vars
    source .env
    if [ "${GEMINI_API_KEY:-}" = "your_gemini_api_key_here" ] || [ -z "${GEMINI_API_KEY:-}" ]; then
        log_error "GEMINI_API_KEY is not set in .env"
        echo "  Get your key from: https://aistudio.google.com/"
        exit 1
    fi

    log_ok "Environment configuration loaded."
}

# ── Start services (HTTP) ──────────────────────────────────────
start() {
    check_prerequisites
    setup_env

    log_info "Building and starting ReadPaper services..."
    docker compose up -d --build

    echo ""
    log_ok "ReadPaper is starting up!"
    echo ""
    echo "  Local access:    http://localhost"
    echo "  Service status:  ./deploy.sh status"
    echo "  View logs:       ./deploy.sh logs"
    echo ""

    if [ "${DOMAIN:-}" ] && [ "$DOMAIN" != "yourdomain.com" ]; then
        echo "  For HTTPS setup: ./deploy.sh setup-ssl"
    fi
}

# ── Setup SSL with Let's Encrypt ───────────────────────────────
setup_ssl() {
    check_prerequisites
    setup_env

    source .env
    if [ -z "${DOMAIN:-}" ] || [ "$DOMAIN" = "yourdomain.com" ]; then
        log_error "Please set DOMAIN in .env to your actual domain name."
        echo "  Example: DOMAIN=readpaper.example.com"
        exit 1
    fi

    if [ -z "${SSL_EMAIL:-}" ]; then
        log_error "Please set SSL_EMAIL in .env for Let's Encrypt notifications."
        echo "  Example: SSL_EMAIL=you@example.com"
        exit 1
    fi

    log_info "Setting up SSL for domain: $DOMAIN"

    # First, start services in HTTP mode so certbot can verify
    docker compose up -d --build

    # Wait for nginx to be ready
    log_info "Waiting for nginx to start..."
    sleep 5

    # Request certificate
    log_info "Requesting Let's Encrypt certificate..."
    docker compose run --rm certbot certonly \
        --webroot \
        --webroot-path=/var/www/certbot \
        --email "$SSL_EMAIL" \
        --agree-tos \
        --no-eff-email \
        -d "$DOMAIN"

    # Stop HTTP nginx, start SSL nginx
    docker compose stop nginx
    docker compose --profile ssl up -d nginx-ssl

    echo ""
    log_ok "SSL is configured! Your site is live at: https://$DOMAIN"
    echo ""
    echo "  Certificate auto-renewal: add this cron job"
    echo "  0 12 * * * cd $SCRIPT_DIR && docker compose run --rm certbot renew && docker compose --profile ssl exec nginx-ssl nginx -s reload"
}

# ── Stop services ──────────────────────────────────────────────
stop() {
    log_info "Stopping ReadPaper services..."
    docker compose --profile ssl down
    log_ok "All services stopped."
}

# ── View logs ──────────────────────────────────────────────────
logs() {
    docker compose logs -f --tail=100
}

# ── Service status ─────────────────────────────────────────────
status() {
    echo ""
    log_info "Service Status:"
    echo ""
    docker compose ps
    echo ""

    # Check health
    if curl -s -o /dev/null -w "%{http_code}" http://localhost/nginx-health 2>/dev/null | grep -q "200"; then
        log_ok "Nginx:    healthy"
    else
        log_warn "Nginx:    not responding"
    fi

    if docker compose exec -T backend curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/health 2>/dev/null | grep -q "200"; then
        log_ok "Backend:  healthy"
    else
        log_warn "Backend:  not responding (may still be starting)"
    fi

    if docker compose exec -T frontend curl -s -o /dev/null -w "%{http_code}" http://localhost:8080 2>/dev/null | grep -q "200"; then
        log_ok "Frontend: healthy"
    else
        log_warn "Frontend: not responding (may still be starting)"
    fi
}

# ── Update & rebuild ──────────────────────────────────────────
update() {
    log_info "Pulling latest changes..."
    git pull

    log_info "Rebuilding services..."
    docker compose up -d --build

    log_ok "Update complete!"
}

# ── Main ───────────────────────────────────────────────────────
case "${1:-start}" in
    start)     start ;;
    stop)      stop ;;
    logs)      logs ;;
    status)    status ;;
    update)    update ;;
    setup-ssl) setup_ssl ;;
    *)
        echo "Usage: $0 {start|stop|logs|status|update|setup-ssl}"
        exit 1
        ;;
esac
