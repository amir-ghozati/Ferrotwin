targetScope = 'subscription'

param location string
param resourceGroupName string

resource rg 'Microsoft.Resources/resourceGroups@2024-11-01' = {
  name: resourceGroupName
  location: location
}

output resourceGroupId string = rg.id
