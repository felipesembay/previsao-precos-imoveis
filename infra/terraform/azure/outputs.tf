output "pg_host" {
  description = "Endereço do servidor (PG_HOST)."
  value       = azurerm_postgresql_flexible_server.imoveis.fqdn
}

output "pg_user" {
  value = azurerm_postgresql_flexible_server.imoveis.administrator_login
}

output "pg_db" {
  value = azurerm_postgresql_flexible_server_database.imoveis.name
}

output "pg_password" {
  description = "terraform output -raw pg_password"
  value       = random_password.admin.result
  sensitive   = true
}
