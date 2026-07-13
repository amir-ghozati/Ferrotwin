targetScope = 'resourceGroup'

param location string
param appInsightsName string
param storageAccountName string
param eventGridTopicName string
param digitalTwinsName string
//param functionAppName string
//param postgresServerName string
//param postgresLocation string

//@secure()
//param postgresPassword string

module appInsights './modules/applicationInsights.bicep' = {
  name: 'application-insights'

  params: {
    location: location
    appInsightsName: appInsightsName
  }
}

module storage './modules/storage.bicep' = {
  name: 'storage'

  params: {
    location: location
    storageAccountName: storageAccountName
  }
}

module eventGrid './modules/eventGrid.bicep' = {
  name: 'event-grid'

  params: {
    location: location
    topicName: eventGridTopicName
  }
}

module digitalTwins './modules/digitalTwins.bicep' = {
  name: 'digital-twins'

  params: {
    location: location
    digitalTwinsName: digitalTwinsName
  }
}

module digitalTwinsEndpoint './modules/digitalTwinsEndpoint.bicep' = {
  name: 'adt-endpoint'

  params: {
    digitalTwinsName: digitalTwinsName
    topicName: eventGrid.outputs.topicName
  }
  dependsOn: [
    digitalTwins
]
}

/*module functionApp './modules/functionApp.bicep' = {
  name: 'function-app'

  params: {
    functionAppName: functionAppName

    storageAccountName: storageAccountName

    appInsightsName: appInsightsName

    location: location
  }
}*/


/*module postgres './modules/postgres.bicep' = {
  name: 'postgres'

  params: {
    serverName: postgresServerName

    administratorPassword: postgresPassword

    location: postgresLocation
  }
}*/
