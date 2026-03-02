locals {
  environment = terraform.workspace
  default_tags = {
    "project"     = "robotshop"
    "environment" = "dev"
  }
}
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.0"

  name               = var.cluster_name
  kubernetes_version = "1.35"

  # Use the existing Default VPC and Subnets
  vpc_id                   = data.aws_vpc.default.id
  subnet_ids               = data.aws_subnets.default.ids
  control_plane_subnet_ids = data.aws_subnets.default.ids

  # Security: Allow public access to the API (required for kubectl from your laptop)
  endpoint_public_access = true

  # Grant admin permissions to the user creating the cluster
  enable_cluster_creator_admin_permissions = true

  addons = {
    coredns = {}
    eks-pod-identity-agent = {
      before_compute = true
    }
    kube-proxy = {}
    vpc-cni = {
      before_compute = true
    }
  }

  eks_managed_node_groups = {
    # Node Group for your 8 Microservices
    apps = {
      ami_type       = "AL2023_ARM_64_STANDARD"
      instance_types = ["t4g.medium"]
      min_size       = 1
      max_size       = 1
      desired_size   = 1

      labels = {
        role = "application"
      }
      associate_public_ip_address = true
    }

    # Dedicated Node Group for Observability (Prometheus/Loki/Grafana)
    bastion = {
      ami_type       = "AL2023_ARM_64_STANDARD"
      instance_types = ["t4g.medium"]
      min_size       = 1
      max_size       = 1
      desired_size   = 1

      labels = {
        role = "bastion"
      }

      # Taint prevents standard apps from accidentally landing here (list format required by EKS module)
      taints = {
        dedicated = {
          key    = "dedicated"
          value  = "bastion"
          effect = "NO_SCHEDULE"
        }
      }
      associate_public_ip_address = true
    }
  }
  access_entries = {
    robot_access = {
      principal_arn = "arn:aws:iam::189429133920:root"
      policy_associations = {
        cluster_admin = {
          policy_arn = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
          access_scope = {
            type = "cluster"
          }
        }
      }

    }
  }
  
  tags = local.default_tags
}


# ECR Repositories for Robot Shop services
resource "aws_ecr_repository" "robot_shop" {
  for_each = toset(var.robot_shop_services)

  name                 = "robot-shop-${each.key}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

# ------------------------------------------------------------------------------
# Outputs (for kubeconfig and scripts)
# ------------------------------------------------------------------------------
output "cluster_name" {
  description = "EKS cluster name; use with: aws eks update-kubeconfig --name <name> --region <region>"
  value       = var.cluster_name
}

output "cluster_region" {
  description = "AWS region of the EKS cluster"
  value       = var.region
}

