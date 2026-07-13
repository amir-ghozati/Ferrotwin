targetScope = 'resourceGroup'

param digitalTwinsName string
param topicName string

resource adt 'Microsoft.DigitalTwins/digitalTwinsInstances@2023-01-31' existing = {
  name: digitalTwinsName
}

resource topic 'Microsoft.EventGrid/topics@2025-02-15' existing = {
  name: topicName
}

resource endpoint 'Microsoft.DigitalTwins/digitalTwinsInstances/endpoints@2023-01-31' = {
  parent: adt
  name: 'eventgrid'

  properties: {
    endpointType: 'EventGrid'

    authenticationType: 'KeyBased'

    TopicEndpoint: topic.properties.endpoint

    accessKey1: listKeys(
      topic.id,
      '2025-02-15'
    ).key1
  }
}
