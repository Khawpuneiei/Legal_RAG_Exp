# Production platform on Azure, Singapore (southeastasia): network, AKS, PostgreSQL Flexible Server with pgvector,
# Key Vault, immutable audit storage, monitoring. Application resources are deployed by the Helm chart.
#   terraform init && terraform plan -var-file=prod.tfvars
terraform {
  required_version = ">= 1.6"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 4.0" }
    random  = { source = "hashicorp/random", version = "~> 3.6" }
  }
  # Remote state with locking (create once, outside this configuration).
  backend "azurerm" {}
}

provider "azurerm" {
  features {
    key_vault { purge_soft_delete_on_destroy = false }
  }
}

data "azurerm_client_config" "current" {}

locals {
  name = "${var.prefix}-${var.environment}"
  tags = merge(var.tags, { system = "legal-agreement-ai", environment = var.environment, data_classification = "confidential" })
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${local.name}"
  location = var.location
  tags     = local.tags
}

# ------------------------------------------------------------------------------------------------ network
resource "azurerm_virtual_network" "main" {
  name                = "vnet-${local.name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  address_space       = [var.vnet_cidr]
  tags                = local.tags
}

resource "azurerm_subnet" "aks" {
  name                 = "snet-aks"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [cidrsubnet(var.vnet_cidr, 4, 0)]
}

resource "azurerm_subnet" "postgres" {
  name                 = "snet-postgres"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [cidrsubnet(var.vnet_cidr, 8, 32)]
  delegation {
    name = "postgres"
    service_delegation {
      name    = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_subnet" "endpoints" {
  name                 = "snet-endpoints"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [cidrsubnet(var.vnet_cidr, 8, 33)]
}

resource "azurerm_private_dns_zone" "postgres" {
  name                = "${local.name}.private.postgres.database.azure.com"
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "postgres" {
  name                  = "postgres-link"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.postgres.name
  virtual_network_id    = azurerm_virtual_network.main.id
}

# ------------------------------------------------------------------------------------------------ monitoring
resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${local.name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 365
  tags                = local.tags
}

# ------------------------------------------------------------------------------------------------ AKS
resource "azurerm_kubernetes_cluster" "main" {
  name                      = "aks-${local.name}"
  location                  = azurerm_resource_group.main.location
  resource_group_name       = azurerm_resource_group.main.name
  dns_prefix                = local.name
  kubernetes_version        = var.kubernetes_version
  sku_tier                  = "Standard"
  private_cluster_enabled   = true
  oidc_issuer_enabled       = true
  workload_identity_enabled = true
  azure_policy_enabled      = true
  local_account_disabled    = true

  default_node_pool {
    name                         = "system"
    vm_size                      = var.system_vm_size
    vnet_subnet_id               = azurerm_subnet.aks.id
    auto_scaling_enabled         = true
    min_count                    = 2
    max_count                    = 4
    zones                        = ["1", "2", "3"]
    only_critical_addons_enabled = true
    upgrade_settings { max_surge = "33%" }
  }

  identity { type = "SystemAssigned" }

  azure_active_directory_role_based_access_control {
    azure_rbac_enabled     = true
    admin_group_object_ids = var.aks_admin_group_ids
  }

  network_profile {
    network_plugin      = "azure"
    network_plugin_mode = "overlay"
    network_policy      = "cilium"
    network_data_plane  = "cilium"
    outbound_type       = "loadBalancer"
  }

  oms_agent { log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id }
  key_vault_secrets_provider { secret_rotation_enabled = true }
  tags = local.tags
}

resource "azurerm_kubernetes_cluster_node_pool" "apps" {
  name                  = "apps"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.main.id
  vm_size               = var.apps_vm_size
  vnet_subnet_id        = azurerm_subnet.aks.id
  auto_scaling_enabled  = true
  min_count             = 2
  max_count             = 8
  zones                 = ["1", "2", "3"]
  tags                  = local.tags
}

# Optional GPU pool for the self-hosted model profile (vLLM / bge-m3 + reranker). Off by default.
resource "azurerm_kubernetes_cluster_node_pool" "gpu" {
  count                 = var.enable_gpu_pool ? 1 : 0
  name                  = "gpu"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.main.id
  vm_size               = var.gpu_vm_size
  vnet_subnet_id        = azurerm_subnet.aks.id
  auto_scaling_enabled  = true
  min_count             = 0
  max_count             = 2
  node_taints           = ["sku=gpu:NoSchedule"]
  tags                  = local.tags
}

# ------------------------------------------------------------------------------------------------ PostgreSQL
resource "random_password" "pg_admin" {
  length  = 32
  special = false
}

resource "azurerm_postgresql_flexible_server" "main" {
  name                          = "psql-${local.name}"
  resource_group_name           = azurerm_resource_group.main.name
  location                      = azurerm_resource_group.main.location
  version                       = "16"
  sku_name                      = var.postgres_sku
  storage_mb                    = 65536
  auto_grow_enabled             = true
  backup_retention_days         = 35
  geo_redundant_backup_enabled  = true
  delegated_subnet_id           = azurerm_subnet.postgres.id
  private_dns_zone_id           = azurerm_private_dns_zone.postgres.id
  public_network_access_enabled = false
  administrator_login           = "pgadmin"
  administrator_password        = random_password.pg_admin.result
  zone                          = "1"
  high_availability {
    mode                      = "ZoneRedundant"
    standby_availability_zone = "2"
  }
  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = true
    tenant_id                     = data.azurerm_client_config.current.tenant_id
  }
  tags       = local.tags
  depends_on = [azurerm_private_dns_zone_virtual_network_link.postgres]
}

resource "azurerm_postgresql_flexible_server_database" "legal" {
  name      = "legal"
  server_id = azurerm_postgresql_flexible_server.main.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

# pgvector must be allow-listed before `create extension vector` (migration 0001).
resource "azurerm_postgresql_flexible_server_configuration" "extensions" {
  name      = "azure.extensions"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "VECTOR"
}

resource "azurerm_postgresql_flexible_server_configuration" "timezone" {
  name      = "timezone"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "UTC"
}

resource "azurerm_postgresql_flexible_server_configuration" "pgbouncer" {
  name      = "pgbouncer.enabled"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "true"
}

# ------------------------------------------------------------------------------------------------ Key Vault
resource "azurerm_key_vault" "main" {
  name                          = substr(replace("kv-${local.name}", "-", ""), 0, 24)
  location                      = azurerm_resource_group.main.location
  resource_group_name           = azurerm_resource_group.main.name
  tenant_id                     = data.azurerm_client_config.current.tenant_id
  sku_name                      = "standard"
  rbac_authorization_enabled    = true
  purge_protection_enabled      = true
  soft_delete_retention_days    = 90
  public_network_access_enabled = false
  tags                          = local.tags
}

resource "azurerm_private_endpoint" "kv" {
  name                = "pe-kv-${local.name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  subnet_id           = azurerm_subnet.endpoints.id
  private_service_connection {
    name                           = "kv"
    private_connection_resource_id = azurerm_key_vault.main.id
    subresource_names              = ["vault"]
    is_manual_connection           = false
  }
  tags = local.tags
}

# Workload identity for the app: reads its secrets from Key Vault through the CSI driver / External Secrets.
resource "azurerm_user_assigned_identity" "app" {
  name                = "id-${local.name}-app"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.tags
}

resource "azurerm_federated_identity_credential" "app" {
  name                = "legal-ai-app"
  resource_group_name = azurerm_resource_group.main.name
  parent_id           = azurerm_user_assigned_identity.app.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = azurerm_kubernetes_cluster.main.oidc_issuer_url
  subject             = "system:serviceaccount:legal-ai:legal-legal-ai"
}

resource "azurerm_role_assignment" "app_kv_reader" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

# ------------------------------------------------------------------------------------------------ immutable audit storage
resource "azurerm_storage_account" "audit" {
  name                            = substr(replace("st${local.name}audit", "-", ""), 0, 24)
  resource_group_name             = azurerm_resource_group.main.name
  location                        = azurerm_resource_group.main.location
  account_tier                    = "Standard"
  account_replication_type        = "ZRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  shared_access_key_enabled       = false
  public_network_access_enabled   = false
  blob_properties {
    versioning_enabled = true
    delete_retention_policy { days = 30 }
  }
  tags = local.tags
}

resource "azurerm_storage_container" "audit" {
  name                  = "audit-chain"
  storage_account_id    = azurerm_storage_account.audit.id
  container_access_type = "private"
}

# WORM: nightly audit-chain exports cannot be modified or deleted for 7 years.
resource "azurerm_storage_container_immutability_policy" "audit" {
  storage_container_resource_manager_id = azurerm_storage_container.audit.id
  immutability_period_in_days           = 2555
  protected_append_writes_all_enabled   = false
}

resource "azurerm_role_assignment" "app_audit_writer" {
  scope                = azurerm_storage_container.audit.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}
