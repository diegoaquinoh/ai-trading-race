param location string
param sqlServerFqdn string
param sqlDatabaseName string
param sqlAdminPassword string
param webAppOutboundIps string

var storageName = 'aitradingracefunc'
var planName = 'ai-trading-race-func-plan'
var appName = 'ai-trading-race-func'

var outboundIps = split(webAppOutboundIps, ',')

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

resource functionPlan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: planName
  location: location
  kind: 'functionapp'
  sku: {
    name: 'Y1'
    tier: 'Dynamic'
  }
  properties: {}
}

resource functionApp 'Microsoft.Web/sites@2023-12-01' = {
  name: appName
  location: location
  kind: 'functionapp,linux'
  properties: {
    serverFarmId: functionPlan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'DOTNET-ISOLATED|8.0'
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      appSettings: [
        {
          name: 'AzureWebJobsStorage'
          value: 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};AccountKey=${storageAccount.listKeys().keys[0].value};EndpointSuffix=core.windows.net'
        }
        { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME', value: 'dotnet-isolated' }
        {
          name: 'ConnectionStrings__TradingDb'
          value: 'Server=tcp:${sqlServerFqdn},1433;Initial Catalog=${sqlDatabaseName};Persist Security Info=False;User ID=sqladmin;Password=${sqlAdminPassword};MultipleActiveResultSets=False;Encrypt=True;TrustServerCertificate=False;Connection Timeout=30;'
        }
      ]
      ipSecurityRestrictions: concat(
        [
          {
            name: 'AllowAzureCloud'
            priority: 100
            action: 'Allow'
            tag: 'ServiceTag'
            ipAddress: 'AzureCloud'
          }
        ],
        [for (ip, i) in outboundIps: {
          name: 'AllowWebApp${i}'
          priority: 110 + i
          action: 'Allow'
          ipAddress: '${trim(ip)}/32'
        }],
        [
          {
            name: 'DenyAll'
            priority: 500
            action: 'Deny'
            ipAddress: '0.0.0.0/0'
          }
        ]
      )
      ipSecurityRestrictionsDefaultAction: 'Deny'
    }
  }
}

output defaultHostName string = functionApp.properties.defaultHostName
