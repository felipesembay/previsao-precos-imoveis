variable "location" {
  description = "Região do Azure. O B1ms gratuito está disponível em brazilsouth."
  type        = string
  default     = "brazilsouth"
}

variable "prefixo" {
  description = "Prefixo dos nomes dos recursos."
  type        = string
  default     = "imoveis"
}

variable "ips_liberados" {
  description = "IPv4 que podem conectar no Postgres (o firewall do Azure não aceita IPv6)."
  type        = list(string)
}

variable "faixas_liberadas" {
  description = "Faixas IPv4 em CIDR que podem conectar no Postgres (ex.: IPs de saída do Render, em Connect → Outbound)."
  type        = list(string)
  default     = []
}

variable "email_alertas" {
  description = "E-mail que recebe o alerta de orçamento."
  type        = string
}

variable "orcamento_mensal" {
  description = "Orçamento mensal na moeda da conta. Qualquer gasto real acima de 1% dele (centavos) gera e-mail."
  type        = number
  default     = 1
}
