// SQL Server firewall: allow only the outbound IPs of the apps that use the database.
// Replaces the "Allow Azure services" rule, which admits every Azure customer's IPs.
// The IP lists are module parameters, so the rule count is known when this module deploys.

param sqlServerName string

@description('Comma-separated possible outbound IPs of the App Service')
param appServiceOutboundIps string

@description('Comma-separated possible outbound IPs of the Function App')
param functionsOutboundIps string

var allowedIps = filter(
  union(map(split(appServiceOutboundIps, ','), ip => trim(ip)), map(split(functionsOutboundIps, ','), ip => trim(ip))),
  ip => !empty(ip)
)

resource sqlServer 'Microsoft.Sql/servers@2023-08-01-preview' existing = {
  name: sqlServerName
}

resource appOutboundRules 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = [for (ip, i) in allowedIps: {
  parent: sqlServer
  name: 'AllowAppOutbound-${i}'
  properties: {
    startIpAddress: ip
    endIpAddress: ip
  }
}]

output allowedIpCount int = length(allowedIps)
