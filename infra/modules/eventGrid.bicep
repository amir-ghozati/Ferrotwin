targetScope = 'resourceGroup'

@description('Event Grid Topic name')
param topicName string

@description('Deployment location')
param location string

resource topic 'Microsoft.EventGrid/topics@2025-02-15' = {
  name: topicName
  location: location

  identity: {
    type: 'SystemAssigned'
  }
}

output topicId string = topic.id
output topicEndpoint string = topic.properties.endpoint
output topicName string = topic.name
