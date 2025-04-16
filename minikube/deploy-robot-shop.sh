echo "Building robot-shop images"
pushd ../services/robot-shop
 eval $(minikube docker-env)
 docker-compose -f docker-compose.yaml build
 pushd k8s
    ./deploy.sh
 popd
popd