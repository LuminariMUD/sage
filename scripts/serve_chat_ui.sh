#!/bin/bash
# Serve the Luminari Sage Chat UI locally
#
# Usage: ./scripts/serve_chat_ui.sh [port]
# Default port: 8080

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
UI_DIR="$PROJECT_ROOT/ui"
PORT="${1:-8080}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🌟 Luminari Sage Chat UI Server${NC}"
echo ""

# Check if UI directory exists
if [ ! -d "$UI_DIR" ]; then
    echo -e "❌ UI directory not found: $UI_DIR"
    exit 1
fi

# Check if chat-ui.html exists
if [ ! -f "$UI_DIR/chat-ui.html" ]; then
    echo -e "❌ chat-ui.html not found in $UI_DIR"
    exit 1
fi

# Check if API is reachable
echo -e "${YELLOW}Checking API connectivity...${NC}"
if curl -s --connect-timeout 2 http://localhost:8003/ping > /dev/null 2>&1; then
    echo -e "${GREEN}✅ API is reachable at http://localhost:8003${NC}"
else
    echo -e "${YELLOW}⚠️  API not reachable at http://localhost:8003${NC}"
    echo -e "   Make sure to run: docker compose up -d"
fi

echo ""
echo -e "${GREEN}Starting UI server on port $PORT...${NC}"
echo ""
echo -e "  📎 Chat UI:  ${BLUE}http://localhost:$PORT/chat-ui.html${NC}"
echo -e "  📚 API Docs: ${BLUE}http://localhost:8003/docs${NC}"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop the server${NC}"
echo ""

# Bind to loopback by default and apply the security headers in ui/serve.py.
exec python3 "$UI_DIR/serve.py" "$PORT"
