echo "Building robot-shop images"
USE_MINIKUBE=false
AWS_REGION=${AWS_REGION:-"us-east-1"}
AWS_ACCOUNT_ID=${AWS_ACCOUNT_ID:-"189429133920"}

if [ "$USE_MINIKUBE" = "true" ]; then
  eval $(minikube -p minikube docker-env)
else
   aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
fi

folders=("cart" "catalogue" "dispatch" "load-gen" "mongo" "mysql" "payment" "ratings" "shipping" "user" "web")
REPO=${REPO:-"robotshop"}
TAG=${TAG:-"2.2.0"}

docker pull redis:6.2-alpine
docker pull rabbitmq:3.8-management-alpine

docker image tag redis:6.2-alpine ${REPO}/rs-redis:${TAG}
docker image tag rabbitmq:3.8-management-alpine ${REPO}/rs-rabbitmq:${TAG}

if [ "$USE_MINIKUBE" = "true" ]; then
  minikube image load ${REPO}/rs-redis:${TAG}
  minikube image load ${REPO}/rs-rabbitmq:${TAG}
else
  docker image tag redis:6.2-alpine ${REPO}/rs-redis:${TAG}
  docker image tag rabbitmq:3.8-management-alpine ${REPO}/rs-rabbitmq:${TAG}
fi

pushd ../services/robot-shop
   for folder in ${folders[@]}; do
      echo "Building ${folder} image"
      pushd ./${folder}
      if [ "$USE_MINIKUBE" = "true" ]; then
        minikube image build -t ${REPO}/rs-${folder}:${TAG} .
      else
        docker build -t ${REPO}/rs-${folder}:${TAG} .
      fi
      popd
   done
   pushd k8s
      echo "Deploying robot-shop"
      ./deploy.sh
   popd
popd


echo "-------------------------------------------"
echo "Run: minikube service loki-grafana -n monitoring"
echo "Access Grafana at: http://$(minikube ip):30300"
echo "-------------------------------------------"
