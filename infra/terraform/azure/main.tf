# ═══════════════════════════════════════════════════════════════════════════════
# PostgreSQL no Azure dentro do plano gratuito (12 meses):
#   750 h/mês de Burstable B1ms + 32 GB de armazenamento + 32 GB de backup.
# Um único servidor ligado 24 h cabe nas 750 h (o mês mais longo tem 744 h).
#
# Tudo que sairia do gratuito está fixado aqui: sem alta disponibilidade, sem
# backup geo-redundante, Premium SSD (não v2) de 32 GB no tier P4, sem
# crescimento automático do disco. Um orçamento avisa por e-mail qualquer gasto.
# ═══════════════════════════════════════════════════════════════════════════════

locals {
  tags = {
    projeto   = "previsao-precos-imoveis"
    ambiente  = "portfolio"
    gerenciar = "terraform"
  }
}

data "azurerm_subscription" "atual" {}

resource "azurerm_resource_group" "imoveis" {
  name     = "rg-${var.prefixo}"
  location = var.location
  tags     = local.tags
}

# Nome do servidor precisa ser único no Azure inteiro (vira <nome>.postgres.database.azure.com)
resource "random_string" "sufixo" {
  length  = 6
  upper   = false
  special = false
}

resource "random_password" "admin" {
  length           = 24
  special          = true
  override_special = "-_."
}

resource "azurerm_postgresql_flexible_server" "imoveis" {
  name                = "${var.prefixo}-pg-${random_string.sufixo.result}"
  resource_group_name = azurerm_resource_group.imoveis.name
  location            = azurerm_resource_group.imoveis.location
  version             = "16" # mesma versão do Postgres local (docker-compose)

  administrator_login    = "${var.prefixo}admin"
  administrator_password = random_password.admin.result

  # Gratuito: Burstable B1ms, 32 GB Premium SSD (P4), sem autogrow
  sku_name          = "B_Standard_B1ms"
  storage_mb        = 32768
  storage_tier      = "P4"
  auto_grow_enabled = false

  # Gratuito: 32 GB de backup; 7 dias locais bastam, nada de geo-redundância
  backup_retention_days        = 7
  geo_redundant_backup_enabled = false

  # Sem bloco high_availability = sem servidor standby (ele dobraria as horas)
  public_network_access_enabled = true

  tags = local.tags

  lifecycle {
    # O Azure escolhe a zona na criação; mudar depois forçaria recriar o servidor
    ignore_changes = [zone]
  }
}

resource "azurerm_postgresql_flexible_server_database" "imoveis" {
  name      = "imoveis"
  server_id = azurerm_postgresql_flexible_server.imoveis.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

# Serviços na nuvem (API no Render): faixas compartilhadas da região, em CIDR
resource "azurerm_postgresql_flexible_server_firewall_rule" "faixas" {
  for_each         = toset(var.faixas_liberadas)
  name             = "faixa-${replace(replace(each.value, ".", "-"), "/", "_")}"
  server_id        = azurerm_postgresql_flexible_server.imoveis.id
  start_ip_address = cidrhost(each.value, 0)
  end_ip_address   = cidrhost(each.value, -1)
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "liberados" {
  for_each         = toset(var.ips_liberados)
  name             = "ip-${replace(each.value, ".", "-")}"
  server_id        = azurerm_postgresql_flexible_server.imoveis.id
  start_ip_address = each.value
  end_ip_address   = each.value
}

# Alerta de custo: o uso gratuito sai como custo zero, então qualquer gasto real
# (mesmo descontado do crédito) indica algo fora do plano gratuito.
resource "azurerm_consumption_budget_subscription" "alerta_custo" {
  name            = "orcamento-${var.prefixo}"
  subscription_id = data.azurerm_subscription.atual.id
  amount          = var.orcamento_mensal
  time_grain      = "Monthly"

  time_period {
    start_date = formatdate("YYYY-MM-01'T'00:00:00Z", timestamp())
  }

  notification {
    enabled        = true
    threshold      = 1 # 1% do orçamento = qualquer centavo gasto
    operator       = "GreaterThanOrEqualTo"
    threshold_type = "Actual"
    contact_emails = [var.email_alertas]
  }

  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThanOrEqualTo"
    threshold_type = "Forecasted"
    contact_emails = [var.email_alertas]
  }

  lifecycle {
    # start_date é calculado na criação; sem isto todo plan tentaria recriar o orçamento
    ignore_changes = [time_period]
  }
}
