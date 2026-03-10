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
export GRAFANA_API_KEY=$(cat "$basedir/api_key.json" | jq -r '.["grafana_api_key"]')
export GRAFANA_URL=$(cat "$basedir/api_key.json" | jq -r '.["grafana_url"]')
export AWS_REGION="us-east-1"
if [ "$params" = "robot" ]; then
    export AWS_PROFILE="dev"
fi
echo "The scope is $scope"


aws sts get-caller-identity