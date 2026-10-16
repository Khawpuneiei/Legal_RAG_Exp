variable "prefix" {
  description = "Short name prefix for resources"
  type        = string
  default     = "legalai"
}

variable "environment" {
  description = "staging or production"
  type        = string
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be staging or production"
  }
}

variable "location" {
  description = "Azure region (Singapore keeps data in-country; see README 1.7 for model availability)"
  type        = string
  default     = "southeastasia"
}

variable "vnet_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

variable "kubernetes_version" {
  type    = string
  default = "1.33"
}

variable "system_vm_size" {
  type    = string
  default = "Standard_D4ds_v5"
}

variable "apps_vm_size" {
  type    = string
  default = "Standard_D4ds_v5"
}

variable "enable_gpu_pool" {
  description = "GPU pool for self-hosted models (vLLM, bge-m3 + reranker)"
  type        = bool
  default     = false
}

variable "gpu_vm_size" {
  type    = string
  default = "Standard_NC4as_T4_v3"
}

variable "postgres_sku" {
  type    = string
  default = "GP_Standard_D2ds_v5"
}

variable "aks_admin_group_ids" {
  description = "Entra ID groups with cluster-admin through Azure RBAC"
  type        = list(string)
  default     = []
}

variable "tags" {
  type    = map(string)
  default = {}
}
