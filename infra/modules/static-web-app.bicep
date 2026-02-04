param location string
param githubRepoUrl string
param githubToken string

resource staticWebApp 'Microsoft.Web/staticSites@2023-12-01' = {
  name: 'ai-trading-race-web'
  location: location
  sku: {
    name: 'Free'
    tier: 'Free'
  }
  properties: {
    repositoryUrl: githubRepoUrl
    branch: 'main'
    repositoryToken: githubToken
    buildProperties: {
      appLocation: 'ai-trading-race-web'
      outputLocation: 'dist'
    }
  }
}

output defaultHostName string = staticWebApp.properties.defaultHostname
