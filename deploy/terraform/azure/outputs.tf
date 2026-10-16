output "resource_group" {
  value = azurerm_resource_group.main.name
}

output "aks_name" {
  value = azurerm_kubernetes_cluster.main.name
}

output "postgres_fqdn" {
  description = "Private FQDN; DATABASE_URL secrets in Key Vault point here"
  value       = azurerm_postgresql_flexible_server.main.fqdn
}

output "key_vault_uri" {
  value = azurerm_key_vault.main.vault_uri
}

output "app_identity_client_id" {
  description = "Annotate the app ServiceAccount with azure.workload.identity/client-id"
  value       = azurerm_user_assigned_identity.app.client_id
}

output "audit_container_id" {
  value = azurerm_storage_container.audit.id
}

output "postgres_admin_password" {
  description = "Bootstrap only: store in Key Vault, create app_login / worker_login, then rotate"
  value       = random_password.pg_admin.result
  sensitive   = true
}
