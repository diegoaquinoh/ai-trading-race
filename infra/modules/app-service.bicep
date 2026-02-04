param location string

@secure()
param jwtSecretKey string

@secure()
param mlApiKey string

param sqlServerFqdn string
param sqlDatabaseName string

@secure()
param sqlAdminPassword string

param mlAppFqdn string
param productionDomain string

var planName = 'ai-trading-race-plan'
var appName = 'ai-trading-race-api'

resource appServicePlan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: planName
  location: location
  kind: 'linux'
  sku: {
    name: 'F1'
    tier: 'Free'
  }
  properties: {
    reserved: true // required for Linux
  }
}

resource webApp 'Microsoft.Web/sites@2023-12-01' = {
  name: appName
  location: location
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'DOTNETCORE|8.0'
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      appSettings: [
        { name: 'Authentication__Jwt__SecretKey', value: jwtSecretKey }
        { name: 'CustomMlAgent__ApiKey', value: mlApiKey }
        { name: 'CustomMlAgent__BaseUrl', value: 'https://${mlAppFqdn}' }
        { name: 'ASPNETCORE_ENVIRONMENT', value: 'Production' }
        { name: 'AllowedOrigins__0', value: productionDomain }
      ]
      connectionStrings: [
        {
          name: 'TradingDb'
          connectionString: 'Server=tcp:${sqlServerFqdn},1433;Initial Catalog=${sqlDatabaseName};Persist Security Info=False;User ID=sqladmin;Password=${sqlAdminPassword};MultipleActiveResultSets=False;Encrypt=True;TrustServerCertificate=False;Connection Timeout=30;'
          type: 'SQLAzure'
        }
      ]
    }
  }
}

output defaultHostName string = webApp.properties.defaultHostName
output outboundIpAddresses string = webApp.properties.outboundIpAddresses
