param location string

@secure()
param mlApiKey string

param ghcrUsername string

@secure()
param ghcrPassword string

param mlImageTag string
param productionDomain string

var envName = 'ai-trading-race-env'
var appName = 'ai-trading-ml'

resource containerAppEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: envName
  location: location
  properties: {
    zoneRedundant: false
  }
}

resource mlApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  properties: {
    managedEnvironmentId: containerAppEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
      }
      registries: [
        {
          server: 'ghcr.io'
          username: ghcrUsername
          passwordSecretRef: 'ghcr-password'
        }
      ]
      secrets: [
        {
          name: 'ghcr-password'
          value: ghcrPassword
        }
        {
          name: 'ml-api-key'
          value: mlApiKey
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'ml-service'
          image: 'ghcr.io/diegoaquinoh/ai-trading-race-ml:${mlImageTag}'
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            { name: 'ML_SERVICE_API_KEY', secretRef: 'ml-api-key' }
            { name: 'ML_SERVICE_ALLOWED_ORIGIN', value: productionDomain }
            { name: 'ENVIRONMENT', value: 'production' }
            { name: 'ML_SERVICE_REDIS_ENABLED', value: 'true' }
            { name: 'ML_SERVICE_REDIS_HOST', value: 'localhost' }
            { name: 'ML_SERVICE_REDIS_PORT', value: '6379' }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              periodSeconds: 30
              initialDelaySeconds: 10
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              periodSeconds: 10
              initialDelaySeconds: 5
            }
          ]
        }
        {
          name: 'redis'
          image: 'redis:7-alpine'
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          command: [
            'redis-server'
            '--appendonly'
            'no'
            '--maxmemory'
            '64mb'
            '--maxmemory-policy'
            'allkeys-lru'
          ]
          probes: [
            {
              type: 'Liveness'
              tcpSocket: {
                port: 6379
              }
              periodSeconds: 30
              initialDelaySeconds: 5
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 1
      }
    }
  }
}

output mlAppFqdn string = mlApp.properties.configuration.ingress.fqdn
