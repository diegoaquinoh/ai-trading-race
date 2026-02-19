param location string
param sqlServerFqdn string
param sqlDatabaseName string

@secure()
param sqlAdminPassword string

param webAppOutboundIps string

// AI & external service configuration
@secure()
param azureOpenAiApiKey string = ''
param azureOpenAiEndpoint string = ''
param azureOpenAiGPT4oMiniDeploymentName string = ''
param azureOpenAiGPT41NanoDeploymentName string = ''

param coinGeckoBaseUrl string = 'https://api.coingecko.com/api/v3/'
param coinGeckoApiKey string = ''

@secure()
param mlApiKey string = ''
param mlAppFqdn string = ''

var storageName = 'aitradingracefunc'
var planName = 'ai-trading-race-func-plan'
var appName = 'ai-trading-race-func'

var outboundIps = split(webAppOutboundIps, ',')

var webAppIpRules = [for (ip, i) in outboundIps: {
  name: 'AllowWebApp${i}'
  priority: 110 + i
  action: 'Allow'
  ipAddress: '${trim(ip)}/32'
}]

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
  properties: {
    reserved: true // Required for Linux
  }
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
        // Azure Functions runtime
        {
          name: 'AzureWebJobsStorage'
          value: 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};AccountKey=${storageAccount.listKeys().keys[0].value};EndpointSuffix=core.windows.net'
        }
        { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME', value: 'dotnet-isolated' }
        { name: 'WEBSITE_RUN_FROM_PACKAGE', value: '1' }
        {
          name: 'ConnectionStrings__TradingDb'
          value: 'Server=tcp:${sqlServerFqdn},1433;Initial Catalog=${sqlDatabaseName};Persist Security Info=False;User ID=sqladmin;Password=${sqlAdminPassword};MultipleActiveResultSets=False;Encrypt=True;TrustServerCertificate=False;Connection Timeout=30;'
        }
        // CoinGecko - market data ingestion
        { name: 'CoinGecko__BaseUrl', value: coinGeckoBaseUrl }
        { name: 'CoinGecko__TimeoutSeconds', value: '30' }
        { name: 'CoinGecko__DefaultDays', value: '1' }
        { name: 'CoinGecko__ApiKey', value: coinGeckoApiKey }
        // Azure OpenAI - agent decisions
        { name: 'AzureOpenAI__Endpoint', value: azureOpenAiEndpoint }
        { name: 'AzureOpenAI__ApiKey', value: azureOpenAiApiKey }
        { name: 'AzureOpenAI__GPT4_o_Mini_DeploymentName', value: azureOpenAiGPT4oMiniDeploymentName }
        { name: 'AzureOpenAI__GPT4_1_nano_DeploymentName', value: azureOpenAiGPT41NanoDeploymentName }
        // Custom ML Agent
        { name: 'CustomMlAgent__BaseUrl', value: mlAppFqdn != '' ? 'https://${mlAppFqdn}' : '' }
        { name: 'CustomMlAgent__ApiKey', value: mlApiKey }
        { name: 'CustomMlAgent__TimeoutSeconds', value: '60' }
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
        webAppIpRules,
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
