locals {
  environment = terraform.workspace
  default_tags = {
    "project"     = "robotshop"
    "environment" = "dev"
  }
  ebs_csi_role_name = "${var.cluster_name}-ebs-csi-role"
  ebs_csi_role_arn  = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${local.ebs_csi_role_name}"
}


module "ebs_csi_irsa_role" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name             = local.ebs_csi_role_name
  attach_ebs_csi_policy = true

  oidc_providers = {
    ex = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:ebs-csi-controller-sa"]
    }
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

  # Cluster admin is granted via access_entries (robot_access). Disable automatic
  # cluster-creator entry to avoid 409 when the Terraform runner is the same principal.
  enable_cluster_creator_admin_permissions = false

  addons = {
    coredns = {}
    eks-pod-identity-agent = {
      before_compute = true
    }
    kube-proxy = {}
    vpc-cni = {
      before_compute = true
      most_recent    = true               # To ensure access to the latest settings provided
      configuration_values = jsonencode({ # This increases number of pods that can be scheduled on the node
        env = {
          ENABLE_PREFIX_DELEGATION = "true"
          WARM_PREFIX_TARGET       = "1"
        }
      })
    }
    aws-ebs-csi-driver = {
      most_recent              = true
      service_account_role_arn = local.ebs_csi_role_arn
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

      iam_role_additional_policies = {
        AmazonEBSCSIDriverPolicy = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
      }
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

      iam_role_additional_policies = {
        AmazonEBSCSIDriverPolicy = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
      }
    }
  }
  access_entries = {
    robot_access = {
      principal_arn = data.aws_iam_user.robot.arn
      policy_associations = {
        cluster_admin = {
          policy_arn = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
          access_scope = {
            type = "cluster"
          }
        }
      }
    }

    # Incident assistant: namespace-scoped edit in application + cluster-scoped view (e.g. list nodes)
    incident_assistant = {
      principal_arn = data.aws_iam_user.incident-assistant.arn
      policy_associations = {
        namespace_edit = {
          policy_arn = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSEditPolicy"
          access_scope = {
            type       = "namespace"
            namespaces = ["application"]
          }
        }
        cluster_view = {
          policy_arn = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy"
          access_scope = {
            type = "cluster"
          }
        }
      }
    }
  }

  tags = local.default_tags
}


# Grant incident-assistant read/write access to ECR
resource "aws_iam_user_policy_attachment" "incident_assistant_ecr_poweruser" {
  user       = data.aws_iam_user.incident-assistant.user_name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser"
}


# ECR Repositories for Robot Shop services
#resource "aws_ecr_repository" "robot_shop" {
#  for_each = toset(var.robot_shop_services)
#
#  name                 = "robot-shop-${each.key}"
#  image_tag_mutability = "MUTABLE"
#
#  image_scanning_configuration {
#    scan_on_push = true
#  }
#  encryption_configuration {
#    encryption_type = "AES256"
#  }
#
#  #lifecycle {
#  #  prevent_destroy = true
#  #}
#}

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

