#!/bin/bash
set -e

echo "=== StockPulse Oracle Cloud Setup ==="

# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install Docker
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
    echo "Docker installed. You may need to log out and back in for group changes."
fi

# Install Docker Compose plugin
if ! docker compose version &> /dev/null; then
    echo "Installing Docker Compose plugin..."
    sudo apt-get install -y docker-compose-plugin
fi

# Open firewall port 8080
echo "Configuring firewall..."
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8080 -j ACCEPT
sudo netfilter-persistent save 2>/dev/null || true

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Clone your repo:  git clone https://github.com/abdeltaehass/stockpulse.git"
echo "  2. cd stockpulse"
echo "  3. Create .env file with your secrets (see .env.example)"
echo "  4. Run:  docker compose up -d --build"
echo "  5. Check logs:  docker compose logs -f"
echo "  6. Open port 8080 in Oracle Cloud Console > Networking > Security Lists"
echo ""
echo "Useful commands:"
echo "  docker compose logs -f          # View logs"
echo "  docker compose restart           # Restart app"
echo "  docker compose down              # Stop app"
echo "  docker compose up -d --build     # Rebuild and restart"
echo ""
