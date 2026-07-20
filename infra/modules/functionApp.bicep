targetScope = 'resourceGroup'

param functionAppName string
param functionPlanName string
param storageAccountName string
param appInsightsName string
param location string
param adtHost string
param eventGridTopicName string
param dashboardAllowedOrigin string

resource storage 'Microsoft.Storage/storageAccounts@2024-01-01' existing = {
  name: storageAccountName
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: appInsightsName
}

resource eventGridTopic 'Microsoft.EventGrid/topics@2025-02-15' existing = {
  name: eventGridTopicName
}

resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: functionPlanName
  location: location

  sku: {
    name: 'Y1'
    tier: 'Dynamic'
  }

  kind: 'linux'

  properties: {
    reserved: true
  }
}

resource function 'Microsoft.Web/sites@2024-04-01' = {
  name: functionAppName
  location: location
  kind: 'functionapp,linux'

  identity: {
    type: 'SystemAssigned'
  }

  properties: {
    serverFarmId: plan.id

    httpsOnly: true

    siteConfig: {
      linuxFxVersion: 'Python|3.12'

      cors: {
        allowedOrigins: [
          dashboardAllowedOrigin
        ]
        supportCredentials: false
      }

      appSettings: [
        {
          name: 'FUNCTIONS_WORKER_RUNTIME'
          value: 'python'
        }
        {
          name: 'FUNCTIONS_EXTENSION_VERSION'
          value: '~4'
        }
        {
          name: 'AzureWebJobsStorage'
          value: 'DefaultEndpointsProtocol=https;AccountName=${storage.name};AccountKey=${storage.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: reference(appInsights.id, '2020-02-02').ConnectionString
        }
        {
          name: 'ADT_HOST'
          value: adtHost
        }
        {
          name: 'STORAGE_ACCOUNT_NAME'
          value: storage.name
        }
        {
          name: 'INSPECTION_BLOB_CONTAINER'
          value: 'inspections'
        }
        {
          name: 'EVENT_GRID_ENABLED'
          value: 'true'
        }
        {
          name: 'EVENT_GRID_TOPIC_ENDPOINT'
          value: eventGridTopic.properties.endpoint
        }
        {
          name: 'EVENT_GRID_TOPIC_KEY'
          value: listKeys(eventGridTopic.id, '2025-02-15').key1
        }
        {
          name: 'TEMPERATURE_ALERT_THRESHOLD'
          value: '900'
        }
        {
          name: 'REPEATED_DEFECT_COUNT'
          value: '3'
        }
        {
          name: 'REPEATED_DEFECT_WINDOW_MINUTES'
          value: '30'
        }
      ]
    }
  }
}
output principalId string = function.identity.principalId
output functionName string = function.name
output functionResourceId string = function.id
