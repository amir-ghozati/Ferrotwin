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

resource functionBlobContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, functionPrincipalId, 'Storage Blob Data Contributor')

  scope: storage

  properties: {
    principalId: functionPrincipalId
    principalType: 'ServicePrincipal'

    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
    )
  }
}

resource functionTableContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, functionPrincipalId, 'Storage Table Data Contributor')

  scope: storage

  properties: {
    principalId: functionPrincipalId
    principalType: 'ServicePrincipal'

    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '0a9a7e1f-baf0-4e21-8d1b-8b6610f9f4f6'
    )
  }
}
