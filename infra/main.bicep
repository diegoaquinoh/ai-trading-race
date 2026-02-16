targetScope = 'resourceGroup'

// ── Parameters ──────────────────────────────────────────────────────────────
param location string = 'westeurope'

@secure()
param sqlAdminPassword string

@secure()
param jwtSecretKey string

@secure()
param mlApiKey string

@secure()
param azureOpenAiApiKey string = ''
param azureOpenAiEndpoint string = ''

param ghcrUsername string

@secure()
param ghcrPassword string

param mlImageTag string = 'latest'

param githubRepoUrl string

@secure()
param githubToken string

param productionDomain string

// ── Modules (ordered by dependency) ─────────────────────────────────────────

// 1. SQL Server (no dependencies)
module sql 'modules/sql.bicep' = {
  name: 'sql'
  params: {
    location: location
    sqlAdminPassword: sqlAdminPassword
  }
}

// 2. Static Web App (no dependencies)
module staticWebApp 'modules/static-web-app.bicep' = {
  name: 'staticWebApp'
  params: {
    location: 'westeurope' // Static Web Apps only available in limited regions
    githubRepoUrl: githubRepoUrl
    githubToken: githubToken
  }
}

// 3. Container Apps - ML service (no dependencies, deployed before app-service)
module containerApps 'modules/container-apps.bicep' = {
  name: 'containerApps'
  params: {
    location: location
    mlApiKey: mlApiKey
    ghcrUsername: ghcrUsername
    ghcrPassword: ghcrPassword
    mlImageTag: mlImageTag
    productionDomain: productionDomain
  }
}

// 4. App Service (depends on sql + container-apps)
module appService 'modules/app-service.bicep' = {
  name: 'appService'
  params: {
    location: location
    jwtSecretKey: jwtSecretKey
    mlApiKey: mlApiKey
    sqlServerFqdn: sql.outputs.serverFqdn
    sqlDatabaseName: sql.outputs.databaseName
    sqlAdminPassword: sqlAdminPassword
    mlAppFqdn: containerApps.outputs.mlAppFqdn
    productionDomain: productionDomain
  }
}

// 5. Functions (depends on sql + app-service + container-apps)
module functions 'modules/functions.bicep' = {
  name: 'functions'
  params: {
    location: 'westeurope' // francecentral doesn't support Linux consumption plans
    sqlServerFqdn: sql.outputs.serverFqdn
    sqlDatabaseName: sql.outputs.databaseName
    sqlAdminPassword: sqlAdminPassword
    webAppOutboundIps: appService.outputs.outboundIpAddresses
    azureOpenAiApiKey: azureOpenAiApiKey
    azureOpenAiEndpoint: azureOpenAiEndpoint
    mlApiKey: mlApiKey
    mlAppFqdn: containerApps.outputs.mlAppFqdn
  }
}

// ── Outputs ─────────────────────────────────────────────────────────────────
output sqlServerFqdn string = sql.outputs.serverFqdn
output sqlDatabaseName string = sql.outputs.databaseName
output apiUrl string = 'https://${appService.outputs.defaultHostName}'
output functionsUrl string = 'https://${functions.outputs.defaultHostName}'
output mlInternalFqdn string = containerApps.outputs.mlAppFqdn
output staticWebAppUrl string = 'https://${staticWebApp.outputs.defaultHostName}'
