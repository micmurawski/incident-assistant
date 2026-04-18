#export.sh

params="$1"

scope="robot"
if [ "$params" = "incident-assistant" ]; then
    scope="incident-assistant"
fi

basedir="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

export ANTHROPIC_API_KEY=$(cat "$basedir/api_key.json" | jq -r '.["anthropic_api_key"]')
export GEMINI_API_KEY=$(cat "$basedir/api_key.json" | jq -r '.["gemini_api_key"]')
export MINIMAX_API_KEY=$(cat "$basedir/api_key.json" | jq -r '.["minimax_api_key"]')
export AWS_ACCESS_KEY_ID=$(cat "$basedir/api_key.json" | jq -r ".[\"$scope\"][\"access_key_id\"]")
export AWS_SECRET_ACCESS_KEY=$(cat "$basedir/api_key.json" | jq -r ".[\"$scope\"][\"secret_access_key\"]")
export GRAFANA_API_KEY=$(cat "$basedir/api_key.json" | jq -r '.["grafana_api_token"]')
export GRAFANA_URL=$(cat "$basedir/api_key.json" | jq -r '.["grafana_url"]')
export DOCKER_HOST="unix:///Users/$USER/.docker/run/docker.sock"
export GROQ_API_KEY=$(cat "$basedir/api_key.json" | jq -r '.["groq_api_key"]')
export OPENAI_API_KEY=$(cat "$basedir/api_key.json" | jq -r '.["openai_api_key"]')
export OPEN_ROUTER_API_KEY=$(cat "$basedir/api_key.json" | jq -r '.["open_router_api_key"]')
export AWS_BEARER_TOKEN_BEDROCK=$(cat "$basedir/api_key.json" | jq -r '.["aws_bearer_token_bedrock"]')
export AWS_REGION="us-east-1"
export OVH_AI_ENDPOINTS_ACCESS_TOKEN=$(cat "$basedir/api_key.json" | jq -r '.["ovh_ai_endpoint_access_token"]')
if [ "$params" = "robot" ]; then
    export AWS_PROFILE="dev"
fi
echo "The scope is $scope"


aws sts get-caller-identity