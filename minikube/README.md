# Minikube - Robot Shop

A microservices-based robot shop application deployed on Minikube. This project demonstrates a complete e-commerce application built with multiple services running in a Kubernetes environment. Application was forked in https://github.com/micmurawski/robot-shop


## Overview

The Robot Shop is a sample microservice application that consists of several components working together to provide a complete e-commerce experience. It's designed to showcase containerized application orchestration and monitoring techniques.

### Technology Stack

- **Backend Services:**
  - MongoDB (Database)
  - Redis (Caching)
  - RabbitMQ (Message Queue)
  - MySQL (Database)
  
- **Application Services:**
  - Web Frontend
  - Catalogue Service
  - Cart Service
  - User Service
  - Payment Service
  - Shipping Service
  - Ratings Service
  - Dispatch Service

## Prerequisites

- Minikube
- kubectl
- Docker
- Helm (optional)

## Deployment and installation

1. Pull git modules containing robot-shop repository

```bash
git submodule update --init --recursive
```

2. Start Minikube:
```bash
./deploy-all.sh
```

3. Create a tunnel to access the application:
```bash
sudo minikube tunnel
```

4. Access the Robot Shop web interface:
```bash
http://localhost:8080
```

## Load Testing

The application includes a load testing utility to simulate user traffic:

1. Run the load generator:
```bash
docker-compose -f docker-compose-load.yaml up -d
```

Load test configuration can be customized using environment variables:
- `HOST`: Target host URL
- `NUM_CLIENTS`: Number of simultaneous clients
- `RUN_TIME`: Duration of the test
- `ERROR`: Enable error simulation
- `SILENT`: Suppress verbose output

## Architecture

The application is built using a microservices architecture where each component runs in its own container:

- **Web Frontend**: Serves the user interface
- **Catalogue Service**: Manages product information
- **Cart Service**: Handles shopping cart operations
- **User Service**: Manages user accounts and authentication
- **Payment Service**: Processes payments
- **Shipping Service**: Handles shipping calculations and management
- **Ratings Service**: Manages product ratings
- **Dispatch Service**: Handles order dispatch

## Resource Requirements

Each service has defined resource limits and requests:
- Memory requests: 64Mi - 256Mi
- CPU requests: 100m - 200m
- Memory limits: 128Mi - 512Mi
- CPU limits: 200m - 500m

## Monitoring

The application includes built-in monitoring capabilities:
- Health check endpoints for each service
- Prometheus metrics endpoints for cart and payment services
- Readiness and liveness probes for Kubernetes health monitoring

