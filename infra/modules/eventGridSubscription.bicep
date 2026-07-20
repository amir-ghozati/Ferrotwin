targetScope = 'resourceGroup'

@description('Custom Event Grid topic name')
param topicName string

@description('Function App receiving custom topic events')
param functionAppName string

resource topic 'Microsoft.EventGrid/topics@2025-02-15' existing = {
  name: topicName
}

resource functionApp 'Microsoft.Web/sites@2024-04-01' existing = {
  name: functionAppName
}

resource functionEvents 'Microsoft.EventGrid/topics/eventSubscriptions@2025-02-15' = {
  parent: topic
  name: 'ferrotwin-function-events'

  properties: {
    destination: {
      endpointType: 'AzureFunction'
      properties: {
        resourceId: '${functionApp.id}/functions/process_event'
      }
    }
    filter: {
      includedEventTypes: [
        'FerroTwin.TelemetryReceived'
        'FerroTwin.InspectionCompleted'
      ]
    }
    retryPolicy: {
      maxDeliveryAttempts: 10
      eventTimeToLiveInMinutes: 1440
    }
  }
}
