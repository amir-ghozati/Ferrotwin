targetScope = 'resourceGroup'

param digitalTwinsName string
param principalId string
param functionPrincipalId string
param storageAccountName string

resource adt 'Microsoft.DigitalTwins/digitalTwinsInstances@2023-01-31' existing = {
  name: digitalTwinsName
}

resource adtDataOwner 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(adt.id, principalId, 'Azure Digital Twins Data Owner')

  scope: adt

  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'bcd981a7-7f74-457b-83e1-cceb9e632ffe'
    )
  }
}

resource functionAdtOwner 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(adt.id, functionPrincipalId, 'Azure Digital Twins Data Owner')

  scope: adt

  properties: {
    principalId: functionPrincipalId
    principalType: 'ServicePrincipal'

    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'bcd981a7-7f74-457b-83e1-cceb9e632ffe'
    )
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2024-01-01' existing = {
  name: storageAccountName
}

resource functionBlobReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, functionPrincipalId, 'Storage Blob Data Reader')

  scope: storage

  properties: {
    principalId: functionPrincipalId
    principalType: 'ServicePrincipal'

    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
    )
  }
}
