param location string

@secure()
param sqlAdminPassword string

var serverName = 'ai-trading-sql'
var databaseName = 'AiTradingRace'

resource sqlServer 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: serverName
  location: location
  properties: {
    administratorLogin: 'sqladmin'
    administratorLoginPassword: sqlAdminPassword
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
  }
}

resource sqlDatabase 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  parent: sqlServer
  name: databaseName
  location: location
  sku: {
    name: 'Free'
  }
  properties: {
    maxSizeBytes: 33554432 // 32 MB - Free tier limit
  }
}

// No "Allow Azure services" (0.0.0.0) rule: it admits every Azure customer's IPs. The App
// Service and Function App outbound IPs are allowed by sql-firewall.bicep once both exist.

output serverName string = sqlServer.name
output serverFqdn string = sqlServer.properties.fullyQualifiedDomainName
output databaseName string = databaseName
