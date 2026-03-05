basedir="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
export ANTHROPIC_API_KEY=$(cat $basedir/api_key.json | jq -r '.["anthropic_api_key"]')
export GEMINI_API_KEY=$(cat $basedir/api_key.json | jq -r '.["gemini_api_key"]')
export MINIMAX_API_KEY=$(cat $basedir/api_key.json | jq -r '.["minimax_api_key"]')
export AWS_ACCESS_KEY_ID=$(cat $basedir/api_key.json | jq -r '.["aws"]["access_key_id"]')
export AWS_SECRET_ACCESS_KEY=$(cat $basedir/api_key.json | jq -r '.["aws"]["secret_access_key"]')
export AWS_REGION="us-east-1"
export AWS_PROFILE="dev"