variable "robot_shop_services" {
  type = list(string)
  default = [
    "cart",
    "catalogue",
    "dispatch",
    "load-gen",
    "mongo",
    "mysql",
    "payment",
    "ratings",
    "shipping",
    "user",
    "web"
  ]
}

variable "cluster_name" {
  type    = string
  default = "1-node-default-vpc"
}

variable "region" {
  type    = string
  default = "us-east-1"
}