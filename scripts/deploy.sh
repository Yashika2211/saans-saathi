#!/usr/bin/env bash
# Deploy SaansSaathi to AWS: secrets -> SAM stack -> dashboard -> Telegram webhook.
#   ./scripts/deploy.sh
# Reads TELEGRAM_BOT_TOKEN and BEDROCK_MODEL_ID from .env. Never prints the token.
set -euo pipefail
cd "$(dirname "$0")/.."

STACK=saans-saathi
REGION=${AWS_REGION:-us-east-1}
PARAM=/saans/telegram-bot-token

env_value() { grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- | sed 's/ #.*//' | tr -d '"'"'"; }
TOKEN=$(env_value TELEGRAM_BOT_TOKEN)
MODEL=$(env_value BEDROCK_MODEL_ID)
PIN=$(env_value PRINCIPAL_PIN)

if [[ -n "$TOKEN" ]]; then
  echo "Storing bot token in SSM $PARAM (SecureString)"
  aws ssm put-parameter --region "$REGION" --name "$PARAM" --type SecureString --value "$TOKEN" --overwrite >/dev/null
elif ! aws ssm get-parameter --region "$REGION" --name "$PARAM" >/dev/null 2>&1; then
  echo "No TELEGRAM_BOT_TOKEN in .env and no $PARAM in SSM. Add the token to .env first." >&2
  exit 1
fi

sam build
sam deploy --region "$REGION" --parameter-overrides \
  "BedrockModelId=${MODEL:-anthropic.claude-sonnet-5-5}" "TelegramTokenParam=$PARAM" "PrincipalPin=$PIN"

out() { aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
API=$(out ApiUrl); WEB_BUCKET=$(out WebBucketName); DIST=$(out WebDistributionId); DASH=$(out DashboardUrl)

echo "Uploading dashboard"
STAGE=$(mktemp -d)
cp web/index.html web/app.js "$STAGE/"
printf 'window.SAANS_CONFIG = { apiBase: "%s" };\n' "$API" > "$STAGE/config.js"
aws s3 sync "$STAGE" "s3://$WEB_BUCKET" --delete --cache-control "max-age=60" >/dev/null
aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/*" >/dev/null
rm -rf "$STAGE"

echo "Pointing Telegram at $API/telegram"
uv run python -m saans.bot --set-webhook "$API/telegram"

echo
echo "Dashboard: $DASH"
echo "API:       $API"
echo "Run now:   curl -X POST '$API/run-now?school=demo-1&replay=2024-11-18'"
