targetScope = 'resourceGroup'

param location string
param appInsightsName string
param storageAccountName string
param eventGridTopicName string
param digitalTwinsName string
param functionAppName string
param functionPlanName string
param currentUserObjectId string
param containerAppsEnvironmentName string
param inferenceAppName string
param postgresContainerName string

@secure()
param postgresPassword string


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

module functionApp './modules/functionApp.bicep' = {
  name: 'function-app'

  params: {
    functionAppName: functionAppName
    functionPlanName: functionPlanName
    storageAccountName: storageAccountName
    appInsightsName: appInsightsName
    location: location
  }
}

module roleAssignments './modules/roleAssignments.bicep' = {
  name: 'rbac'

  params: {
    digitalTwinsName: digitalTwinsName
    principalId: currentUserObjectId

    functionPrincipalId: functionApp.outputs.principalId
    storageAccountName: storageAccountName
  }
}

module containerAppsEnvironment './modules/containerAppsEnvironment.bicep' = {
  name: 'containerapps-env'

  params: {
    environmentName: containerAppsEnvironmentName
    location: location
  }
}
module inference './modules/containerApp.bicep' = {
  name: 'inference'

  params: {
    appName: inferenceAppName
    environmentName: containerAppsEnvironmentName
    location: location
  }
}

module postgresContainer './modules/postgresContainer.bicep' = {
  name: 'postgres-container'

  params: {
    appName: postgresContainerName
    environmentName: containerAppsEnvironmentName
    location: location
    postgresPassword: postgresPassword
  }
}
