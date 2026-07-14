targetScope = 'resourceGroup'

param environmentName string
param location string

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentName
  location: location

  properties: {}
}

output environmentId string = env.id
