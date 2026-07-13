targetScope = 'resourceGroup'

@description('Azure Digital Twins instance name')
param digitalTwinsName string

@description('Deployment location')
param location string

resource adt 'Microsoft.DigitalTwins/digitalTwinsInstances@2023-01-31' = {
  name: digitalTwinsName
  location: location

  identity: {
    type: 'SystemAssigned'
  }

  properties: {
    publicNetworkAccess: 'Enabled'
  }
}

output id string = adt.id
output hostName string = adt.properties.hostName
output principalId string = adt.identity.principalId
