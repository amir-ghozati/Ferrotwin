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
/*param postgresServerName string

@secure()
param postgresPassword string
param postgresLocation string
*/
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
    /*functionAppName: functionAppName
    postgresServerName: postgresServerName
    postgresPassword: postgresPassword
    postgresLocation: postgresLocation*/
  }

  dependsOn: [
    rg
  ]
}
