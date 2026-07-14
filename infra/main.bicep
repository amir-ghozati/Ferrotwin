targetScope = 'subscription'

@description('Deployment location')
param location string = 'westeurope'

@description('Resource Group name')
param resourceGroupName string = 'ferrotwin-rg'

@description('Application Insights name')
param appInsightsName string = 'ferrotwin-ai'

@description('Storage Account name')
param storageAccountName string = 'ferrotwinst001'

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

resource rg 'Microsoft.Resources/resourceGroups@2024-11-01' = {
  name: resourceGroupName
  location: location
}

module workload './workload.bicep' = {
  name: 'workload'

  scope: resourceGroup(resourceGroupName)

  params: {
    location: location
    appInsightsName: appInsightsName
    storageAccountName: storageAccountName
    eventGridTopicName: eventGridTopicName
    digitalTwinsName: digitalTwinsName
    functionAppName: functionAppName
    functionPlanName: functionPlanName
    /*postgresServerName: postgresServerName
    postgresPassword: postgresPassword
    postgresLocation: postgresLocation*/
    currentUserObjectId: currentUserObjectId
    containerAppsEnvironmentName: containerAppsEnvironmentName
    inferenceAppName: inferenceAppName
    postgresContainerName: postgresContainerName
    postgresPassword: postgresPassword
  }

  dependsOn: [
    rg
  ]
}
