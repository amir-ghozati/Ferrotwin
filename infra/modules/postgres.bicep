targetScope = 'resourceGroup'

param serverName string
param location string

@secure()
param administratorPassword string

param administratorLogin string = 'pgadmin'

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: serverName
  location: location

  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }

  properties: {
    administratorLogin: administratorLogin
    administratorLoginPassword: administratorPassword

    version: '16'

    storage: {
      storageSizeGB: 32
    }

    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }

    network: {
      publicNetworkAccess: 'Enabled'
    }

    highAvailability: {
      mode: 'Disabled'
    }
  }
}
