module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "20.2.0"

  cluster_name    = var.cluster_name
  cluster_version = "1.33"

  # Use the existing Default VPC and Subnets
  vpc_id                   = data.aws_vpc.default.id
  subnet_ids               = data.aws_subnets.default.ids
  control_plane_subnet_ids = data.aws_subnets.default.ids

  # Security: Allow public access to the API (required for local kubectl)
  cluster_endpoint_public_access = true

  # Grant admin permissions to the user creating the cluster
  enable_cluster_creator_admin_permissions = true

  # 4. The 1-Node Worker Group
  eks_managed_node_groups = {
    one_node = {
      min_size     = 1
      max_size     = 1
      desired_size = 1

      instance_types = ["t3.micro"]
      capacity_type  = "ON_DEMAND"

      # CRITICAL: Since Default VPC subnets are public, we must assign public IPs
      # or the nodes cannot download software/join the cluster.
      associate_public_ip_address = true
    }
  }
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