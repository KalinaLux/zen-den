#!/bin/bash
set -e

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
SKILLS_DIR="$HERMES_HOME/skills/paid-search"
STATE_DIR="$HERMES_HOME/state"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "============================================"
echo "  Marketing Autopilot — Hermes Installer"
echo "============================================"
echo ""

# Check for Hermes
if ! command -v hermes &> /dev/null; then
    echo "WARNING: 'hermes' command not found in PATH."
    echo "If Hermes is installed elsewhere, the skills will still be copied."
    echo "Install Hermes: https://hermes-agent.nousresearch.com/docs/getting-started"
    echo ""
fi

echo "Installing to: $SKILLS_DIR"
echo ""

# Create directories
mkdir -p "$SKILLS_DIR" "$STATE_DIR"

# Install skills
SKILLS=(
    campaign-status
    promo-checker
    slack-triage
    daily-digest
    slack-faq-responder
    thread-summarizer
    email-draft-responder
)

echo "Installing ${#SKILLS[@]} skills..."
for skill in "${SKILLS[@]}"; do
    if [ -d "$SKILLS_DIR/$skill" ]; then
        echo "  ↻ Updating: $skill"
        rm -rf "$SKILLS_DIR/$skill"
    else
        echo "  + Installing: $skill"
    fi
    cp -r "$SCRIPT_DIR/skills/$skill" "$SKILLS_DIR/$skill"
done
echo ""

# Install config
echo "Installing config..."
CONFIG_DEST="$SKILLS_DIR/_config"
mkdir -p "$CONFIG_DEST"
cp "$SCRIPT_DIR/config/"* "$CONFIG_DEST/"

# Symlink config into each skill that needs it
for skill in "${SKILLS[@]}"; do
    ln -sf "$CONFIG_DEST" "$SKILLS_DIR/$skill/config" 2>/dev/null || true
done
echo ""

# Install Python dependencies for campaign scripts
echo "Installing Python dependencies..."
if command -v pip3 &> /dev/null; then
    pip3 install google-ads --quiet 2>/dev/null && echo "  ✓ google-ads installed" || echo "  ⚠ Could not install google-ads. Run manually: pip3 install google-ads"
else
    echo "  ⚠ pip3 not found. Install google-ads manually: pip3 install google-ads"
fi
echo ""

# Make scripts executable
find "$SKILLS_DIR" -name "*.py" -exec chmod +x {} \;

echo "============================================"
echo "  Installation complete!"
echo "============================================"
echo ""
echo "NEXT STEPS:"
echo ""
echo "1. Set up Google Ads API access (for campaign status checks):"
echo "   - Create a service account: https://console.cloud.google.com"
echo "   - Download the JSON key file"
echo "   - Set environment variables:"
echo "     export GOOGLE_ADS_DEVELOPER_TOKEN='your-dev-token'"
echo "     export GOOGLE_ADS_JSON_KEY_PATH='/path/to/service-account.json'"
echo "     export GOOGLE_ADS_LOGIN_CUSTOMER_ID='your-mcc-id'"
echo ""
echo "2. Configure your client accounts:"
echo "   open $CONFIG_DEST/client-accounts.json"
echo ""
echo "3. Set up access control (who can query what):"
echo "   open $CONFIG_DEST/access-control.json"
echo ""
echo "4. Add your VIP senders:"
echo "   open $CONFIG_DEST/vip-senders.txt"
echo ""
echo "5. Customize FAQ answers for your team:"
echo "   open $CONFIG_DEST/faq-answers.json"
echo ""
echo "6. Configure Slack integration (if not done):"
echo "   hermes integrations slack"
echo ""
echo "7. Set your LLM provider (ChatGPT):"
echo "   hermes config set llm.provider openai"
echo "   hermes config set llm.api_key sk-..."
echo "   hermes config set llm.model gpt-4o"
echo ""
echo "8. Restart Hermes:"
echo "   hermes restart"
echo ""
echo "9. Test it:"
echo "   hermes chat 'Is the Example Client A campaign enabled?'"
echo ""
echo "Read PRIVACY.md for details on how client data is handled."
echo ""
